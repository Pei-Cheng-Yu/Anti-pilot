from app.langgraph.llm.gemini import get_gemini
from app.langgraph.planner.graphs.utils import to_dict, to_dict_list
from app.langgraph.planner.policy_prompt.skillpath import (
    SHARED_SKILLPATH_POLICY,
    SHARED_SKILLPATH_POLICY_CORE,
)
from app.langgraph.planner.schema.entities import (
    SkillPathEvaluateResponse,
    SkillPathRevisionResponse,
)
from app.langgraph.planner.schema.state import PlannerState
from langgraph.types import Overwrite, Send

from .prompt import SKILLPATH_REVISE_PROMPT, SKILLPATHS_EVALUATE_PROMPT
from .utils import format_skillpaths, wrap_skillpaths_with_milestones

# TODO: discussion about valuate_milestone:
# do we still need it, since quick_review one done a densent job already


def distribute_skillpath_review(state: PlannerState):
    milestones = state.get("milestones", [])
    skillpaths = state.get("skillpaths", [])
    if not milestones or not skillpaths:
        return {}

    bundles = wrap_skillpaths_with_milestones(
        milestones=milestones,
        skillpaths=skillpaths,
    )

    tasks = []
    for bundle in bundles:
        milestone = bundle.milestone
        bundle_skillpaths = bundle.skillpaths

        tasks.append(
            Send(
                "skillpath_review_worker",
                {
                    "goal_spec": to_dict(state.get("goal_spec")),
                    "learning_profile": to_dict(state.get("learning_profile")),
                    "milestone": to_dict(milestone),
                    "skillpaths": to_dict_list(bundle_skillpaths),
                },
            )
        )
    return tasks


def skillpath_review_worker(state: PlannerState):
    milestone = state["milestone"]
    goal_spec = state.get("goal_spec", {})
    learning_profile = state.get("learning_profile", {})
    skillpaths = state.get("skillpaths", [])

    skill_paths_text = format_skillpaths(skillpaths)

    prompt = SKILLPATHS_EVALUATE_PROMPT.format(
        goal_title=goal_spec.get("title", ""),
        goal_description=goal_spec.get("description", ""),
        target_outcome=goal_spec.get("target_outcome", ""),
        constraints=goal_spec.get("constraints", []),
        learning_baseline_level=learning_profile.get("baseline_level", ""),
        learning_prior_knowledges=learning_profile.get("prior_knowledges", []),
        learning_weak_areas=learning_profile.get("weak_areas", []),
        learning_pace_preference=learning_profile.get("pace_preference", "medium"),
        milestone_id=milestone.get("milestone_id", ""),
        milestone_title=milestone.get("title", ""),
        milestone_description=milestone.get("description", ""),
        milestone_objective=milestone.get("objective", ""),
        milestone_estimated_hours=milestone.get("estimated_hours", ""),
        skill_paths=skill_paths_text,
        skillpath_policy=SHARED_SKILLPATH_POLICY,
    )

    llm = get_gemini()
    response = llm.with_structured_output(SkillPathEvaluateResponse).invoke(prompt)
    return {"skillpaths_review": [response]}


def reviewed_fan_in(state: PlannerState):
    # we overwrite with empty [] make sure it clean (since might loop again here)
    # when review-> revise -> review_2 -> revise_2
    return {"skillpath_revisions": Overwrite([])}


def distribute_skillpath_revise(state: PlannerState):
    milestones = state.get("milestones", [])
    skillpaths = state.get("skillpaths", [])
    reviews = state.get("skillpaths_review", [])

    if not milestones or not skillpaths or not reviews:
        return "__end__"

    # state 內部仍是 model
    milestone_map = {ms.milestone_id: ms for ms in milestones}

    skillpaths_by_milestone = {}
    for sp in skillpaths:
        skillpaths_by_milestone.setdefault(sp.milestone_id, []).append(sp)

    tasks = []
    for review in reviews:
        review_data = to_dict(review)

        if review_data.get("proceed", False) and not review_data.get("findings", []):
            continue

        milestone_id = review_data.get("milestone_id")
        milestone = milestone_map.get(milestone_id)
        milestone_skillpaths = skillpaths_by_milestone.get(milestone_id, [])

        if not milestone or not milestone_skillpaths:
            continue

        tasks.append(
            Send(
                "skillpath_revise_worker",
                {
                    "goal_spec": to_dict(state.get("goal_spec")),
                    "learning_profile": to_dict(state.get("learning_profile")),
                    "milestone": to_dict(milestone),
                    "skillpaths": to_dict_list(milestone_skillpaths),
                    "skillpath_review": review_data,
                },
            )
        )

    if not tasks:
        return "merge_revised_skillpaths"
    return tasks


def skillpath_revise_worker(state: PlannerState):
    milestone = state.get("milestone", {})
    review = state.get("skillpath_review", {})
    skillpaths = state.get("skillpaths", [])
    goal_spec = state.get("goal_spec", {})
    learning_profile = state.get("learning_profile", {})

    prompt = SKILLPATH_REVISE_PROMPT.format(
        goal_title=goal_spec.get("title", ""),
        goal_description=goal_spec.get("description", ""),
        target_outcome=goal_spec.get("target_outcome", ""),
        goal_constraints=goal_spec.get("constraints", []),
        learning_baseline_level=learning_profile.get("baseline_level", ""),
        learning_prior_knowledges=learning_profile.get("prior_knowledges", []),
        learning_weak_areas=learning_profile.get("weak_areas", []),
        learning_pace_preference=learning_profile.get("pace_preference", "balanced"),
        milestone_id=milestone.get("milestone_id", ""),
        milestone_title=milestone.get("title", ""),
        milestone_description=milestone.get("description", ""),
        milestone_objective=milestone.get("objective", ""),
        milestone_estimated_hours=milestone.get("estimated_hours", 0),
        current_skillpaths=format_skillpaths(skillpaths),
        review_summary=review.get("summary", ""),
        review_findings=str(review.get("findings", [])),
        shared_skillpath_policy_core=SHARED_SKILLPATH_POLICY_CORE,
    )

    llm = get_gemini()
    response = llm.with_structured_output(SkillPathRevisionResponse).invoke(prompt)

    return {"skillpath_revisions": [response]}


def revised_fan_in(state: PlannerState):
    # we overwrite with empty [] make sure it clean (since might loop again here)
    # when review-> revise -> review_2 -> revise_2
    return {"skillpaths_review": Overwrite([])}


def distribute_revised_review(state: PlannerState):
    skillpath_revisions = state.get("skillpath_revisions", [])
    milestones = state.get("milestones", [])

    if not skillpath_revisions or not milestones:
        return "__end__"

    # state 內部 milestones 仍是 model
    milestone_map = {ms.milestone_id: ms for ms in milestones}

    tasks = []
    for skillpath_revision in skillpath_revisions:
        skillpath_revision_data = to_dict(skillpath_revision)

        milestone_id = skillpath_revision_data.get("milestone_id")
        milestone = milestone_map.get(milestone_id)
        revised_skillpaths = skillpath_revision_data.get("skillpaths", [])

        if not milestone:
            continue

        tasks.append(
            Send(
                "skillpath_review_worker",
                {
                    "goal_spec": to_dict(state.get("goal_spec")),
                    "learning_profile": to_dict(state.get("learning_profile")),
                    "milestone": to_dict(milestone),
                    "skillpaths": to_dict_list(revised_skillpaths),
                },
            )
        )

    return tasks


def merge_revised_skillpaths(state: PlannerState):
    original_skillpaths = state.get("skillpaths", [])
    revisions = state.get("skillpath_revisions", [])

    if not revisions:
        return {}

    # revisions 是 model
    revised_milestone_ids = {rev.milestone_id for rev in revisions}

    unchanged = [
        sp for sp in original_skillpaths if sp.milestone_id not in revised_milestone_ids
    ]

    merged = unchanged[:]
    for rev in revisions:
        merged.extend(rev.skillpaths)

    return {"skillpaths": merged}
