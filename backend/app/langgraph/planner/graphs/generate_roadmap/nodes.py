import asyncio
from uuid import uuid4

from app.core.config import settings
from app.langgraph.llm.gemini import get_gemini
from app.langgraph.planner.policy_prompt.milestone import (
    SHARED_MILESTONE_POLICY,
    SHARED_MILESTONE_POLICY_CORE,
)
from app.langgraph.planner.schema.review import QuickReviewResponse
from app.langgraph.planner.schema.state import PlannerState
from app.schema.entities import (
    LearningMemoryContext,
    MemoryRerankRequest,
    MilestoneItem,
    RetrieveLearningMemoryInput,
    RoadmapItem,
)
from app.schema.enums import MemoryRerankPurpose
from app.services import memory_service
from app.services.memory_rerank_policy import arerank_memories
from langgraph.types import Send
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .prompt import (
    MILESTONE_PROMPT,
    QUICK_REVIEW_PROMPT,
    REVISE_MILESTONE_PROMPT,
    SKILLPATH_PROMPT,
)
from .utils import finalize_skillpaths


class SimpleMilestone(BaseModel):
    title: str
    description: str
    objective: str
    estimated_hours: float
    dependencies: list[str] = Field(default_factory=list)


class MilestoneResponse(BaseModel):
    milestones: list[SimpleMilestone]


class SimpleSkillPath(BaseModel):
    title: str
    description: str
    estimated_hours: float
    learning_objectives: list[str] = Field(default_factory=list)
    depends_on_titles: list[str] = Field(default_factory=list)


class SkillPathResponse(BaseModel):
    skillpaths: list[SimpleSkillPath]


def _retrieve_memory_context(user_id: str, query_text: str) -> LearningMemoryContext:
    """Synchronously retrieve learner memory from inside a sync planner node.

    Mirrors the content-generation graph: wrap the async service call with a fresh
    DB session via ``asyncio.run``. No skillpath_id is supplied at planner scope, so
    mastery data arrives via ``linked_mastery_states`` (the linked_skillpath_ids bridge).
    """

    async def _run() -> LearningMemoryContext:
        # Use an isolated NullPool engine per call. The planner's sync nodes wrap
        # this in asyncio.run(), and the per-milestone skillpath_worker fan-out
        # runs several of them on different event loops. A shared/pooled engine
        # would leak asyncpg connections across loops ("attached to a different
        # loop"); a fresh NullPool engine, disposed after use, stays loop-local.
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                return await memory_service.retrieve_learning_memory(
                    RetrieveLearningMemoryInput(user_id=user_id, query_text=query_text),
                    session,
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _format_note_lines(label: str, notes) -> list[str]:
    if not notes:
        return []
    lines = [f"{label}:"]
    for note in notes:
        lines.append(f"  - {note.title}: {note.summary}")
    return lines


def _format_memory_for_prompt(context: LearningMemoryContext | None) -> str:
    """Render a LearningMemoryContext into labelled prompt text for the planner.

    Each memory type drives a different structural decision, so every bucket is
    rendered under a clear label. Returns a placeholder when there is no memory.
    """
    if context is None:
        return "LEARNER MEMORY: none available (treat learner as new)."

    sections: list[str] = []
    sections += _format_note_lines(
        "ERROR PATTERNS (expand / add remediation here)", context.active_error_patterns
    )
    sections += _format_note_lines(
        "MASTERY SIGNALS (skip or compress these areas)", context.mastery_signals
    )
    sections += _format_note_lines(
        "TEACHING HEURISTICS (shape ordering / progression)",
        context.teaching_heuristics,
    )
    sections += _format_note_lines(
        "BACKGROUND & PREFERENCES (adjust depth / pacing)", context.background_notes
    )

    if context.linked_mastery_states:
        sections.append("PRIOR SKILLPATH MASTERY (evidence from related skillpaths):")
        for skillpath_id, state in context.linked_mastery_states.items():
            sections.append(
                f"  - {skillpath_id}: status={state.status.value}, "
                f"score={state.mastery_score:.2f}, "
                f"strong={state.strong_concepts}, weak={state.weak_concepts}"
            )

    if not sections:
        return "LEARNER MEMORY: none available (treat learner as new)."
    return (
        "LEARNER MEMORY (personalize the roadmap structure accordingly):\n"
        + "\n".join(sections)
    )


def _rerank_milestone_memory(notes, milestone):
    """Select which retrieved notes matter for this milestone (LLM-first).

    Reuses the shared Rerank Policy with purpose=ROADMAP_PLANNING. The advisor is
    resolved inside arerank_memories (gated by ENABLE_MEMORY_RERANK_ADVISOR); when
    off/uncredentialed it returns the deterministic top-N. No DB access, so it is
    safe to wrap in its own asyncio.run.
    """

    async def _run():
        return await arerank_memories(
            MemoryRerankRequest(
                purpose=MemoryRerankPurpose.ROADMAP_PLANNING,
                task_context="\n".join(
                    part for part in (milestone.title, milestone.objective) if part
                ),
                candidate_memories=notes,
                max_selected=5,
            )
        )

    return asyncio.run(_run())


def _filter_context_by_ids(
    context: LearningMemoryContext, selected_ids: set[str]
) -> LearningMemoryContext:
    """Return a copy of the context whose note buckets keep only selected IDs."""

    def keep(notes):
        return [n for n in notes if n.memory_id in selected_ids]

    return LearningMemoryContext(
        mastery_state=context.mastery_state,
        recent_attempts=context.recent_attempts,
        active_error_patterns=keep(context.active_error_patterns),
        mastery_signals=keep(context.mastery_signals),
        teaching_heuristics=keep(context.teaching_heuristics),
        background_notes=keep(context.background_notes),
        relevant_notes=keep(context.relevant_notes),
        linked_mastery_states=context.linked_mastery_states,
    )


def retrieve_goal_memory(state: PlannerState):
    """Goal-level memory retrieval, before milestone generation.

    Runs once. Stores the goal-scoped context in state, shared (read-only) by
    generate_milestone, milestone_quick_review, and revise_milestones.
    """
    user_id = state.get("user_id")
    goal_spec = state.get("goal_spec")
    if not user_id or not goal_spec:
        return {}
    query_text = " ".join(
        part
        for part in (
            goal_spec.title,
            goal_spec.description,
            goal_spec.target_outcome,
        )
        if part
    )
    context = _retrieve_memory_context(user_id, query_text)
    return {"goal_memory_context": context}


def init_roadmap_context(state: PlannerState):
    if not state.get("roadmap_uuid"):
        return {"roadmap_uuid": str(uuid4())}
    return {}


def generate_milestone(state: PlannerState):
    roadmap_uuid = state.get("roadmap_uuid")
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")

    if not roadmap_uuid or not goal_spec or not learning_profile:
        return {}

    prompt = MILESTONE_PROMPT.format(
        goal_title=goal_spec.title,
        goal_description=goal_spec.description,
        target_outcome=goal_spec.target_outcome,
        deadline=goal_spec.deadline,
        criteria=goal_spec.criteria,
        constraints=goal_spec.constraints,
        baseline_level=learning_profile.baseline_level,
        prior_knowledges=learning_profile.prior_knowledges,
        weak_areas=learning_profile.weak_areas,
        pace_preference=learning_profile.pace_preference,
        shared_milestone_policy=SHARED_MILESTONE_POLICY,
    )
    prompt += "\n\n" + _format_memory_for_prompt(state.get("goal_memory_context"))

    llm = get_gemini()
    response = llm.with_structured_output(MilestoneResponse).invoke(prompt)

    milestones = []
    for i, simple in enumerate(response.milestones, start=1):
        milestones.append(
            MilestoneItem(
                roadmap_uuid=roadmap_uuid,
                milestone_id=str(uuid4()),
                title=simple.title,
                description=simple.description,
                objective=simple.objective,
                estimated_hours=simple.estimated_hours,
                order_index=i,
                dependency_titles=simple.dependencies,
                status="generated",
                need_modification=False,
                revision_reason=None,
            )
        )

    return {"milestones": milestones}


def milestone_quick_review(state: PlannerState):
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")
    milestones = state.get("milestones", [])
    revision_count = state.get("milestone_revision_count", 0)

    if not goal_spec or not learning_profile or not milestones:
        return {}

    prompt = (
        QUICK_REVIEW_PROMPT.format(shared_milestone_policy=SHARED_MILESTONE_POLICY)
        + f"""
Here is the actual data you need to check out

Current revision context:
- This roadmap has already been revised {revision_count} time(s).

Review guidance for repeated revision:
- Still focus on major structural issues only.
- Be stricter about blocking only when issues would materially harm downstream skill path generation.
- Do not block for minor imperfections, especially after one or more revision rounds.
- If the roadmap is workable and structurally sound enough, prefer proceeding.

Goal:
- Title: {goal_spec.title}
- Description: {goal_spec.description}
- Target outcome: {goal_spec.target_outcome}
- Deadline: {goal_spec.deadline}
- Success criteria: {goal_spec.criteria}
- Constraints: {goal_spec.constraints}

Learner profile:
- Baseline level: {learning_profile.baseline_level}
- Prior knowledges: {learning_profile.prior_knowledges}
- Weak areas: {learning_profile.weak_areas}
- Pace preference: {learning_profile.pace_preference}

Generated milestones:
{[m.model_dump() for m in milestones]}
"""
    )
    prompt += (
        "\n\n"
        + _format_memory_for_prompt(state.get("goal_memory_context"))
        + "\n\nDo NOT flag memory-driven omissions (mastered areas) or expansions "
        "(error-pattern remediation) as structural defects."
    )

    llm = get_gemini()
    response = llm.with_structured_output(QuickReviewResponse).invoke(prompt)
    return {"milestone_quick_review": response}


def route_after_milestone_quick_review(state: PlannerState):
    review = state.get("milestone_quick_review")
    if review and review.proceed:
        # Memory retrieval + rerank happens in a single pre-fan-out node (one event
        # loop, on this thread). The skillpath workers stay pure-sync so their
        # get_gemini().invoke() never runs after a worker-thread asyncio.run (which
        # would deadlock on a loop-bound Google client).
        return "retrieve_and_rerank_milestones"
    return "revise_milestones"


def retrieve_and_rerank_milestones(state: PlannerState):
    """Pre-fan-out: retrieve + rerank milestone memory for ALL milestones in one
    event loop (concurrently), then store per-milestone full context + selected ids
    in state. No async work happens inside the parallel skillpath workers.
    """
    user_id = state.get("user_id")
    milestones = state.get("milestones", [])
    if not user_id or not milestones:
        return {}

    async def _run():
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)

            async def _one(milestone):
                try:
                    query_text = " ".join(
                        part for part in (milestone.title, milestone.objective) if part
                    )
                    async with session_factory() as session:
                        context = await memory_service.retrieve_learning_memory(
                            RetrieveLearningMemoryInput(
                                user_id=user_id, query_text=query_text
                            ),
                            session,
                        )
                    selected_ids: list[str] = []
                    if context.relevant_notes:
                        rerank = await arerank_memories(
                            MemoryRerankRequest(
                                purpose=MemoryRerankPurpose.ROADMAP_PLANNING,
                                task_context=query_text,
                                candidate_memories=context.relevant_notes,
                                max_selected=5,
                            )
                        )
                        selected_ids = [m.memory_id for m in rerank.selected_memories]
                    return milestone.milestone_id, context, selected_ids
                except Exception:
                    return milestone.milestone_id, None, []

            return await asyncio.gather(*[_one(m) for m in milestones])
        finally:
            await engine.dispose()

    results = asyncio.run(_run())
    contexts = {mid: ctx for (mid, ctx, _ids) in results if ctx is not None}
    selected = {mid: ids for (mid, _ctx, ids) in results if ids}
    return {
        "milestone_memory_contexts": contexts,
        "milestone_selected_ids": selected,
    }


def route_to_skillpath_workers(state: PlannerState):
    """Fan out one skillpath_worker per milestone, passing the pre-computed,
    rerank-filtered memory context in each Send payload (workers stay sync)."""
    milestones = state.get("milestones", [])
    if not milestones:
        return []
    full = state.get("milestone_memory_contexts", {}) or {}
    selected = state.get("milestone_selected_ids", {}) or {}

    tasks = []
    for milestone in milestones:
        context = full.get(milestone.milestone_id)
        selected_ids = set(selected.get(milestone.milestone_id, []))
        prompt_context = context
        if context is not None and selected_ids:
            prompt_context = _filter_context_by_ids(context, selected_ids)
        tasks.append(
            Send(
                "skillpath_worker",
                {
                    "roadmap_uuid": state["roadmap_uuid"],
                    "goal_spec": state.get("goal_spec"),
                    "learning_profile": state.get("learning_profile"),
                    "milestone": milestone,
                    "milestone_prompt_context": prompt_context,
                },
            )
        )
    return tasks


def revise_milestones(state: PlannerState):
    roadmap_uuid = state.get("roadmap_uuid")
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")
    milestones = state.get("milestones", [])
    quick_review = state.get("milestone_quick_review")
    revision_count = state.get("milestone_revision_count", 0)

    if (
        not roadmap_uuid
        or not goal_spec
        or not learning_profile
        or not milestones
        or not quick_review
    ):
        return {}

    if quick_review.proceed:
        return {}

    findings = quick_review.findings
    if not findings:
        return {}

    current_milestones_for_prompt = []
    for i, m in enumerate(milestones, start=1):
        current_milestones_for_prompt.append(
            {
                "milestone_id": f"M{i}",
                "title": m.title,
                "description": m.description,
                "objective": m.objective,
                "estimated_hours": m.estimated_hours,
                "dependencies": list(m.dependency_titles or []),
            }
        )

    prompt = REVISE_MILESTONE_PROMPT.format(
        shared_milestone_policy_core=SHARED_MILESTONE_POLICY_CORE,
        goal_title=goal_spec.title,
        goal_description=goal_spec.description,
        target_outcome=goal_spec.target_outcome,
        deadline=goal_spec.deadline,
        criteria=goal_spec.criteria,
        constraints=goal_spec.constraints,
        baseline_level=learning_profile.baseline_level,
        prior_knowledges=learning_profile.prior_knowledges,
        weak_areas=learning_profile.weak_areas,
        pace_preference=learning_profile.pace_preference,
        milestones=current_milestones_for_prompt,
        review_findings=[f.model_dump() for f in findings],
    )
    prompt += (
        "\n\n"
        + _format_memory_for_prompt(state.get("goal_memory_context"))
        + "\n\nPreserve memory-driven personalization across this revision."
    )

    llm = get_gemini()
    response = llm.with_structured_output(MilestoneResponse).invoke(prompt)

    revised_milestones = []
    for i, simple in enumerate(response.milestones, start=1):
        revised_milestones.append(
            MilestoneItem(
                roadmap_uuid=roadmap_uuid,
                milestone_id=str(uuid4()),
                title=simple.title,
                description=simple.description,
                objective=simple.objective,
                estimated_hours=simple.estimated_hours,
                order_index=i,
                dependency_titles=simple.dependencies,
                status="revised",
                need_modification=False,
                revision_reason=None,
            )
        )

    return {
        "milestones": revised_milestones,
        "milestone_revision_count": revision_count + 1,
    }


def skillpath_worker(state: PlannerState):
    # PURE SYNC: no asyncio.run here. Memory was already retrieved + reranked in the
    # pre-fan-out node (retrieve_and_rerank_milestones); the rerank-filtered context
    # for this milestone arrives in the Send payload as `milestone_prompt_context`.
    # Keeping this worker sync avoids running an event loop in the fan-out thread,
    # which previously left a loop-bound Google client and deadlocked get_gemini().
    milestone = state.get("milestone")
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")

    if not milestone or not goal_spec or not learning_profile:
        return {}

    prompt_context = state.get("milestone_prompt_context")

    prompt = SKILLPATH_PROMPT.format(
        goal_title=goal_spec.title,
        goal_outcome=goal_spec.target_outcome,
        goal_constraints=goal_spec.constraints,
        learning_baseline_level=learning_profile.baseline_level,
        learning_prior_knowledges=learning_profile.prior_knowledges,
        learning_weak_areas=learning_profile.weak_areas,
        learning_pace_preference=learning_profile.pace_preference,
        milestone_title=milestone.title,
        milestone_description=milestone.description,
        milestone_objective=milestone.objective,
        milestone_estimated_hours=milestone.estimated_hours,
    )
    prompt += "\n\n" + _format_memory_for_prompt(prompt_context)

    llm = get_gemini()
    response = llm.with_structured_output(SkillPathResponse).invoke(prompt)

    drafts = []
    for simple in response.skillpaths:
        drafts.append(
            {
                "milestone_id": milestone.milestone_id,
                "title": simple.title,
                "description": simple.description,
                "estimated_hours": simple.estimated_hours,
                "learning_objectives": simple.learning_objectives,
                "depends_on_titles": simple.depends_on_titles,
            }
        )

    return {"skillpath_drafts": drafts}


def finalize_skillpath(state: PlannerState):
    drafts = state.get("skillpath_drafts", [])
    if not drafts:
        return {}

    skillpaths = finalize_skillpaths(drafts)
    roadmap_uuid = state.get("roadmap_uuid")
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")
    milestones = state.get("milestones", [])

    if not roadmap_uuid or not goal_spec or not learning_profile:
        return {"skillpaths": skillpaths}

    assumptions = [
        f"Planner considered stated constraints: {', '.join(goal_spec.constraints)}.",
        f"Planner considered baseline level: {learning_profile.baseline_level}.",
        f"Planner considered stated weak areas: {', '.join(learning_profile.weak_areas)}.",
        f"Planner used preferred pace: {learning_profile.pace_preference}.",
    ]
    roadmap = RoadmapItem(
        roadmap_id=roadmap_uuid,
        title=goal_spec.title,
        version=1,
        summary=(
            f"A personalized roadmap for {goal_spec.title} with "
            f"{len(milestones)} milestones and {len(skillpaths)} skill paths."
        ),
        target_outcome=goal_spec.target_outcome,
        assumptions=assumptions,
    )

    return {"skillpaths": skillpaths, "roadmap": roadmap}
