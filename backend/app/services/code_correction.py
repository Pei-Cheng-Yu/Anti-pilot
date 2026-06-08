from app.schema.entities import (
    CodeCorrectionRequest,
    CodeCorrectionResult,
    CodeSubmissionResult,
    LearnerMemoryNote,
    MemoryRerankRequest,
    RecordAndConsolidateAttemptResult,
    RecordCodingProblemAttemptInput,
    RetrieveLearningMemoryInput,
)
from app.schema.enums import AttemptCorrectness, MemoryRerankPurpose
from app.services import memory_service
from app.validators.deepagent_validator import validate_code_submission
from app.validators.schemas import CodeValidationRequest, CodeValidationResult
from sqlalchemy.ext.asyncio import AsyncSession


def _infer_correctness(request: CodeCorrectionRequest) -> AttemptCorrectness:
    if request.correctness is not None:
        return request.correctness
    if request.compile_error or request.runtime_error:
        return AttemptCorrectness.RUNTIME_ERROR
    if request.test_results:
        passed_count = sum(1 for item in request.test_results if item.passed)
        if passed_count == len(request.test_results):
            return AttemptCorrectness.CORRECT
        if passed_count > 0:
            return AttemptCorrectness.PARTIALLY_CORRECT
        return AttemptCorrectness.INCORRECT
    return AttemptCorrectness.INCORRECT


def _derive_feedback_summary(
    request: CodeCorrectionRequest, correctness: AttemptCorrectness
) -> str:
    if request.feedback_summary:
        return request.feedback_summary
    if request.compile_error:
        return f"Compilation or syntax issue detected: {request.compile_error}"
    if request.runtime_error:
        return f"Runtime issue detected: {request.runtime_error}"
    if request.test_results:
        passed_count = sum(1 for item in request.test_results if item.passed)
        total_count = len(request.test_results)
        if correctness == AttemptCorrectness.CORRECT:
            return f"All {total_count} tests passed."
        return f"Passed {passed_count} of {total_count} tests."
    if request.detected_mistakes:
        return "Detected issues: " + ", ".join(request.detected_mistakes[:3])
    return "Submission needs review against the problem requirements."


def _derive_query_text(request: CodeCorrectionRequest, feedback_summary: str) -> str:
    query_parts = [
        request.coding_problem_prompt,
        feedback_summary,
        " ".join(request.detected_concepts),
        " ".join(request.detected_mistakes),
        request.compile_error or "",
        request.runtime_error or "",
    ]
    return "\n".join(part for part in query_parts if part.strip())


def _derive_suggested_focus(request: CodeCorrectionRequest) -> list[str]:
    seen: set[str] = set()
    ordered_focus: list[str] = []
    for item in [*request.detected_mistakes, *request.detected_concepts]:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered_focus.append(normalized)
    return ordered_focus


def _candidate_memories_from_context(context) -> list[LearnerMemoryNote]:
    candidates: list[LearnerMemoryNote] = []
    seen: set[str] = set()
    for group in (
        context.relevant_notes,
        context.active_error_patterns,
        context.teaching_heuristics,
        context.mastery_signals,
        context.background_notes,
    ):
        for note in group:
            if note.memory_id in seen:
                continue
            seen.add(note.memory_id)
            candidates.append(note)
    return candidates


def build_correction_request_from_validation(
    *,
    user_id: str,
    skillpath_id: str,
    content_id: str,
    coding_problem_prompt: str,
    submitted_code: str,
    language: str,
    validation: CodeValidationResult,
) -> CodeCorrectionRequest:
    return CodeCorrectionRequest(
        user_id=user_id,
        skillpath_id=skillpath_id,
        content_id=content_id,
        coding_problem_prompt=coding_problem_prompt,
        submitted_code=submitted_code,
        language=language,
        compile_error=validation.compile_error,
        runtime_error=validation.runtime_error,
        test_results=validation.test_results,
        correctness=validation.correctness,
        feedback_summary=validation.feedback_summary,
        detected_concepts=validation.detected_concepts,
        detected_mistakes=validation.detected_mistakes,
    )


async def process_code_correction(
    request: CodeCorrectionRequest, session: AsyncSession
) -> CodeCorrectionResult:
    inferred_correctness = _infer_correctness(request)
    feedback_summary = _derive_feedback_summary(request, inferred_correctness)
    query_text = _derive_query_text(request, feedback_summary)

    retrieval_context = await memory_service.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=request.user_id,
            query_text=query_text,
            skillpath_id=request.skillpath_id,
            content_id=request.content_id,
            concept_keys=request.detected_concepts + request.detected_mistakes,
            top_k_notes=request.top_k_notes,
            top_k_attempts=request.top_k_attempts,
        ),
        session,
    )
    memory_rerank = await memory_service.rerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.CODE_CORRECTION,
            task_context=query_text,
            learner_context=feedback_summary,
            recent_attempts=retrieval_context.recent_attempts,
            candidate_memories=_candidate_memories_from_context(retrieval_context),
            max_selected=3,
        )
    )

    saved_attempt, updated_notes = await memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=request.user_id,
            skillpath_id=request.skillpath_id,
            content_id=request.content_id,
            submitted_code=request.submitted_code,
            language=request.language,
            correctness=inferred_correctness,
            feedback_summary=feedback_summary,
            detected_concepts=request.detected_concepts,
            detected_mistakes=request.detected_mistakes,
            compile_error=request.compile_error,
            runtime_error=request.runtime_error,
            score=request.score,
            test_results=request.test_results,
        ),
        session,
    )

    return CodeCorrectionResult(
        inferred_correctness=inferred_correctness,
        feedback_summary=feedback_summary,
        retrieval_context=retrieval_context,
        persistence_result=RecordAndConsolidateAttemptResult(
            attempt=saved_attempt,
            updated_notes=updated_notes,
        ),
        suggested_focus=_derive_suggested_focus(request),
        memory_rerank=memory_rerank,
    )


async def submit_code_attempt(
    request: CodeValidationRequest,
    session: AsyncSession,
    *,
    validator_backend=None,
    validator_model: str | None = None,
) -> CodeSubmissionResult:
    validation = await validate_code_submission(
        request,
        backend=validator_backend,
        model=validator_model,
    )
    correction_request = build_correction_request_from_validation(
        user_id=request.user_id,
        skillpath_id=request.skillpath_id,
        content_id=request.content_id,
        coding_problem_prompt=request.coding_problem_prompt,
        submitted_code=request.submitted_code,
        language=request.language,
        validation=validation,
    )
    correction = await process_code_correction(correction_request, session)
    return CodeSubmissionResult(validation=validation, correction=correction)
