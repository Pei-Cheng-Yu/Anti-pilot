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
    MemoryConsolidationJudgment,
    MemorySalienceAdjustment,
    RecordCodingProblemAttemptInput,
    RetrieveLearningMemoryInput,
)
from app.schema.enums import AttemptCorrectness, MasteryStatus, MemoryStatus, MemoryType
from app.services import learning_memory as learning_memory_service
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
    user_id = f"mem-itest-{uuid4()}"
    db_session.add(UserModel(user_id=user_id))
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    skillpath_id = "sp-fastapi-routing"
    db_session.add(
        RoadmapModel(
            roadmap_id=roadmap_id,
            user_id=user_id,
            version=1,
            summary="Memory test roadmap",
            target_outcome="Validate learning memory flow",
            assumptions=[],
        )
    )
    db_session.add(
        MilestoneModel(
            milestone_id=milestone_id,
            roadmap_id=roadmap_id,
            title="FastAPI basics",
            description="Memory test milestone",
            objective="Support memory-service tests",
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
            description="Memory test skillpath",
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


def test_build_memory_note_search_text_includes_scope_and_evidence():
    search_text = learning_memory_service._build_memory_note_search_text(
        title="Repeated async issue",
        summary="Learner forgets await in FastAPI routes.",
        tags=["fastapi", "async"],
        linked_concepts=["fastapi.async"],
        linked_skillpath_ids=["sp-fastapi-routing"],
        linked_content_ids=["cp-1"],
        evidence_attempt_ids=["attempt-1"],
    )

    assert "Repeated async issue" in search_text
    assert "fastapi.async" in search_text
    assert "sp-fastapi-routing" in search_text
    assert "attempt-1" in search_text


@pytest.mark.asyncio
async def test_add_memory_note_creates_embedding(db_session, test_user: str):
    note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="Knows Python basics",
            summary="Learner has completed Python fundamentals before APIs.",
            tags=["python"],
            linked_concepts=["python.basics"],
        ),
        db_session,
    )

    assert note.embedding is not None
    assert len(note.embedding) == 3072


@pytest.mark.asyncio
async def test_record_attempt_updates_mastery(db_session, test_user: str):
    await learning_memory_service.record_coding_problem_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-1",
            submitted_code="print('ok')",
            language="python",
            correctness=AttemptCorrectness.CORRECT,
            feedback_summary="Looks correct.",
            detected_concepts=["fastapi.routing"],
        ),
        db_session,
    )

    mastery_state = await learning_memory_service.get_skill_mastery_state(
        test_user, "sp-fastapi-routing", db_session
    )

    assert mastery_state is not None
    assert mastery_state.successful_attempts == 1
    assert mastery_state.mastery_score > 0.0
    assert mastery_state.status == MasteryStatus.PRACTICING


@pytest.mark.asyncio
async def test_retrieve_memory_ranks_linked_skillpath_and_concepts_higher(
    db_session, test_user: str
):
    strong = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI async route confusion",
            summary="Learner forgets await in FastAPI route handlers.",
            tags=["fastapi", "async"],
            linked_concepts=["fastapi.async", "fastapi.routing"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.7,
        ),
        db_session,
    )
    await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="General Python background",
            summary="Learner has Python experience from earlier study.",
            tags=["python"],
            linked_concepts=["python.basics"],
            linked_skillpath_ids=["sp-python-basics"],
            salience_score=0.7,
        ),
        db_session,
    )

    context = await learning_memory_service.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=test_user,
            query_text="fastapi async route await problem",
            skillpath_id="sp-fastapi-routing",
            concept_keys=["fastapi.async", "fastapi.routing"],
            top_k_notes=2,
        ),
        db_session,
    )

    assert len(context.relevant_notes) == 2
    assert context.relevant_notes[0].memory_id == strong.memory_id
    assert context.active_error_patterns[0].memory_id == strong.memory_id
    assert len(context.background_notes) == 1


@pytest.mark.asyncio
async def test_retrieve_memory_prefers_fastapi_async_error_over_nearby_noise(
    db_session, test_user: str
):
    strong = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await in async route handlers",
            summary=(
                "Learner repeatedly calls async dependencies in FastAPI route "
                "handlers without awaiting them."
            ),
            tags=["fastapi", "async", "await", "route"],
            linked_concepts=["fastapi.async", "fastapi.routing", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-fastapi-await"],
            salience_score=0.85,
        ),
        db_session,
    )
    nearby = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="FastAPI route decorator familiarity",
            summary="Learner understands basic FastAPI route decorators and paths.",
            tags=["fastapi", "routing"],
            linked_concepts=["fastapi.routing"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.45,
        ),
        db_session,
    )
    unrelated = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="Python list comprehension preference",
            summary="Learner likes examples using list comprehensions.",
            tags=["python", "style"],
            linked_concepts=["python.lists"],
            linked_skillpath_ids=["sp-python-basics"],
            salience_score=0.9,
        ),
        db_session,
    )
    resolved = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Resolved FastAPI async issue",
            summary="Old issue about missing await in route handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "fastapi.routing", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=1.0,
        ),
        db_session,
    )
    await learning_memory_service.resolve_memory_note(resolved.memory_id, db_session)

    context = await learning_memory_service.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=test_user,
            query_text="fastapi async await route",
            skillpath_id="sp-fastapi-routing",
            concept_keys=["fastapi.async", "fastapi.routing", "missing await"],
            top_k_notes=5,
        ),
        db_session,
    )

    ranked_ids = [note.memory_id for note in context.relevant_notes]
    assert ranked_ids[0] == strong.memory_id
    assert resolved.memory_id not in ranked_ids
    assert context.active_error_patterns[0].memory_id == strong.memory_id
    assert nearby.memory_id in ranked_ids
    if unrelated.memory_id in ranked_ids:
        assert ranked_ids.index(strong.memory_id) < ranked_ids.index(
            unrelated.memory_id
        )


@pytest.mark.asyncio
async def test_consolidate_attempt_memory_updates_existing_error_pattern(
    db_session, test_user: str
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Repeated async issue",
            summary="Learner struggles with async usage.",
            tags=["async"],
            linked_concepts=["python.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-1"],
            evidence_attempt_ids=[],
            salience_score=0.6,
        ),
        db_session,
    )

    attempt = await learning_memory_service.record_coding_problem_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-1",
            submitted_code="result = db_call()",
            language="python",
            correctness=AttemptCorrectness.RUNTIME_ERROR,
            feedback_summary="Forgot to await async DB call.",
            detected_concepts=["python.async"],
            detected_mistakes=["missing await"],
        ),
        db_session,
    )

    updated_notes = await learning_memory_service.consolidate_attempt_memory(
        test_user, attempt.attempt_id, db_session
    )

    result = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user,
            LearnerMemoryNoteModel.memory_type == MemoryType.ERROR_PATTERN.value,
        )
    )
    rows = list(result.scalars())

    assert len(rows) == 1
    assert rows[0].memory_id == existing.memory_id
    assert attempt.attempt_id in (rows[0].evidence_attempt_ids or [])
    assert rows[0].salience_score > 0.6
    assert updated_notes[0].memory_id == existing.memory_id


@pytest.mark.asyncio
async def test_record_and_consolidate_attempt_creates_grouped_context_and_heuristic(
    db_session, test_user: str
):
    first_attempt, first_notes = (
        await learning_memory_service.record_and_consolidate_attempt(
            RecordCodingProblemAttemptInput(
                user_id=test_user,
                skillpath_id="sp-fastapi-routing",
                content_id="cp-2",
                submitted_code="db_call()",
                language="python",
                correctness=AttemptCorrectness.RUNTIME_ERROR,
                feedback_summary="Forgot to await async route dependency.",
                detected_concepts=["fastapi.async", "fastapi.routing"],
                detected_mistakes=["missing await", "routing confusion"],
            ),
            db_session,
        )
    )
    second_attempt, second_notes = (
        await learning_memory_service.record_and_consolidate_attempt(
            RecordCodingProblemAttemptInput(
                user_id=test_user,
                skillpath_id="sp-fastapi-routing",
                content_id="cp-2",
                submitted_code="db_call()",
                language="python",
                correctness=AttemptCorrectness.RUNTIME_ERROR,
                feedback_summary="Still forgot to await async route dependency.",
                detected_concepts=["fastapi.async", "fastapi.routing"],
                detected_mistakes=["missing await", "routing confusion"],
            ),
            db_session,
        )
    )

    assert first_attempt.attempt_id != second_attempt.attempt_id
    assert any(note.memory_type == MemoryType.ERROR_PATTERN for note in second_notes)
    assert any(note.memory_type == MemoryType.HEURISTIC for note in second_notes)

    context = await learning_memory_service.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=test_user,
            query_text="fastapi await route problem",
            skillpath_id="sp-fastapi-routing",
            content_id="cp-2",
            concept_keys=["fastapi.async", "fastapi.routing"],
            top_k_notes=5,
        ),
        db_session,
    )

    assert len(context.active_error_patterns) == 1
    assert len(context.teaching_heuristics) == 1
    assert len(context.recent_attempts) == 2
    assert any(
        note.memory_id in {n.memory_id for n in context.relevant_notes}
        for note in second_notes
    )
    assert all(
        note.memory_type == MemoryType.ERROR_PATTERN
        for note in context.active_error_patterns
    )
    assert all(
        note.memory_type == MemoryType.HEURISTIC for note in context.teaching_heuristics
    )


@pytest.mark.asyncio
async def test_resolved_notes_are_excluded_from_retrieval(db_session, test_user: str):
    note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Old resolved issue",
            summary="Learner previously struggled with async routing.",
            tags=["async"],
            linked_concepts=["fastapi.async", "fastapi.routing"],
        ),
        db_session,
    )
    await learning_memory_service.resolve_memory_note(note.memory_id, db_session)

    context = await learning_memory_service.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=test_user,
            query_text="fastapi async routing",
            concept_keys=["fastapi.async"],
            top_k_notes=5,
        ),
        db_session,
    )

    assert all(item.memory_id != note.memory_id for item in context.relevant_notes)


@pytest.mark.asyncio
async def test_successful_related_attempt_downgrades_old_error_pattern(
    db_session, test_user: str
):
    old_error = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner repeatedly forgets await in async FastAPI routes.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-await"],
            salience_score=0.55,
            status=MemoryStatus.ACTIVE,
        ),
        db_session,
    )

    attempt, updated_notes = (
        await learning_memory_service.record_and_consolidate_attempt(
            RecordCodingProblemAttemptInput(
                user_id=test_user,
                skillpath_id="sp-fastapi-routing",
                content_id="cp-await",
                submitted_code="user = await fetch_user()",
                language="python",
                correctness=AttemptCorrectness.CORRECT,
                feedback_summary="Correctly awaited the async route dependency.",
                detected_concepts=["fastapi.async", "missing await"],
            ),
            db_session,
        )
    )

    persisted = await db_session.get(LearnerMemoryNoteModel, old_error.memory_id)
    assert persisted is not None
    assert persisted.status == MemoryStatus.WATCH.value
    assert persisted.salience_score < old_error.salience_score
    assert attempt.attempt_id in persisted.evidence_attempt_ids
    assert any(note.memory_id == old_error.memory_id for note in updated_notes)


@pytest.mark.asyncio
async def test_repeated_related_success_resolves_old_error_pattern_and_signals_mastery(
    db_session, test_user: str
):
    old_error = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner repeatedly forgets await in async FastAPI routes.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-await"],
            salience_score=0.55,
            status=MemoryStatus.ACTIVE,
        ),
        db_session,
    )

    for index in range(2):
        await learning_memory_service.record_and_consolidate_attempt(
            RecordCodingProblemAttemptInput(
                user_id=test_user,
                skillpath_id="sp-fastapi-routing",
                content_id="cp-await",
                submitted_code=f"user = await fetch_user({index})",
                language="python",
                correctness=AttemptCorrectness.CORRECT,
                feedback_summary="Correctly awaited the async route dependency.",
                detected_concepts=["fastapi.async", "missing await"],
            ),
            db_session,
        )

    persisted = await db_session.get(LearnerMemoryNoteModel, old_error.memory_id)
    assert persisted is not None
    assert persisted.status == MemoryStatus.RESOLVED.value
    assert persisted.salience_score <= 0.4

    notes = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user,
            LearnerMemoryNoteModel.memory_type == MemoryType.MASTERY_SIGNAL.value,
        )
    )
    mastery_signal = notes.scalar_one_or_none()
    assert mastery_signal is not None
    assert "fastapi.async" in mastery_signal.linked_concepts


@pytest.mark.asyncio
async def test_related_failure_reactivates_watched_error_pattern(
    db_session, test_user: str
):
    watched_error = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner may still forget await in async FastAPI routes.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-await"],
            salience_score=0.45,
            status=MemoryStatus.WATCH,
        ),
        db_session,
    )

    attempt, _ = await learning_memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-await",
            submitted_code="user = fetch_user()",
            language="python",
            correctness=AttemptCorrectness.RUNTIME_ERROR,
            feedback_summary="Forgot to await the async route dependency.",
            detected_concepts=["fastapi.async"],
            detected_mistakes=["missing await"],
        ),
        db_session,
    )

    persisted = await db_session.get(LearnerMemoryNoteModel, watched_error.memory_id)
    assert persisted is not None
    assert persisted.status == MemoryStatus.ACTIVE.value
    assert persisted.salience_score > watched_error.salience_score
    assert attempt.attempt_id in persisted.evidence_attempt_ids


@pytest.mark.asyncio
async def test_repeated_success_moves_concept_from_weak_to_strong(
    db_session, test_user: str
):
    await learning_memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-await",
            submitted_code="user = fetch_user()",
            language="python",
            correctness=AttemptCorrectness.RUNTIME_ERROR,
            feedback_summary="Forgot to await the async route dependency.",
            detected_concepts=["fastapi.async"],
            detected_mistakes=["missing await"],
        ),
        db_session,
    )

    first_success, _ = await learning_memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-await",
            submitted_code="user = await fetch_user()",
            language="python",
            correctness=AttemptCorrectness.CORRECT,
            feedback_summary="Correctly awaited the async route dependency.",
            detected_concepts=["fastapi.async", "missing await"],
        ),
        db_session,
    )

    early_mastery = await learning_memory_service.get_skill_mastery_state(
        test_user, "sp-fastapi-routing", db_session
    )
    assert early_mastery is not None
    assert "fastapi.async" in early_mastery.weak_concepts

    second_success, _ = await learning_memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-await",
            submitted_code="return await fetch_user()",
            language="python",
            correctness=AttemptCorrectness.CORRECT,
            feedback_summary="Correctly awaited the async route dependency again.",
            detected_concepts=["fastapi.async", "missing await"],
        ),
        db_session,
    )

    mastery = await learning_memory_service.get_skill_mastery_state(
        test_user, "sp-fastapi-routing", db_session
    )
    assert mastery is not None
    assert "fastapi.async" in mastery.strong_concepts
    assert "missing await" in mastery.strong_concepts
    assert "fastapi.async" not in mastery.weak_concepts
    assert "missing await" not in mastery.weak_concepts

    notes = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user,
            LearnerMemoryNoteModel.memory_type == MemoryType.MASTERY_SIGNAL.value,
        )
    )
    mastery_signal = notes.scalar_one_or_none()
    assert mastery_signal is not None
    assert first_success.attempt_id in mastery_signal.evidence_attempt_ids
    assert second_success.attempt_id in mastery_signal.evidence_attempt_ids


@pytest.mark.asyncio
async def test_consolidation_judgment_applies_bounded_salience_adjustment(
    db_session, test_user: str
):
    note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async route handlers.",
            tags=["fastapi", "async"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-other"],
            linked_content_ids=["cp-await"],
            salience_score=0.5,
            status=MemoryStatus.ACTIVE,
        ),
        db_session,
    )

    def provider(attempt, mastery_state, candidate_notes, recent_attempts):
        assert attempt.skillpath_id == "sp-fastapi-routing"
        assert mastery_state is not None
        assert any(
            candidate.memory_id == note.memory_id for candidate in candidate_notes
        )
        assert recent_attempts
        return MemoryConsolidationJudgment(
            success_quality="strong",
            salience_adjustments=[
                MemorySalienceAdjustment(
                    memory_id=note.memory_id,
                    delta=-0.12,
                    reason="Strong related success reduces active salience.",
                )
            ],
            rationale="Learner demonstrated the awaited route pattern.",
        )

    await learning_memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-unrelated",
            submitted_code="return await fetch_user()",
            language="python",
            correctness=AttemptCorrectness.CORRECT,
            feedback_summary="Correct.",
            detected_concepts=["fastapi.routing"],
        ),
        db_session,
        judgment_provider=provider,
    )

    persisted = await db_session.get(LearnerMemoryNoteModel, note.memory_id)
    assert persisted is not None
    assert persisted.salience_score == pytest.approx(0.38)


@pytest.mark.asyncio
async def test_consolidation_judgment_clamps_and_ignores_out_of_scope_ids(
    db_session, test_user: str
):
    note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async route handlers.",
            tags=["fastapi", "async"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-other"],
            linked_content_ids=["cp-await"],
            salience_score=0.5,
            status=MemoryStatus.ACTIVE,
        ),
        db_session,
    )

    def provider(attempt, mastery_state, candidate_notes, recent_attempts):
        return {
            "failure_kind": "same_pattern",
            "salience_adjustments": [
                {
                    "memory_id": note.memory_id,
                    "delta": 0.9,
                    "reason": "Overconfident judgment should be capped.",
                },
                {
                    "memory_id": "other-user-note",
                    "delta": -0.9,
                    "reason": "Out-of-scope memory id should be ignored.",
                },
            ],
            "mastery_delta": 0.9,
            "rationale": "Exercise guardrails.",
        }

    await learning_memory_service.record_and_consolidate_attempt(
        RecordCodingProblemAttemptInput(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-unrelated",
            submitted_code="return fetch_user()",
            language="python",
            correctness=AttemptCorrectness.RUNTIME_ERROR,
            feedback_summary="Runtime error.",
            detected_concepts=["fastapi.routing"],
            detected_mistakes=["runtime error"],
        ),
        db_session,
        judgment_provider=provider,
    )

    persisted = await db_session.get(LearnerMemoryNoteModel, note.memory_id)
    assert persisted is not None
    assert persisted.salience_score == pytest.approx(0.65)

    mastery = await learning_memory_service.get_skill_mastery_state(
        test_user, "sp-fastapi-routing", db_session
    )
    assert mastery is not None
    assert mastery.mastery_score == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_memory_note_mutations_reject_wrong_owner(db_session, test_user: str):
    intruder_user_id = f"mem-intruder-{uuid4()}"
    db_session.add(UserModel(user_id=intruder_user_id))
    await db_session.commit()

    try:
        note = await learning_memory_service.add_memory_note(
            AddMemoryNoteInput(
                user_id=test_user,
                memory_type=MemoryType.ERROR_PATTERN,
                title="Owned note",
                summary="This note belongs to the primary test user.",
                tags=["ownership"],
                linked_concepts=["security.boundary"],
            ),
            db_session,
        )

        with pytest.raises(ValueError, match="does not belong to user"):
            await learning_memory_service.resolve_memory_note(
                note.memory_id, db_session, user_id=intruder_user_id
            )

        with pytest.raises(ValueError, match="does not belong to user"):
            await learning_memory_service.delete_memory_note(
                note.memory_id, db_session, user_id=intruder_user_id
            )

        persisted = await db_session.get(LearnerMemoryNoteModel, note.memory_id)
        assert persisted is not None
        assert persisted.user_id == test_user
        assert persisted.status != "resolved"
    finally:
        await db_session.execute(
            delete(UserModel).where(UserModel.user_id == intruder_user_id)
        )
        await db_session.commit()
