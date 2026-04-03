import operator
from datetime import date
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field


class GoalSpec(BaseModel):
    title: str = Field(..., description="Short title of the user's learning goal")
    description: str = Field(
        ..., description="Detailed description of what the user wants to learn"
    )
    target_outcome: str = Field(
        ...,
        description="Expected outcome or capability the user should have after learning",
    )
    deadline: date = Field(..., description="Target deadline for achieving the goal")
    criteria: list[str] = Field(
        ...,
        description="Conditions or indicators used to judge whether the goal is successfully completed",
    )
    constraints: list[str] = Field(
        ...,
        description="Limitations or constraints affecting the learning plan, such as time, tools, background, or schedule",
    )


class LearningProfile(BaseModel):
    baseline_level: Literal["beginner", "intermediate", "advanced"] = Field(
        ..., description="The user's current overall level related to this goal"
    )
    prior_knowledges: list[str] = Field(
        ...,
        description="Knowledge, skills, or experiences the user already has that are relevant to the goal",
    )
    weak_areas: list[str] = Field(
        ...,
        description="Topics or skills the user currently struggles with or lacks confidence in",
    )
    pace_preference: Literal["slow", "balanced", "intensive"] = Field(
        ..., description="Preferred learning speed or workload intensity"
    )
    confidence_level: Literal["low", "medium", "high"] = Field(
        ...,
        description="How confident the user currently feels about learning or achieving this goal",
    )
    needs_recap: bool = Field(
        ...,
        description="Whether the user benefits from frequent review and recap of previous material",
    )
    prefers_examples_first: bool = Field(
        ...,
        description="Whether the user learns better by seeing examples before theory or explanation",
    )
    overload_risk: Literal["low", "medium", "high"] = Field(
        ...,
        description="Estimated risk that the user may feel overwhelmed given the goal difficulty, pace, and available capacity",
    )


class SkillPathItem(BaseModel):
    roadmap_id: str = Field(
        ..., description="The parent roadmap this skill path belongs to."
    )
    skillpath_id: str = Field(
        ..., description="Unique identifier for this skill path unit."
    )
    milestone_id: str = Field(
        ..., description="The parent milestone this skill path belongs to."
    )
    title: str = Field(
        ...,
        description="Short title of the skill path, such as 'HTTP Basics' or 'FastAPI Routing'.",
    )
    description: str = Field(
        ...,
        description="A concise explanation of what this skill path covers and why it matters in the learning roadmap.",
    )
    estimated_hours: float = Field(
        ..., description="Estimated number of hours needed to complete this skill path."
    )
    prerequisite_skillpath_ids: list[str] = Field(
        default_factory=list,
        description="List of prerequisite skill path IDs that should be learned before starting this one.",
    )
    learning_objectives: list[str] = Field(
        default_factory=list,
        description="Specific learning outcomes the user should achieve after completing this skill path.",
    )

    status: Literal["ready", "generated", "revising", "completed", "revised"] = Field(
        ...,
        description="Current status of the skill path, such as ready, generated, revising, or completed.",
    )
    need_generation: bool = Field(
        default=False,
        description="Whether this skill path still needs its detailed content, tasks, or resources to be generated.",
    )
    need_modification: bool = Field(
        default=False,
        description="Whether this skill path has been marked for revision or modification.",
    )
    revision_reason: Optional[str] = Field(
        default=None,
        description="Reason why this skill path needs revision, such as pace too fast, missing prerequisite, or user feedback.",
    )
    affected_downstream_ids: list[str] = Field(
        default_factory=list,
        description="IDs of downstream skill paths that may also be affected if this skill path is revised.",
    )


class MilestoneItem(BaseModel):
    roadmap_id: str = Field(
        ..., description="The parent roadmap this milestone belongs to."
    )
    milestone_id: str = Field(..., description="Unique identifier for this milestone.")
    title: str = Field(..., description="Short title of the milestone.")
    description: str = Field(
        ..., description="Explanation of what this milestone covers."
    )
    objective: str = Field(
        ..., description="Concrete learning objective of this milestone."
    )
    estimated_hours: float = Field(..., description="Estimated hours needed.")
    order_index: int = Field(..., description="Order of this milestone in the roadmap.")
    dependency_titles: list[str] = Field(
        default_factory=list,
        description="Titles of prerequisite milestones generated in the same roadmap.",
    )
    prerequisite_milestone_ids: list[str] = Field(
        default_factory=list,
        description="IDs of milestones that should be completed before this one.",
    )

    status: Literal["ready", "generated", "revising", "completed", "revised"] = Field(
        default="ready", description="Current status of the milestone."
    )
    need_modification: bool = Field(
        default=False,
        description="Whether this milestone has been marked for revision.",
    )
    revision_reason: Optional[str] = Field(
        default=None, description="Reason why this milestone needs revision."
    )


class RoadmapItem(BaseModel):
    roadmap_id: str
    title: str = Field(..., description="Short title of the roadmap")
    version: int = Field(
        ...,
        description="Version number of the roadmap. Increment this when the roadmap is revised.",
    )
    summary: str = Field(
        ...,
        description="High-level summary of the roadmap, describing the overall learning journey.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Key assumptions used when generating this roadmap, such as weekly study time or prior knowledge.",
    )
    target_outcome: str


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
