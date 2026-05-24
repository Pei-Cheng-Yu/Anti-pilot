from __future__ import annotations

from app.schema.entities import TestCaseResult
from app.schema.enums import AttemptCorrectness
from pydantic import BaseModel, Field


class GeneratedValidationArtifact(BaseModel):
    path: str = Field(..., description="Absolute or validation-context artifact path.")
    purpose: str = Field(
        ...,
        description="Short reason this artifact was created, such as learner_submission or generated_test_harness.",
    )
    content: str | None = Field(
        default=None,
        description="Optional artifact content when the caller chooses to return it inline.",
    )


class CodeValidationRequest(BaseModel):
    user_id: str = Field(..., description="Learner requesting validation.")
    skillpath_id: str = Field(..., description="Skillpath tied to the coding problem.")
    content_id: str = Field(..., description="Coding problem content identifier.")
    language: str = Field(..., description="Programming language of the submission.")
    coding_problem_prompt: str = Field(
        ..., description="Full coding problem prompt shown to the learner."
    )
    submitted_code: str = Field(..., description="Learner-submitted solution code.")
    starter_code: str | None = Field(
        default=None,
        description="Optional starter template originally given with the problem.",
    )
    expected_output: str | None = Field(
        default=None,
        description="Optional expected output or behavior description.",
    )
    compile_error: str | None = Field(
        default=None,
        description="Compiler or syntax error supplied by the caller.",
    )
    runtime_error: str | None = Field(
        default=None,
        description="Runtime error supplied by the caller.",
    )
    stdout: str | None = Field(
        default=None,
        description="Standard output supplied by the caller.",
    )
    stderr: str | None = Field(
        default=None,
        description="Standard error supplied by the caller.",
    )
    test_results: list[TestCaseResult] = Field(
        default_factory=list,
        description="Structured test results supplied by the caller.",
    )
    timeout_seconds: int = Field(
        default=20,
        description="Maximum validation time budget retained for compatibility.",
    )


class CodeValidationResult(BaseModel):
    correctness: AttemptCorrectness = Field(
        ..., description="Normalized correctness outcome for the submission."
    )
    has_serious_blocker: bool = Field(
        ...,
        description="Whether the validator found a hard blocker before deeper validation.",
    )
    blocker_reason: str | None = Field(
        default=None,
        description="Short description of the blocker when one exists.",
    )
    compile_error: str | None = Field(
        default=None, description="Compiler or syntax error captured during validation."
    )
    runtime_error: str | None = Field(
        default=None, description="Runtime error captured during validation."
    )
    stdout: str | None = Field(
        default=None, description="Captured standard output from validation."
    )
    stderr: str | None = Field(
        default=None, description="Captured standard error from validation."
    )
    test_results: list[TestCaseResult] = Field(
        default_factory=list,
        description="Structured validation checks generated or executed by the validator.",
    )
    generated_artifacts: list[GeneratedValidationArtifact] = Field(
        default_factory=list,
        description="Files or artifacts the validator generated while validating.",
    )
    validation_strategy: str = Field(
        ...,
        description="Short strategy label such as compile_check_only or generated_harness_and_ran.",
    )
    feedback_summary: str = Field(
        ..., description="Short learner-facing summary of the validation result."
    )
    detected_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts the validator believes are relevant to the submission.",
    )
    detected_mistakes: list[str] = Field(
        default_factory=list,
        description="Mistakes or failure patterns inferred from the validation run.",
    )
    confidence_score: float = Field(
        default=0.0,
        description="Validator confidence from 0.0 to 1.0 in the produced result.",
    )
