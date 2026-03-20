import operator
from typing import Annotated, Optional

from app.langgraph.planner.schema.entities import (
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    QuickReviewResponse,
    RoadmapItem,
    SkillPathEvaluateResponse,
    SkillPathItem,
    SkillPathRevisionResponse,
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
    skillpaths_review: Annotated[list[SkillPathEvaluateResponse], operator.add]
    skillpath_revisions: Annotated[list[SkillPathRevisionResponse], operator.add]
