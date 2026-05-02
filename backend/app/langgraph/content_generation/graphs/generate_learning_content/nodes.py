from app.adk_agents.content_generator import generate_skillpath_content
from app.adk_agents.content_generator.schemas import (
    AdkContentGenerationOutput,
    AdkContentGenerationRequest,
)
from app.langgraph.content_generation.graphs.generate_learning_content.utils import (
    apply_content_drafts,
)
from app.langgraph.content_generation.schema.state import ContentGenerationState
from app.schema.entities import ContentGenerationPlan, MilestoneItem, SkillPathItem
from app.schema.enums import ExampleStyle, PracticeMode
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


def content_worker(state: ContentGenerationState):
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

    request = AdkContentGenerationRequest(
        goal=goal_spec,
        profile=learning_profile,
        milestone=milestone,
        skillpath=skillpath.model_copy(
            update={"practice_mode": selected_practice_mode}
        ),
        content_plan=content_plan,
    )
    response: AdkContentGenerationOutput = generate_skillpath_content(request)

    return {
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
        ]
    }


def finalize_generated_content(state: ContentGenerationState):
    skillpaths = state.get("skillpaths", [])
    content_drafts = state.get("content_drafts", [])
    if not skillpaths or not content_drafts:
        return {}

    return {"generated_skillpaths": apply_content_drafts(skillpaths, content_drafts)}
