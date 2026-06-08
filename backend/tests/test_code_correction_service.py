from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.model import (
    Base,
    CodingProblemAttemptModel,
    LearnerMemoryNoteModel,
    MilestoneModel,
    RoadmapModel,
    SkillMasteryStateModel,
    SkillPathModel,
    UserModel,
)
from app.schema.entities import (
    AddMemoryNoteInput,
    CodeCorrectionRequest,
    MemoryRerankResult,
    RetrieveLearningMemoryInput,
    SelectedMemoryMetadata,
    TestCaseResult,
)
from app.schema.enums import (
    AttemptCorrectness,
    MemoryRerankPurpose,
    MemoryType,
    TeachingAction,
)
from app.services import code_correction as code_correction_service
from app.services import learning_memory as learning_memory_service
from app.services import memory_service
from app.validators.schemas import CodeValidationRequest, CodeValidationResult
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


@pytest.fixture
async def test_user(db_session):
    user_id = f"correction-itest-{uuid4()}"
    db_session.add(UserModel(user_id=user_id))
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    skillpath_id = "sp-fastapi-routing"
    db_session.add(
        RoadmapModel(
            roadmap_id=roadmap_id,
            user_id=user_id,
            version=1,
            summary="Correction test roadmap",
            target_outcome="Validate code correction flow",
            assumptions=[],
        )
    )
    db_session.add(
        MilestoneModel(
            milestone_id=milestone_id,
            roadmap_id=roadmap_id,
            title="FastAPI basics",
            description="Correction test milestone",
            objective="Support code-correction tests",
            estimated_hours=2.0,
            order_index=1,
            dependency_titles=[],
            prerequisite_milestone_ids=[],
            status="generated",
            need_modification=False,
            revision_reason=None,
        )
    )
    db_session.add(
        SkillPathModel(
            skillpath_id=skillpath_id,
            milestone_id=milestone_id,
            title="FastAPI routing",
            description="Correction test skillpath",
            estimated_hours=1.0,
            prerequisite_skillpath_ids=[],
            learning_objectives=["Understand routing"],
            status="generated",
            need_generation=False,
            need_modification=False,
            revision_reason=None,
            affected_downstream_ids=[],
            practice_mode=None,
        )
    )
    await db_session.commit()
    try:
        yield user_id
    finally:
        await db_session.execute(
            delete(CodingProblemAttemptModel).where(
                CodingProblemAttemptModel.user_id == user_id
            )
        )
        await db_session.execute(
            delete(SkillMasteryStateModel).where(
                SkillMasteryStateModel.user_id == user_id
            )
        )
        await db_session.execute(
            delete(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == user_id
            )
        )
        await db_session.execute(
            delete(SkillPathModel).where(SkillPathModel.skillpath_id == skillpath_id)
        )
        await db_session.execute(
            delete(MilestoneModel).where(MilestoneModel.milestone_id == milestone_id)
        )
        await db_session.execute(
            delete(RoadmapModel).where(RoadmapModel.roadmap_id == roadmap_id)
        )
        await db_session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await db_session.commit()


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    def _fake_embed_text(text: str) -> list[float]:
        lowered = text.lower()
        seed = [
            1.0 if "fastapi" in lowered else 0.0,
            1.0 if "python" in lowered else 0.0,
            1.0 if "async" in lowered else 0.0,
            float(len(lowered.split())) / 10.0,
        ]
        return seed + [0.0] * (3072 - len(seed))

    async def _fake_async_embed_text(text: str) -> list[float]:
        return _fake_embed_text(text)

    monkeypatch.setattr(learning_memory_service, "_embed_text", _fake_embed_text)
    monkeypatch.setattr(
        learning_memory_service, "_async_embed_text", _fake_async_embed_text
    )


def test_build_correction_request_from_validation():
    validation = CodeValidationResult(
        correctness=AttemptCorrectness.RUNTIME_ERROR,
        has_serious_blocker=True,
        blocker_reason="Runtime error from VS Code run",
        runtime_error="NameError: name 'x' is not defined",
        validation_strategy="external_execution_evidence",
        feedback_summary="The code fails because x is undefined.",
        detected_concepts=["python.variables"],
        detected_mistakes=["undefined variable"],
        confidence_score=0.91,
    )

    request = code_correction_service.build_correction_request_from_validation(
        user_id="user-1",
        skillpath_id="sp-1",
        content_id="cp-1",
        coding_problem_prompt="Print x.",
        submitted_code="print(x)",
        language="python",
        validation=validation,
    )

    assert request.runtime_error == "NameError: name 'x' is not defined"
    assert request.correctness == AttemptCorrectness.RUNTIME_ERROR
    assert request.detected_mistakes == ["undefined variable"]


@pytest.mark.asyncio
async def test_process_code_correction_uses_runtime_error_and_updates_memory(
    db_session, test_user: str
):
    seeded_note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Existing async issue",
            summary="Learner often forgets await in FastAPI routes.",
            tags=["fastapi", "async"],
            linked_concepts=["fastapi.async", "fastapi.routing"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-1"],
            salience_score=0.6,
        ),
        db_session,
    )

    result = await code_correction_service.process_code_correction(
        CodeCorrectionRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-1",
            coding_problem_prompt="Fix the async FastAPI handler so the DB call is awaited.",
            submitted_code="result = db_call()",
            language="python",
            runtime_error="Coroutine was never awaited",
            detected_concepts=["fastapi.async", "fastapi.routing"],
            detected_mistakes=["missing await"],
        ),
        db_session,
    )

    assert result.inferred_correctness == AttemptCorrectness.RUNTIME_ERROR
    assert "Runtime issue detected" in result.feedback_summary
    assert result.retrieval_context.active_error_patterns
    assert (
        result.retrieval_context.active_error_patterns[0].memory_id
        == seeded_note.memory_id
    )
    assert (
        result.persistence_result.attempt.runtime_error == "Coroutine was never awaited"
    )
    assert result.persistence_result.updated_notes
    assert any(
        note.memory_type == MemoryType.ERROR_PATTERN
        for note in result.persistence_result.updated_notes
    )
    assert result.suggested_focus == [
        "missing await",
        "fastapi.async",
        "fastapi.routing",
    ]


@pytest.mark.asyncio
async def test_process_code_correction_reranks_retrieved_memory_for_correction(
    monkeypatch, db_session, test_user: str
):
    seeded_note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI route missing await",
            summary="Learner repeatedly forgets await in FastAPI handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-rerank"],
            salience_score=0.95,
        ),
        db_session,
    )
    captured_requests = []

    async def _fake_rerank_memories(request, *, advisor=None):
        captured_requests.append(request)
        return MemoryRerankResult(
            purpose=MemoryRerankPurpose.CODE_CORRECTION,
            selected_memories=[
                SelectedMemoryMetadata(
                    memory_id=seeded_note.memory_id,
                    memory_type=seeded_note.memory_type,
                    title=seeded_note.title,
                    reason="Directly matches the missing-await correction.",
                )
            ],
            teaching_action=TeachingAction.QUICK_RECAP_THEN_HINT,
            focused_concepts=["fastapi.async", "missing await"],
            guidance="Focus feedback on awaiting coroutine-producing calls.",
        )

    monkeypatch.setattr(memory_service, "rerank_memories", _fake_rerank_memories)

    result = await code_correction_service.process_code_correction(
        CodeCorrectionRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-rerank",
            coding_problem_prompt="Fix the FastAPI route so it awaits the DB call.",
            submitted_code="async def route():\n    return fetch_user()",
            language="python",
            runtime_error="RuntimeWarning: coroutine was never awaited",
            detected_concepts=["fastapi.async"],
            detected_mistakes=["missing await"],
        ),
        db_session,
    )

    assert captured_requests
    rerank_request = captured_requests[0]
    assert rerank_request.purpose == MemoryRerankPurpose.CODE_CORRECTION
    assert seeded_note.memory_id in [
        note.memory_id for note in rerank_request.candidate_memories
    ]
    assert result.memory_rerank.selected_memory_ids == [seeded_note.memory_id]
    assert result.memory_rerank.teaching_action == (
        TeachingAction.QUICK_RECAP_THEN_HINT
    )
    assert "awaiting coroutine-producing calls" in result.memory_rerank.guidance


@pytest.mark.asyncio
async def test_process_code_correction_persists_attempt_and_retrieves_new_memory(
    db_session, test_user: str
):
    result = await code_correction_service.process_code_correction(
        CodeCorrectionRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-vscode-runtime",
            coding_problem_prompt=(
                "Implement an async FastAPI route handler that awaits the database call."
            ),
            submitted_code="async def route():\n    return db.fetch_user()",
            language="python",
            runtime_error="RuntimeWarning: coroutine 'fetch_user' was never awaited",
            test_results=[
                TestCaseResult(
                    name="awaits db call",
                    passed=False,
                    message="coroutine was never awaited",
                )
            ],
            detected_concepts=["fastapi.async", "fastapi.routing"],
            detected_mistakes=["missing await"],
        ),
        db_session,
    )

    persisted_attempts = await db_session.execute(
        select(CodingProblemAttemptModel).where(
            CodingProblemAttemptModel.user_id == test_user,
            CodingProblemAttemptModel.content_id == "cp-vscode-runtime",
        )
    )
    persisted_attempt = persisted_attempts.scalar_one()
    assert persisted_attempt.attempt_id == result.persistence_result.attempt.attempt_id
    assert persisted_attempt.runtime_error == (
        "RuntimeWarning: coroutine 'fetch_user' was never awaited"
    )

    notes = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user,
            LearnerMemoryNoteModel.memory_type == MemoryType.ERROR_PATTERN.value,
        )
    )
    error_note = notes.scalar_one()
    assert persisted_attempt.attempt_id in error_note.evidence_attempt_ids

    later_context = await learning_memory_service.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=test_user,
            query_text="fastapi async route await coroutine was never awaited",
            skillpath_id="sp-fastapi-routing",
            content_id="cp-vscode-runtime",
            concept_keys=["fastapi.async", "fastapi.routing", "missing await"],
            top_k_notes=5,
        ),
        db_session,
    )

    later_ids = [note.memory_id for note in later_context.relevant_notes]
    assert error_note.memory_id in later_ids
    assert later_context.active_error_patterns[0].memory_id == error_note.memory_id


@pytest.mark.asyncio
async def test_process_code_correction_infers_partial_correctness_from_tests(
    db_session, test_user: str
):
    result = await code_correction_service.process_code_correction(
        CodeCorrectionRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-2",
            coding_problem_prompt="Return both route metadata and payload correctly.",
            submitted_code="return {'ok': True}",
            language="python",
            test_results=[
                TestCaseResult(name="returns payload", passed=True),
                TestCaseResult(name="includes metadata", passed=False),
            ],
            detected_concepts=["fastapi.routing"],
            detected_mistakes=["missing metadata"],
        ),
        db_session,
    )

    assert result.inferred_correctness == AttemptCorrectness.PARTIALLY_CORRECT
    assert result.feedback_summary == "Passed 1 of 2 tests."
    assert (
        result.persistence_result.attempt.correctness
        == AttemptCorrectness.PARTIALLY_CORRECT
    )
    assert result.retrieval_context.mastery_state is None or (
        result.retrieval_context.mastery_state.skillpath_id == "sp-fastapi-routing"
    )

    persisted_attempts = await db_session.execute(
        select(CodingProblemAttemptModel).where(
            CodingProblemAttemptModel.user_id == test_user,
            CodingProblemAttemptModel.content_id == "cp-2",
        )
    )
    rows = list(persisted_attempts.scalars())
    assert len(rows) == 1
    assert rows[0].correctness == AttemptCorrectness.PARTIALLY_CORRECT.value


@pytest.mark.asyncio
async def test_submit_code_attempt_validates_then_persists_memory(
    monkeypatch, db_session, test_user: str
):
    async def _fake_validate_code_submission(request, *, backend=None, model=None):
        assert request.user_id == test_user
        return CodeValidationResult(
            correctness=AttemptCorrectness.RUNTIME_ERROR,
            has_serious_blocker=True,
            blocker_reason="Un-awaited coroutine",
            runtime_error="RuntimeWarning: coroutine 'fetch_user' was never awaited",
            test_results=[
                TestCaseResult(
                    name="awaits fetch_user",
                    passed=False,
                    message="coroutine was never awaited",
                )
            ],
            validation_strategy="fake_validator",
            feedback_summary="The async helper was called without await.",
            detected_concepts=["fastapi.async", "fastapi.routing"],
            detected_mistakes=["missing await", "unawaited coroutine"],
            confidence_score=0.94,
        )

    monkeypatch.setattr(
        code_correction_service,
        "validate_code_submission",
        _fake_validate_code_submission,
    )

    result = await code_correction_service.submit_code_attempt(
        CodeValidationRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-submit-boundary",
            language="python",
            coding_problem_prompt=(
                "Implement an async FastAPI route that awaits fetch_user()."
            ),
            submitted_code=(
                "async def get_user(user_id: str):\n"
                "    user = fetch_user(user_id)\n"
                "    return {'user': user}\n"
            ),
            runtime_error="RuntimeWarning: coroutine 'fetch_user' was never awaited",
        ),
        db_session,
    )

    assert result.validation.validation_strategy == "fake_validator"
    assert result.correction.inferred_correctness == AttemptCorrectness.RUNTIME_ERROR
    assert (
        result.correction.persistence_result.attempt.content_id == "cp-submit-boundary"
    )
    assert result.correction.persistence_result.updated_notes
    assert any(
        note.memory_type == MemoryType.ERROR_PATTERN
        for note in result.correction.persistence_result.updated_notes
    )
