import asyncio

from app.adk_agents.content_generator import generate_skillpath_content
from app.adk_agents.content_generator.schemas import (
    AdkContentGenerationOutput,
    AdkContentGenerationRequest,
)
from app.db.session import get_session
from app.langgraph.content_generation.graphs.generate_learning_content.utils import (
    apply_content_drafts,
)
from app.langgraph.content_generation.schema.state import (
    ContentGenerationState,
    LearningMemoryRerankDiagnostic,
    LearningMemoryRetrievalDiagnostic,
)
from app.schema.entities import (
    ContentGenerationPlan,
    LearnerMemoryNote,
    LearningMemoryContext,
    MemoryRerankRequest,
    MemoryRerankResult,
    MilestoneItem,
    RetrieveLearningMemoryInput,
    SkillPathItem,
)
from app.schema.enums import ExampleStyle, MemoryRerankPurpose, PracticeMode
from app.services import memory_service
from langgraph.graph import END
from langgraph.types import Send


def build_content_plan(state: ContentGenerationState):
    existing_plan = state.get("content_plan")
    if existing_plan is not None:
        return {"content_plan": existing_plan}

    learning_profile = state.get("learning_profile")
    if not learning_profile:
        return {}

    if learning_profile.prefers_examples_first:
        example_style = ExampleStyle.EXAMPLE_FIRST
    else:
        example_style = ExampleStyle.BALANCED

    return {
        "content_plan": ContentGenerationPlan(
            article_depth=None,
            example_style=example_style,
            include_recap=learning_profile.needs_recap,
        )
    }


def route_content_workers(state: ContentGenerationState):
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")
    milestones = state.get("milestones", [])
    skillpaths = state.get("skillpaths", [])

    if not goal_spec or not learning_profile or not milestones or not skillpaths:
        return END

    milestones_by_id = {milestone.milestone_id: milestone for milestone in milestones}
    skillpaths_by_milestone: dict[str, list[SkillPathItem]] = {}
    for skillpath in skillpaths:
        if not skillpath.need_generation:
            continue
        skillpaths_by_milestone.setdefault(skillpath.milestone_id, []).append(skillpath)

    tasks = []
    for milestone_id, milestone_skillpaths in skillpaths_by_milestone.items():
        explicit_coding_exists = any(
            skillpath.practice_mode == PracticeMode.CODING_PROBLEM
            for skillpath in milestone_skillpaths
        )
        fallback_coding_skillpath_id = (
            None if explicit_coding_exists else milestone_skillpaths[-1].skillpath_id
        )
        milestone = milestones_by_id.get(milestone_id)
        if not milestone:
            continue

        for skillpath in milestone_skillpaths:
            selected_practice_mode = skillpath.practice_mode
            if not selected_practice_mode and (
                skillpath.skillpath_id == fallback_coding_skillpath_id
            ):
                selected_practice_mode = PracticeMode.CODING_PROBLEM
            elif not selected_practice_mode:
                selected_practice_mode = PracticeMode.EITHER

            tasks.append(
                Send(
                    "content_worker",
                    {
                        "goal_spec": goal_spec,
                        "user_id": state.get("user_id"),
                        "learning_profile": learning_profile,
                        "milestone": milestone,
                        "skillpath": skillpath,
                        "content_plan": state.get("content_plan"),
                        "require_coding_problem": selected_practice_mode
                        == PracticeMode.CODING_PROBLEM,
                        "selected_practice_mode": selected_practice_mode,
                    },
                )
            )

    return tasks or END


def _retrieve_learning_memory_context(
    *,
    user_id: str | None,
    skillpath: SkillPathItem,
) -> LearningMemoryContext | None:
    if not user_id:
        return None

    async def _retrieve() -> LearningMemoryContext:
        async with get_session() as session:
            return await memory_service.retrieve_learning_memory(
                RetrieveLearningMemoryInput(
                    user_id=user_id,
                    query_text="\n".join(
                        [
                            skillpath.title,
                            skillpath.description,
                            " ".join(skillpath.learning_objectives),
                        ]
                    ),
                    skillpath_id=skillpath.skillpath_id,
                    concept_keys=skillpath.learning_objectives,
                ),
                session,
            )

    return asyncio.run(_retrieve())


def _candidate_memories_from_context(
    context: LearningMemoryContext | None,
) -> list[LearnerMemoryNote]:
    if context is None:
        return []

    candidates: list[LearnerMemoryNote] = []
    seen: set[str] = set()
    for group in (
        context.relevant_notes,
        context.active_error_patterns,
        context.teaching_heuristics,
        context.mastery_signals,
        context.background_notes,
    ):
        for note in group:
            if note.memory_id in seen:
                continue
            seen.add(note.memory_id)
            candidates.append(note)
    return candidates


def _rerank_learning_memory_for_content(
    *,
    skillpath: SkillPathItem,
    context: LearningMemoryContext | None,
) -> tuple[MemoryRerankResult | None, LearningMemoryRerankDiagnostic]:
    candidates = _candidate_memories_from_context(context)
    if not candidates:
        return None, LearningMemoryRerankDiagnostic(
            skillpath_id=skillpath.skillpath_id,
            status="skipped_no_memory",
            candidate_memory_count=0,
        )

    try:
        rerank_result = asyncio.run(
            memory_service.rerank_memories(
                MemoryRerankRequest(
                    purpose=MemoryRerankPurpose.CONTENT_GENERATION,
                    task_context="\n".join(
                        [
                            skillpath.title,
                            skillpath.description,
                            " ".join(skillpath.learning_objectives),
                        ]
                    ),
                    learner_context=(
                        context.mastery_state.model_dump_json()
                        if context and context.mastery_state
                        else ""
                    ),
                    recent_attempts=context.recent_attempts if context else [],
                    candidate_memories=candidates,
                    max_selected=3,
                )
            )
        )
    except Exception as exc:
        return None, LearningMemoryRerankDiagnostic(
            skillpath_id=skillpath.skillpath_id,
            status="failed",
            candidate_memory_count=len(candidates),
            error_summary=f"{type(exc).__name__}: {exc}",
        )

    return rerank_result, LearningMemoryRerankDiagnostic(
        skillpath_id=skillpath.skillpath_id,
        status="reranked",
        candidate_memory_count=len(candidates),
        selected_memory_ids=rerank_result.selected_memory_ids,
        teaching_action=rerank_result.teaching_action.value,
        focused_concepts=rerank_result.focused_concepts,
        guidance_present=bool(rerank_result.guidance),
    )


def _build_learning_memory_retrieval_diagnostic(
    *,
    user_id: str | None,
    skillpath_id: str,
    context: LearningMemoryContext | None = None,
    error: Exception | None = None,
) -> LearningMemoryRetrievalDiagnostic:
    if error is not None:
        return LearningMemoryRetrievalDiagnostic(
            skillpath_id=skillpath_id,
            status="failed",
            user_id_present=bool(user_id),
            error_summary=f"{type(error).__name__}: {error}",
        )

    if not user_id:
        return LearningMemoryRetrievalDiagnostic(
            skillpath_id=skillpath_id,
            status="skipped_no_user_id",
            user_id_present=False,
        )

    if context is None:
        return LearningMemoryRetrievalDiagnostic(
            skillpath_id=skillpath_id,
            status="retrieved_empty",
            user_id_present=True,
        )

    active_error_pattern_count = len(context.active_error_patterns)
    teaching_heuristic_count = len(context.teaching_heuristics)
    recent_attempt_count = len(context.recent_attempts)
    relevant_note_count = len(context.relevant_notes)
    has_memory = any(
        [
            context.mastery_state is not None,
            active_error_pattern_count,
            teaching_heuristic_count,
            recent_attempt_count,
            relevant_note_count,
            len(context.mastery_signals),
            len(context.background_notes),
        ]
    )

    return LearningMemoryRetrievalDiagnostic(
        skillpath_id=skillpath_id,
        status="retrieved" if has_memory else "retrieved_empty",
        user_id_present=True,
        active_error_pattern_count=active_error_pattern_count,
        teaching_heuristic_count=teaching_heuristic_count,
        recent_attempt_count=recent_attempt_count,
        relevant_note_count=relevant_note_count,
    )


def content_worker(state: ContentGenerationState):
    user_id = state.get("user_id")
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")
    milestone: MilestoneItem | None = state.get("milestone")
    skillpath: SkillPathItem | None = state.get("skillpath")
    content_plan: ContentGenerationPlan | None = state.get("content_plan")
    selected_practice_mode = state.get("selected_practice_mode") or (
        PracticeMode.CODING_PROBLEM
        if state.get("require_coding_problem", False)
        else PracticeMode.EITHER
    )

    if (
        not goal_spec
        or not learning_profile
        or not milestone
        or not skillpath
        or not content_plan
    ):
        return {}

    retrieval_error: Exception | None = None
    try:
        learning_memory_context = _retrieve_learning_memory_context(
            user_id=user_id,
            skillpath=skillpath,
        )
    except Exception as exc:
        learning_memory_context = None
        retrieval_error = exc

    memory_diagnostic = _build_learning_memory_retrieval_diagnostic(
        user_id=user_id,
        skillpath_id=skillpath.skillpath_id,
        context=learning_memory_context,
        error=retrieval_error,
    )
    memory_rerank_result, memory_rerank_diagnostic = (
        _rerank_learning_memory_for_content(
            skillpath=skillpath,
            context=learning_memory_context,
        )
    )

    request = AdkContentGenerationRequest(
        goal=goal_spec,
        profile=learning_profile,
        milestone=milestone,
        skillpath=skillpath.model_copy(
            update={"practice_mode": selected_practice_mode}
        ),
        content_plan=content_plan,
        learning_memory_context=learning_memory_context,
        memory_rerank_result=memory_rerank_result,
    )
    response: AdkContentGenerationOutput = generate_skillpath_content(request)

    update = {
        "learning_memory_retrieval_diagnostics_by_skillpath": {
            skillpath.skillpath_id: memory_diagnostic
        },
        "learning_memory_rerank_diagnostics_by_skillpath": {
            skillpath.skillpath_id: memory_rerank_diagnostic
        },
        "content_drafts": [
            {
                "skillpath_id": skillpath.skillpath_id,
                "article": response.article.model_dump(),
                "coding_problem": (
                    response.coding_problem.model_dump()
                    if response.coding_problem
                    else None
                ),
                "multiple_choice": (
                    response.multiple_choice.model_dump()
                    if response.multiple_choice
                    else None
                ),
            }
        ],
    }
    if learning_memory_context is not None:
        update["learning_memory_contexts_by_skillpath"] = {
            skillpath.skillpath_id: learning_memory_context
        }
    if memory_rerank_result is not None:
        update["learning_memory_rerank_results_by_skillpath"] = {
            skillpath.skillpath_id: memory_rerank_result
        }

    return update


def finalize_generated_content(state: ContentGenerationState):
    skillpaths = state.get("skillpaths", [])
    content_drafts = state.get("content_drafts", [])
    if not skillpaths or not content_drafts:
        return {}

    return {"generated_skillpaths": apply_content_drafts(skillpaths, content_drafts)}
