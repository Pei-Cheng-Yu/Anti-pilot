from app.schema.entities import (
    ContentGenerationPlan,
    GoalSpec,
    LearningMemoryContext,
    LearningProfile,
    MemoryRerankResult,
    MilestoneItem,
    SkillPathItem,
)
from pydantic import BaseModel, Field, model_validator


class AdkContentGenerationRequest(BaseModel):
    goal: GoalSpec = Field(
        ..., description="The learner goal that this content should support."
    )
    profile: LearningProfile = Field(
        ..., description="Learner profile used to adapt tone, depth, and pacing."
    )
    milestone: MilestoneItem = Field(
        ..., description="Milestone context for the skill path being generated."
    )
    skillpath: SkillPathItem = Field(
        ..., description="The exact skill path that needs learning content."
    )
    content_plan: ContentGenerationPlan = Field(
        ...,
        description="Run-level content-generation policy derived before worker fanout.",
    )
    learning_memory_context: LearningMemoryContext | None = Field(
        default=None,
        description="Optional learner memory context used to personalize content.",
    )
    memory_rerank_result: MemoryRerankResult | None = Field(
        default=None,
        description=(
            "Optional advisory selected memories and teaching guidance for this "
            "content-generation request."
        ),
    )


class AdkSourceLink(BaseModel):
    title: str = Field(..., description="Human-readable source title.")
    url: str = Field(..., description="Source URL used for grounding.")


class AdkSourceNote(BaseModel):
    source: AdkSourceLink = Field(
        ..., description="The source this note was derived from."
    )
    note: str = Field(
        ...,
        description="Short note describing what information from the source was used in the article.",
    )


class AdkArticleOutput(BaseModel):
    title: str = Field(..., description="Article title shown to the learner.")
    description: str = Field(
        ...,
        description="Brief explanation of what the article covers and why it matters.",
    )
    skill_intro: str = Field(
        ...,
        description="Short framing intro that explains why this skill matters in the roadmap.",
    )
    reading_content: str = Field(
        ...,
        description="The actual teaching article content for this skill path.",
    )
    references: list[AdkSourceLink] = Field(
        default_factory=list,
        description="Grounding references used to support the article.",
    )
    source_notes: list[AdkSourceNote] = Field(
        default_factory=list,
        description="Short notes explaining how the references informed the article.",
    )


class AdkCodingProblemOutput(BaseModel):
    title: str = Field(..., description="Coding problem title.")
    description: str = Field(
        ...,
        description="Short learner-facing description of what the coding task practices.",
    )
    prompt: str = Field(
        ...,
        description="Full coding problem prompt.",
    )
    difficulty: str = Field(
        ...,
        description="Relative difficulty such as easy, medium, or hard.",
    )
    starter_code: str | None = Field(
        default=None,
        description="Optional starter code provided to the learner.",
    )
    expected_output: str | None = Field(
        default=None,
        description="Optional expected output or target behavior.",
    )
    hints: list[str] = Field(
        default_factory=list,
        description="Optional hints to help the learner if stuck.",
    )


class AdkMultipleChoiceOptionOutput(BaseModel):
    option_id: str = Field(..., description="Stable option identifier such as A or B.")
    text: str = Field(..., description="Text shown for this option.")


class AdkMultipleChoiceOutput(BaseModel):
    title: str = Field(..., description="Multiple-choice item title.")
    description: str = Field(
        ...,
        description="Brief learner-facing description of the concept check.",
    )
    question: str = Field(..., description="The multiple-choice question text.")
    options: list[AdkMultipleChoiceOptionOutput] = Field(
        default_factory=list,
        description="Available answer choices.",
    )
    correct_option_id: str = Field(
        ...,
        description="Option identifier for the correct answer.",
    )
    explanation: str = Field(
        ...,
        description="Short explanation of why the correct answer is right.",
    )


class AdkContentGenerationOutput(BaseModel):
    article: AdkArticleOutput = Field(
        ..., description="Generated article content for the skill path."
    )
    coding_problem: AdkCodingProblemOutput | None = Field(
        default=None,
        description="Optional generated coding problem.",
    )
    multiple_choice: AdkMultipleChoiceOutput | None = Field(
        default=None,
        description="Optional generated multiple-choice check.",
    )

    @model_validator(mode="after")
    def validate_assessment_shape(self):
        provided = int(self.coding_problem is not None) + int(
            self.multiple_choice is not None
        )
        if provided < 1:
            raise ValueError(
                "At least one of coding_problem or multiple_choice must be present."
            )
        return self
