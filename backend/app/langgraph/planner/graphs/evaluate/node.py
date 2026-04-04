from app.langgraph.llm.gemini import get_gemini
from app.langgraph.planner.graphs.utils import to_dict, to_dict_list
from app.langgraph.planner.policy_prompt.skillpath import SHARED_SKILLPATH_POLICY
from app.langgraph.planner.schema.review import SkillPathRevisionResponse
from app.langgraph.planner.schema.state import PlannerState
from langgraph.types import Send

from .prompt import SKILLPATHS_EVALUATE_PROMPT
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
    response = llm.with_structured_output(SkillPathRevisionResponse).invoke(prompt)
    return {"skillpath_revision": [response]}


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
