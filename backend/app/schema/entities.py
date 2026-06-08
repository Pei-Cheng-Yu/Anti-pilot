from datetime import date, datetime
from typing import Annotated, Any, Literal, Optional

from app.schema.enums import (
    ArticleDepth,
    AttemptCorrectness,
    ExampleStyle,
    HintLevel,
    LearningContentType,
    MasteryStatus,
    MemoryIntegrityAction,
    MemoryRerankPurpose,
    MemoryStatus,
    MemoryType,
    PracticeMode,
    TeachingAction,
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


class MilestoneCustomizationRequest(BaseModel):
    instructions: str = Field(
        default="",
        description="Learner's requested milestone customization.",
    )
    title: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    objective: Optional[str] = Field(default=None)
    estimated_hours: Optional[float] = Field(default=None)
    mark_skillpaths_for_regeneration: bool = Field(default=True)


class MilestoneCustomizationResponse(BaseModel):
    applied: bool
    message: str
    milestone: Optional[MilestoneItem] = None
    affected_skillpath_ids: list[str] = Field(default_factory=list)
    follow_up_required: bool = False


class TestCaseResult(BaseModel):
    name: str = Field(..., description="Short name or identifier for the test case.")
    passed: bool = Field(..., description="Whether the test case passed.")
    message: Optional[str] = Field(
        default=None,
        description="Optional short detail describing the observed result.",
    )


class CodingProblemAttempt(BaseModel):
    attempt_id: str = Field(..., description="Unique identifier for this attempt.")
    user_id: str = Field(..., description="Learner who submitted this attempt.")
    skillpath_id: str = Field(..., description="Skillpath tied to this attempt.")
    content_id: str = Field(..., description="Coding problem content identifier.")
    submitted_code: str = Field(..., description="Learner-submitted code.")
    language: str = Field(..., description="Programming language of the submission.")
    correctness: AttemptCorrectness = Field(
        ..., description="Overall correctness outcome for this attempt."
    )
    feedback_summary: str = Field(
        ..., description="Short summary of the feedback given for the attempt."
    )
    detected_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts the evaluator believes are relevant in this attempt.",
    )
    detected_mistakes: list[str] = Field(
        default_factory=list,
        description="Mistakes or failure patterns detected for this attempt.",
    )
    compile_error: Optional[str] = Field(
        default=None, description="Optional compiler or syntax error message."
    )
    runtime_error: Optional[str] = Field(
        default=None, description="Optional runtime error message."
    )
    score: Optional[float] = Field(
        default=None,
        description="Optional normalized score for this attempt, if available.",
    )
    test_results: list[TestCaseResult] = Field(
        default_factory=list,
        description="Structured test-case results for this attempt.",
    )
    submitted_at: datetime = Field(
        ..., description="Timestamp when the attempt was recorded."
    )


class SkillMasteryState(BaseModel):
    user_id: str = Field(..., description="Learner this mastery state belongs to.")
    skillpath_id: str = Field(..., description="Tracked skillpath identifier.")
    status: MasteryStatus = Field(
        ..., description="Current mastery state for this skillpath."
    )
    mastery_score: float = Field(
        default=0.0, description="Normalized mastery score for the skillpath."
    )
    successful_attempts: int = Field(
        default=0, description="Number of successful attempts tied to this skillpath."
    )
    failed_attempts: int = Field(
        default=0, description="Number of failed attempts tied to this skillpath."
    )
    strong_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts the learner appears comfortable with in this skillpath.",
    )
    weak_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts the learner still struggles with in this skillpath.",
    )
    last_attempt_at: Optional[datetime] = Field(
        default=None, description="Timestamp of the most recent linked attempt."
    )
    last_updated_at: datetime = Field(
        ..., description="Timestamp when this mastery state was last updated."
    )


class LearnerMemoryNote(BaseModel):
    memory_id: str = Field(..., description="Unique identifier for this memory note.")
    user_id: str = Field(..., description="Learner this memory note belongs to.")
    memory_type: MemoryType = Field(..., description="Type of learning memory note.")
    title: str = Field(..., description="Short human-readable memory title.")
    summary: str = Field(..., description="Compact summary of the learner memory.")
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags used for exact or keyword retrieval.",
    )
    linked_concepts: list[str] = Field(
        default_factory=list,
        description="Concept identifiers or labels tied to this memory.",
    )
    linked_skillpath_ids: list[str] = Field(
        default_factory=list,
        description="Skillpaths this memory is most relevant to.",
    )
    linked_content_ids: list[str] = Field(
        default_factory=list,
        description="Specific learning content items this memory relates to.",
    )
    evidence_attempt_ids: list[str] = Field(
        default_factory=list,
        description="Attempt identifiers that support this memory note.",
    )
    embedding: Optional[list[float]] = Field(
        default=None,
        description="Optional embedding used internally for semantic retrieval.",
    )
    salience_score: float = Field(
        default=0.5,
        description="Importance score used during retrieval ranking.",
    )
    status: MemoryStatus = Field(
        default=MemoryStatus.ACTIVE,
        description="Lifecycle status for this memory note.",
    )
    created_at: datetime = Field(
        ..., description="Timestamp when this memory note was created."
    )
    last_seen_at: Optional[datetime] = Field(
        default=None, description="Most recent time supporting evidence was observed."
    )
    last_used_at: Optional[datetime] = Field(
        default=None, description="Most recent time this memory was retrieved for use."
    )


class LearningMemoryContext(BaseModel):
    mastery_state: Optional[SkillMasteryState] = Field(
        default=None,
        description="Current mastery state for the requested skillpath, if available.",
    )
    recent_attempts: list[CodingProblemAttempt] = Field(
        default_factory=list,
        description="Recent attempts relevant to the current coding task.",
    )
    active_error_patterns: list[LearnerMemoryNote] = Field(
        default_factory=list,
        description="Retrieved active error-pattern memories relevant to the current task.",
    )
    mastery_signals: list[LearnerMemoryNote] = Field(
        default_factory=list,
        description="Retrieved mastery-signal memories relevant to the current task.",
    )
    teaching_heuristics: list[LearnerMemoryNote] = Field(
        default_factory=list,
        description="Retrieved teaching-heuristic memories relevant to the current task.",
    )
    background_notes: list[LearnerMemoryNote] = Field(
        default_factory=list,
        description="Retrieved background or preference memories relevant to the current task.",
    )
    relevant_notes: list[LearnerMemoryNote] = Field(
        default_factory=list,
        description="Retrieved learner memory notes ranked for the current task.",
    )


class RecordAndConsolidateAttemptResult(BaseModel):
    attempt: CodingProblemAttempt = Field(
        ..., description="The coding problem attempt that was persisted."
    )
    updated_notes: list[LearnerMemoryNote] = Field(
        default_factory=list,
        description="Memory notes created or updated during consolidation.",
    )


class MemorySalienceAdjustment(BaseModel):
    memory_id: str = Field(..., description="Memory note the judgment wants to adjust.")
    delta: float = Field(
        ...,
        description=(
            "Suggested salience change. The memory service clamps this before "
            "applying it."
        ),
    )
    reason: str = Field(..., description="Short rationale for the adjustment.")


class MemoryIntegrityEvidence(BaseModel):
    candidate_memory_id: str
    candidate_memory_type: MemoryType
    type_compatible: bool = False
    concept_overlap: int = 0
    tag_overlap: int = 0
    scope_overlap: int = 0
    semantic_similarity: float = 0.0
    salience_score: float = 0.0
    status: MemoryStatus = MemoryStatus.ACTIVE
    reasons: list[str] = Field(default_factory=list)


class MemoryIntegrityAdvisorRecommendation(BaseModel):
    action: MemoryIntegrityAction
    target_memory_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    field_updates: dict[str, Any] = Field(default_factory=dict)


class MemoryIntegrityDecision(BaseModel):
    action: MemoryIntegrityAction
    target_memory_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    advisor_used: bool = False
    evidence: list[MemoryIntegrityEvidence] = Field(default_factory=list)
    field_updates: dict[str, Any] = Field(default_factory=dict)


class MergeMemoryNotesInput(BaseModel):
    user_id: str
    primary_memory_id: str
    duplicate_memory_ids: list[str]
    rationale: str = ""


class MergeMemoryNotesResult(BaseModel):
    primary_note: LearnerMemoryNote
    merged_memory_ids: list[str] = Field(default_factory=list)
    resolved_memory_ids: list[str] = Field(default_factory=list)


class ResolveMemoryConflictInput(BaseModel):
    user_id: str
    primary_memory_id: str
    conflicting_memory_id: str
    rationale: str = ""


class ResolveMemoryConflictResult(BaseModel):
    primary_note: LearnerMemoryNote
    conflicting_note: LearnerMemoryNote
    action: MemoryIntegrityAction
    rationale: str = ""


class SelectedMemoryMetadata(BaseModel):
    memory_id: str
    memory_type: MemoryType
    title: str
    reason: str = ""


class MemoryRerankRequest(BaseModel):
    purpose: MemoryRerankPurpose
    task_context: str = ""
    learner_context: str = ""
    recent_attempts: list[CodingProblemAttempt] = Field(default_factory=list)
    candidate_memories: list[LearnerMemoryNote] = Field(default_factory=list)
    max_selected: int = Field(default=3, ge=0, le=10)


class MemoryRerankResult(BaseModel):
    purpose: MemoryRerankPurpose
    selected_memories: list[SelectedMemoryMetadata] = Field(default_factory=list)
    teaching_action: TeachingAction = TeachingAction.NORMAL_HINT
    focused_concepts: list[str] = Field(default_factory=list)
    guidance: str = ""

    @property
    def selected_memory_ids(self) -> list[str]:
        return [memory.memory_id for memory in self.selected_memories]


class HintRequest(BaseModel):
    user_id: str
    skillpath_id: str | None = None
    content_id: str | None = None
    task_prompt: str
    submitted_code: str = ""
    language: str = "python"
    concept_keys: list[str] = Field(default_factory=list)
    validation_feedback: str | None = None
    hint_level: HintLevel = HintLevel.NUDGE


class HintResponse(BaseModel):
    hint: str
    hint_level: HintLevel
    teaching_action: TeachingAction = TeachingAction.NORMAL_HINT
    selected_memory_ids: list[str] = Field(default_factory=list)
    selected_memories: list[SelectedMemoryMetadata] = Field(default_factory=list)
    focused_concepts: list[str] = Field(default_factory=list)
    quick_recap: str | None = None
    contrast_example: str | None = None
    used_memory: bool = False


class MemoryConsolidationJudgment(BaseModel):
    attempt_importance: Literal["low", "medium", "high"] = "medium"
    success_quality: Literal["none", "shallow", "normal", "strong"] = "none"
    failure_kind: Literal["none", "same_pattern", "new_pattern", "mechanical_error"] = (
        "none"
    )
    related_error_pattern_ids: list[str] = Field(default_factory=list)
    merge_candidate_ids: list[list[str]] = Field(default_factory=list)
    salience_adjustments: list[MemorySalienceAdjustment] = Field(default_factory=list)
    mastery_delta: float = Field(
        default=0.0,
        description="Suggested mastery-score change. The service clamps before use.",
    )
    should_create_heuristic: bool = False
    should_mark_resolved: bool = False
    teaching_heuristic_summary: Optional[str] = None
    rationale: str = Field(
        default="No optional consolidation judgment was provided.",
        description="Human-readable explanation of the judgment.",
    )


class CodeCorrectionRequest(BaseModel):
    user_id: str = Field(..., description="Learner requesting code correction.")
    skillpath_id: str = Field(..., description="Skillpath tied to the coding problem.")
    content_id: str = Field(..., description="Coding problem content identifier.")
    coding_problem_prompt: str = Field(
        ..., description="Prompt or instructions for the coding problem."
    )
    submitted_code: str = Field(..., description="Learner-submitted code to review.")
    language: str = Field(..., description="Programming language of the submission.")
    compile_error: Optional[str] = Field(
        default=None,
        description="Optional syntax or compiler error captured by the evaluator.",
    )
    runtime_error: Optional[str] = Field(
        default=None,
        description="Optional runtime error captured by the evaluator.",
    )
    test_results: list[TestCaseResult] = Field(
        default_factory=list,
        description="Optional structured test results from a sandbox or external evaluator.",
    )
    correctness: Optional[AttemptCorrectness] = Field(
        default=None,
        description="Optional precomputed correctness result from an evaluator.",
    )
    score: Optional[float] = Field(
        default=None,
        description="Optional normalized score supplied by an evaluator.",
    )
    feedback_summary: Optional[str] = Field(
        default=None,
        description="Optional evaluator summary. If omitted, the service derives a basic one.",
    )
    detected_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts believed to be relevant to the current submission.",
    )
    detected_mistakes: list[str] = Field(
        default_factory=list,
        description="Mistakes detected by an evaluator or agent.",
    )
    top_k_notes: int = Field(
        default=5,
        description="How many memory notes to retrieve for context assembly.",
    )
    top_k_attempts: int = Field(
        default=3,
        description="How many recent attempts to retrieve for context assembly.",
    )


class CodeCorrectionResult(BaseModel):
    inferred_correctness: AttemptCorrectness = Field(
        ..., description="Normalized correctness outcome used for persistence."
    )
    feedback_summary: str = Field(
        ..., description="Correction summary stored for this attempt."
    )
    retrieval_context: LearningMemoryContext = Field(
        ...,
        description="Learner memory context retrieved before attempt persistence.",
    )
    persistence_result: RecordAndConsolidateAttemptResult = Field(
        ...,
        description="Persisted attempt plus memory notes updated during consolidation.",
    )
    suggested_focus: list[str] = Field(
        default_factory=list,
        description="Concepts or mistakes the correction agent should emphasize next.",
    )
    memory_rerank: MemoryRerankResult = Field(
        default_factory=lambda: MemoryRerankResult(
            purpose=MemoryRerankPurpose.CODE_CORRECTION
        ),
        description=(
            "Advisory selected memories and teaching guidance used for the "
            "code-correction response."
        ),
    )


class CodeSubmissionResult(BaseModel):
    validation: Any = Field(
        ...,
        description=(
            "Structured CodeValidationResult returned by the validator. Kept "
            "structural here to avoid a schema import cycle."
        ),
    )
    correction: CodeCorrectionResult = Field(
        ...,
        description="Correction, persistence, and memory-consolidation result.",
    )


class AddMemoryNoteInput(BaseModel):
    user_id: str
    memory_type: MemoryType
    title: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    linked_concepts: list[str] = Field(default_factory=list)
    linked_skillpath_ids: list[str] = Field(default_factory=list)
    linked_content_ids: list[str] = Field(default_factory=list)
    evidence_attempt_ids: list[str] = Field(default_factory=list)
    salience_score: float = 0.5
    status: MemoryStatus = MemoryStatus.ACTIVE


class UpdateMemoryNoteInput(BaseModel):
    memory_id: str
    memory_type: Optional[MemoryType] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None
    linked_concepts: Optional[list[str]] = None
    linked_skillpath_ids: Optional[list[str]] = None
    linked_content_ids: Optional[list[str]] = None
    evidence_attempt_ids: Optional[list[str]] = None
    salience_score: Optional[float] = None
    status: Optional[MemoryStatus] = None


class RecordCodingProblemAttemptInput(BaseModel):
    user_id: str
    skillpath_id: str
    content_id: str
    submitted_code: str
    language: str
    correctness: AttemptCorrectness
    feedback_summary: str
    detected_concepts: list[str] = Field(default_factory=list)
    detected_mistakes: list[str] = Field(default_factory=list)
    compile_error: Optional[str] = None
    runtime_error: Optional[str] = None
    score: Optional[float] = None
    test_results: list[TestCaseResult] = Field(default_factory=list)


class RetrieveLearningMemoryInput(BaseModel):
    user_id: str
    query_text: str
    skillpath_id: Optional[str] = None
    content_id: Optional[str] = None
    concept_keys: list[str] = Field(default_factory=list)
    memory_types: list[MemoryType] = Field(default_factory=list)
    top_k_notes: int = 5
    top_k_attempts: int = 3
