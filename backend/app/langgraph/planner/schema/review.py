import operator
from typing import Annotated, Literal

from app.schema.entities import SkillPathItem
from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    level: Literal["minor", "major"]
    target_type: Literal["milestone", "skillpath"]
    target_id: str
    issue_type: str
    reason: str
    suggested_action: str


class QuickReviewResponse(BaseModel):
    proceed: bool = Field(
        ...,
        description="Whether the milestone roadmap is structurally sound enough to proceed to skillpath generation.",
    )
    summary: str = Field(
        ..., description="Brief overall judgment of the milestone roadmap."
    )
    findings: list[ReviewFinding] = Field(
        default_factory=list,
        description="Major milestone-level issues that should be revised before generating skillpaths.",
    )


class SkillPathEvaluateResponse(BaseModel):
    proceed: bool = Field(
        ...,
        description="Whether the current SkillPath is good enough to continue to the next stage.",
    )
    summary: str = Field(..., description="Brief overall judgment of the review.")
    milestone_id: str = Field(
        ..., description="The parent milestone this skill path belongs to."
    )
    findings: Annotated[list[ReviewFinding], operator.add] = Field(
        default_factory=list,
        description="Structured findings about meaningful issues in the skill path set.",
    )


class SkillPathRevisionResponse(BaseModel):
    milestone_id: str
    summary: str
    skillpaths: list[SkillPathItem]
