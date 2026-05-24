import operator
from typing import Annotated, Literal, Optional

from app.schema.entities import (
    ContentGenerationPlan,
    GoalSpec,
    LearningMemoryContext,
    LearningProfile,
    MilestoneItem,
    SkillPathItem,
)
from app.schema.enums import PracticeMode
from pydantic import BaseModel
from typing_extensions import TypedDict


def merge_learning_memory_contexts(
    left: dict[str, LearningMemoryContext] | None,
    right: dict[str, LearningMemoryContext] | None,
) -> dict[str, LearningMemoryContext]:
    merged: dict[str, LearningMemoryContext] = {}
    if left:
        merged.update(left)
    if right:
        merged.update(right)
    return merged


class LearningMemoryRetrievalDiagnostic(BaseModel):
    skillpath_id: str
    status: Literal[
        "skipped_no_user_id",
        "retrieved",
        "retrieved_empty",
        "failed",
    ]
    user_id_present: bool
    active_error_pattern_count: int = 0
    teaching_heuristic_count: int = 0
    recent_attempt_count: int = 0
    relevant_note_count: int = 0
    error_summary: str | None = None


def merge_learning_memory_retrieval_diagnostics(
    left: dict[str, LearningMemoryRetrievalDiagnostic] | None,
    right: dict[str, LearningMemoryRetrievalDiagnostic] | None,
) -> dict[str, LearningMemoryRetrievalDiagnostic]:
    merged: dict[str, LearningMemoryRetrievalDiagnostic] = {}
    if left:
        merged.update(left)
    if right:
        merged.update(right)
    return merged


class ContentGenerationState(TypedDict):
    user_id: Optional[str]
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
    learning_memory_contexts_by_skillpath: Annotated[
        dict[str, LearningMemoryContext],
        merge_learning_memory_contexts,
    ]
    learning_memory_retrieval_diagnostics_by_skillpath: Annotated[
        dict[str, LearningMemoryRetrievalDiagnostic],
        merge_learning_memory_retrieval_diagnostics,
    ]
    generated_skillpaths: list[SkillPathItem]
