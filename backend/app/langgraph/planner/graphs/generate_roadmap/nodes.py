from uuid import uuid4

from app.langgraph.llm.gemini import get_gemini
from app.langgraph.planner.policy_prompt.milestone import (
    SHARED_MILESTONE_POLICY,
    SHARED_MILESTONE_POLICY_CORE,
)
from app.langgraph.planner.schema.entities import MilestoneItem, QuickReviewResponse
from app.langgraph.planner.schema.state import PlannerState
from langgraph.types import Send
from pydantic import BaseModel, Field

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

    llm = get_gemini()
    response = llm.with_structured_output(QuickReviewResponse).invoke(prompt)
    return {"milestone_quick_review": response}


def route_after_milestone_quick_review(state: PlannerState):
    review = state.get("milestone_quick_review")

    if review and review.proceed:
        milestones = state.get("milestones", [])
        if not milestones:
            return []

        tasks = []
        for milestone in milestones:
            tasks.append(
                Send(
                    "skillpath_worker",
                    {
                        "roadmap_uuid": state["roadmap_uuid"],
                        "goal_spec": state.get("goal_spec"),
                        "learning_profile": state.get("learning_profile"),
                        "milestone": milestone,
                    },
                )
            )
        return tasks

    return "revise_milestones"


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
    milestone = state.get("milestone")
    goal_spec = state.get("goal_spec")
    learning_profile = state.get("learning_profile")

    if not milestone or not goal_spec or not learning_profile:
        return {}

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
    return {"skillpaths": skillpaths}
