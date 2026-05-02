import operator
from typing import Annotated, Optional

from app.schema.entities import (
    ContentGenerationPlan,
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    SkillPathItem,
)
from app.schema.enums import PracticeMode
from typing_extensions import TypedDict


class ContentGenerationState(TypedDict):
    goal_spec: Optional[GoalSpec]
    learning_profile: Optional[LearningProfile]
    milestones: list[MilestoneItem]
    skillpaths: list[SkillPathItem]
    milestone: Optional[MilestoneItem]
    skillpath: Optional[SkillPathItem]
    content_plan: Optional[ContentGenerationPlan]
    require_coding_problem: bool
    selected_practice_mode: Optional[PracticeMode]
    content_drafts: Annotated[list[dict], operator.add]
    generated_skillpaths: list[SkillPathItem]
