import operator
from typing import Annotated, Optional

from app.langgraph.planner.schema.review import (
    QuickReviewResponse,
    SkillPathRevisionResponse,
)
from app.schema.entities import (
    GoalSpec,
    LearningMemoryContext,
    LearningProfile,
    MilestoneItem,
    RoadmapItem,
    SkillPathItem,
)
from typing_extensions import TypedDict


def _merge_contexts(
    left: dict[str, LearningMemoryContext] | None,
    right: dict[str, LearningMemoryContext] | None,
) -> dict[str, LearningMemoryContext]:
    """Reducer merging per-milestone memory contexts from parallel skillpath workers.

    ``operator.add`` cannot merge dicts, so concurrent ``{milestone_id: context}``
    writes are merged here. On key collision the right (newer) value wins.
    """
    return {**(left or {}), **(right or {})}


class PlannerState(TypedDict):
    goal_spec: Optional[GoalSpec]
    learning_profile: Optional[LearningProfile]
    user_id: str
    roadmap_uuid: str
    roadmap: RoadmapItem
    milestones: list[MilestoneItem]
    milestone_quick_review: Optional[QuickReviewResponse]
    milestone_revision_count: int
    skillpath_drafts: Annotated[list[dict], operator.add]
    skillpaths: list[SkillPathItem]
    skillpath_revisions: Annotated[list[SkillPathRevisionResponse], operator.add]
    goal_memory_context: Optional[LearningMemoryContext]
    # Written once by retrieve_and_rerank_milestones (pre-fan-out), so a plain dict
    # is sufficient. Kept reducer-merged for safety if multiple writers ever appear.
    milestone_memory_contexts: Annotated[
        dict[str, LearningMemoryContext], _merge_contexts
    ]
    # milestone_id -> rerank-selected note ids (subset to inject into that milestone)
    milestone_selected_ids: Annotated[dict[str, list[str]], _merge_contexts]
    # Per-worker Send payload: the filtered context that worker should inject.
    milestone_prompt_context: Optional[LearningMemoryContext]
