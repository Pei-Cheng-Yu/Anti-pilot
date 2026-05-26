from datetime import date
from typing import Annotated, Literal, Optional

from app.schema.enums import (
    ArticleDepth,
    ExampleStyle,
    LearningContentType,
    PracticeMode,
)
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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


class SourceLink(BaseModel):
    title: str = Field(..., description="Human-readable title of the source.")
    url: str = Field(..., description="Reference URL for the source material.")


class ContentSourceNote(BaseModel):
    source: SourceLink
    note: str = Field(
        ...,
        description="Short note summarizing what was useful from this source for the generated learning content.",
    )


class MultipleChoiceOption(BaseModel):
    option_id: str = Field(..., description="Stable option identifier, such as A.")
    text: str = Field(..., description="The option text shown to the learner.")


class BaseLearningContent(BaseModel):
    content_id: str = Field(..., description="Unique identifier for this content item.")
    skillpath_id: str = Field(
        ..., description="Parent skill path that this learning content belongs to."
    )
    title: str = Field(..., description="Short title of this learning content item.")
    description: str = Field(
        ...,
        description="Brief description of why this content item exists and what it helps the learner practice or understand.",
    )


class ArticleLearningContent(BaseLearningContent):
    content_type: Literal[LearningContentType.ARTICLE] = LearningContentType.ARTICLE
    skill_intro: str = Field(
        ...,
        description="Short introduction that frames the skill for the learner before the main reading section.",
    )
    reading_content: str = Field(
        ...,
        description="Main article content that teaches the skill path concept in a concise, learner-friendly way.",
    )
    references: list[SourceLink] = Field(
        default_factory=list,
        description="Reference links used to ground or support the article.",
    )
    source_notes: list[ContentSourceNote] = Field(
        default_factory=list,
        description="Optional notes captured during source research for this article.",
    )


class CodingProblemLearningContent(BaseLearningContent):
    content_type: Literal[LearningContentType.CODING_PROBLEM] = (
        LearningContentType.CODING_PROBLEM
    )
    prompt: str = Field(
        ...,
        description="Coding challenge prompt for the learner to implement or debug.",
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        ...,
        description="Relative difficulty of the coding exercise for this learner and roadmap stage.",
    )
    starter_code: Optional[str] = Field(
        default=None,
        description="Optional starter code provided to reduce setup friction.",
    )
    expected_output: Optional[str] = Field(
        default=None,
        description="Optional target output or behavior for the coding task.",
    )
    hints: list[str] = Field(
        default_factory=list,
        description="Optional hints the learner can use if they get stuck.",
    )


class MultipleChoiceLearningContent(BaseLearningContent):
    content_type: Literal[LearningContentType.MULTIPLE_CHOICE] = (
        LearningContentType.MULTIPLE_CHOICE
    )
    question: str = Field(..., description="Multiple-choice question prompt.")
    options: list[MultipleChoiceOption] = Field(
        default_factory=list,
        description="Available answer choices for this question.",
    )
    correct_option_id: str = Field(
        ...,
        description="Identifier of the correct answer option.",
    )
    explanation: str = Field(
        ...,
        description="Short explanation of why the correct answer is right.",
    )


LearningContentItem = Annotated[
    ArticleLearningContent
    | CodingProblemLearningContent
    | MultipleChoiceLearningContent,
    Field(discriminator="content_type"),
]


class ContentGenerationPlan(BaseModel):
    article_depth: Optional[ArticleDepth] = Field(
        default=None,
        description="Optional run-level article depth override. When omitted, the content-generation agent should infer the appropriate depth from the learner profile and roadmap context.",
    )
    example_style: ExampleStyle = Field(
        ...,
        description="Whether generated articles should be minimal with examples, balanced, or explicitly example-first.",
    )
    include_recap: bool = Field(
        ...,
        description="Whether generated learning content should include recap-oriented reinforcement.",
    )


class MilestoneRecap(BaseModel):
    recap_id: str = Field(
        ..., description="Unique identifier for this milestone recap."
    )
    milestone_id: str = Field(..., description="Milestone this recap belongs to.")
    title: str = Field(..., description="Short learner-facing title for the recap.")
    summary: str = Field(
        ...,
        description="Concise recap summary that consolidates what the learner should retain before moving on.",
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Key concepts or takeaways the learner should retain.",
    )
    readiness_checks: list[str] = Field(
        default_factory=list,
        description="Short self-check prompts that help the learner judge whether they are ready for the next milestone.",
    )
    related_skillpath_ids: list[str] = Field(
        default_factory=list,
        description="Skillpaths within the milestone that this recap summarizes.",
    )


class SkillPathItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    roadmap_id: Optional[str] = Field(
        default=None,
        description="Optional parent roadmap ID kept for REST/API compatibility.",
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
    practice_mode: Optional[PracticeMode] = Field(
        default=None,
        description="Optional post-planning guidance set during roadmap review to indicate whether this skill path should use a coding problem, a multiple-choice check, or either as its main assessment mode.",
    )
    learning_contents: list[LearningContentItem] = Field(
        default_factory=list,
        description="Generated learning content items attached to this skill path, such as article, coding problem, or quiz content.",
    )


class MilestoneItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    roadmap_id: str = Field(
        ...,
        description="The parent roadmap this milestone belongs to.",
        validation_alias=AliasChoices("roadmap_id", "roadmap_uuid"),
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

    @property
    def roadmap_uuid(self) -> str:
        return self.roadmap_id


class RoadmapItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    roadmap_id: str
    title: str = Field(default="", description="Short title of the roadmap.")
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


# --- Nested read models for agent consumption ---


class MilestoneWithSkillPaths(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    milestone_id: str = Field(..., description="Unique identifier for this milestone.")
    roadmap_id: str = Field(
        ...,
        description="Parent roadmap ID.",
        validation_alias=AliasChoices("roadmap_id", "roadmap_uuid"),
    )
    title: str = Field(..., description="Short title of the milestone.")
    description: str = Field(
        ..., description="Explanation of what this milestone covers."
    )
    objective: str = Field(
        ..., description="Concrete learning objective of this milestone."
    )
    estimated_hours: float = Field(..., description="Estimated hours needed.")
    order_index: int = Field(..., description="Order of this milestone in the roadmap.")
    dependency_titles: list[str] = Field(default_factory=list)
    prerequisite_milestone_ids: list[str] = Field(default_factory=list)
    status: Literal["ready", "generated", "revising", "completed", "revised"] = Field(
        default="ready"
    )
    need_modification: bool = Field(default=False)
    revision_reason: Optional[str] = Field(default=None)
    skillpaths: list[SkillPathItem] = Field(
        default_factory=list,
        description="Skillpaths nested under this milestone, ordered by prerequisites.",
    )
    recaps: list[MilestoneRecap] = Field(
        default_factory=list,
        description="Optional recap units generated after milestone-level content is complete.",
    )

    @property
    def roadmap_uuid(self) -> str:
        return self.roadmap_id


class RoadmapFull(BaseModel):
    roadmap_id: str
    title: str = ""
    version: int
    summary: str
    target_outcome: str
    assumptions: list[str] = Field(default_factory=list)
    milestones: list[MilestoneWithSkillPaths] = Field(
        default_factory=list,
        description="All milestones with their skillpaths nested inside, ordered by order_index.",
    )
