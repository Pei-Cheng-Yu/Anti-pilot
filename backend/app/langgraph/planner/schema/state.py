import operator
from typing import Annotated, Optional

from app.langgraph.planner.schema.review import (
    QuickReviewResponse,
    SkillPathRevisionResponse,
)
from app.schema.entities import (
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    RoadmapItem,
    SkillPathItem,
)
from typing_extensions import TypedDict


class PlannerState(TypedDict):
    goal_spec: Optional[GoalSpec]
    learning_profile: Optional[LearningProfile]
    roadmap_uuid: str
    roadmap: RoadmapItem
    milestones: list[MilestoneItem]
    milestone_quick_review: Optional[QuickReviewResponse]
    milestone_revision_count: int
    skillpath_drafts: Annotated[list[dict], operator.add]
    skillpaths: list[SkillPathItem]
    skillpath_revisions: Annotated[list[SkillPathRevisionResponse], operator.add]
