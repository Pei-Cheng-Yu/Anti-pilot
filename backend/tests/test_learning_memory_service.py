from datetime import UTC, datetime
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
    HintRequest,
    LearnerMemoryNote,
    MemoryConsolidationJudgment,
    MemoryIntegrityAdvisorRecommendation,
    MemoryRerankRequest,
    MemoryRerankResult,
    MemorySalienceAdjustment,
    MergeMemoryNotesInput,
    RecordCodingProblemAttemptInput,
    ResolveMemoryConflictInput,
    RetrieveLearningMemoryInput,
)
from app.schema.enums import (
    AttemptCorrectness,
    HintLevel,
    MasteryStatus,
    MemoryIntegrityAction,
    MemoryRerankPurpose,
    MemoryStatus,
    MemoryType,
    TeachingAction,
)
from app.services import learning_memory as learning_memory_service
from app.services import memory_hint as memory_hint_service
from app.services import memory_integrity as memory_integrity_service
from app.services import memory_rerank_policy as memory_rerank_service
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
    await db_session.execute(
        delete(CodingProblemAttemptModel).where(
            CodingProblemAttemptModel.skillpath_id == skillpath_id
        )
    )
    await db_session.execute(
        delete(SkillMasteryStateModel).where(
            SkillMasteryStateModel.skillpath_id == skillpath_id
        )
    )
    await db_session.execute(
        delete(SkillPathModel).where(SkillPathModel.skillpath_id == skillpath_id)
    )
    await db_session.commit()
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
async def test_add_memory_note_prevents_duplicates_across_memory_types(
    db_session, test_user: str
):
    for memory_type in MemoryType:
        first = await learning_memory_service.add_memory_note(
            AddMemoryNoteInput(
                user_id=test_user,
                memory_type=memory_type,
                title=f"FastAPI async {memory_type.value}",
                summary="Learner needs support around await in FastAPI routes.",
                tags=["fastapi", "async"],
                linked_concepts=["fastapi.async", "missing await"],
                linked_skillpath_ids=["sp-fastapi-routing"],
                linked_content_ids=[f"cp-{memory_type.value}"],
                evidence_attempt_ids=[f"attempt-a-{memory_type.value}"],
                salience_score=0.4,
            ),
            db_session,
        )
        second = await learning_memory_service.add_memory_note(
            AddMemoryNoteInput(
                user_id=test_user,
                memory_type=memory_type,
                title=f"FastAPI await duplicate {memory_type.value}",
                summary="Learner still needs await support in FastAPI routes.",
                tags=["await", "async"],
                linked_concepts=["fastapi.async", "missing await"],
                linked_skillpath_ids=["sp-fastapi-routing"],
                linked_content_ids=[f"cp-{memory_type.value}"],
                evidence_attempt_ids=[f"attempt-b-{memory_type.value}"],
                salience_score=0.8,
            ),
            db_session,
        )

        assert second.memory_id == first.memory_id
        assert set(second.tags) >= {"fastapi", "async", "await"}
        assert set(second.evidence_attempt_ids) >= {
            f"attempt-a-{memory_type.value}",
            f"attempt-b-{memory_type.value}",
        }
        assert second.salience_score == 0.8

    rows = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user
        )
    )
    assert len(list(rows.scalars())) == len(MemoryType)


def test_integrity_advisor_rejects_unknown_target_ids():
    recommendation = MemoryIntegrityAdvisorRecommendation(
        action=MemoryIntegrityAction.MERGE,
        target_memory_ids=["known-memory", "unknown-memory"],
        confidence=0.95,
        rationale="Merge the duplicate notes.",
    )

    decision = memory_integrity_service.validate_advisor_recommendation(
        recommendation,
        candidate_memory_ids={"known-memory"},
    )

    assert decision.action == MemoryIntegrityAction.CREATE_NEW
    assert decision.advisor_used is False
    assert "unknown" in decision.rationale.lower()


def test_integrity_advisor_low_confidence_falls_back_to_create_new():
    recommendation = MemoryIntegrityAdvisorRecommendation(
        action=MemoryIntegrityAction.SKIP_DUPLICATE,
        target_memory_ids=["candidate"],
        confidence=0.2,
        rationale="Maybe a duplicate.",
    )

    decision = memory_integrity_service.validate_advisor_recommendation(
        recommendation,
        candidate_memory_ids={"candidate"},
        min_confidence=0.6,
    )

    assert decision.action == MemoryIntegrityAction.CREATE_NEW
    assert decision.advisor_used is False


def test_integrity_advisor_accepts_valid_merge_and_conflict_recommendations():
    merge = MemoryIntegrityAdvisorRecommendation(
        action=MemoryIntegrityAction.MERGE,
        target_memory_ids=["candidate-a"],
        confidence=0.9,
        rationale="The notes are semantic duplicates.",
    )
    conflict = MemoryIntegrityAdvisorRecommendation(
        action=MemoryIntegrityAction.FLAG_CONFLICT,
        target_memory_ids=["candidate-b"],
        confidence=0.85,
        rationale="The notes contradict each other.",
    )

    merge_decision = memory_integrity_service.validate_advisor_recommendation(
        merge,
        candidate_memory_ids={"candidate-a", "candidate-b"},
    )
    conflict_decision = memory_integrity_service.validate_advisor_recommendation(
        conflict,
        candidate_memory_ids={"candidate-a", "candidate-b"},
    )

    assert merge_decision.action == MemoryIntegrityAction.MERGE
    assert merge_decision.advisor_used is True
    assert conflict_decision.action == MemoryIntegrityAction.FLAG_CONFLICT
    assert conflict_decision.advisor_used is True


def test_integrity_advisor_invalid_schema_falls_back_to_create_new():
    decision = memory_integrity_service.validate_advisor_recommendation(
        {"action": "not_allowed", "target_memory_ids": ["candidate"]},
        candidate_memory_ids={"candidate"},
    )

    assert decision.action == MemoryIntegrityAction.CREATE_NEW
    assert decision.advisor_used is False
    assert "invalid" in decision.rationale.lower()


@pytest.mark.asyncio
async def test_memory_integrity_invokes_default_advisor_for_ambiguous_candidates(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.8,
        ),
        db_session,
    )

    async def advisor(_payload, candidates, _evidence, allowed_actions):
        assert existing.memory_id in {row.memory_id for row in candidates}
        assert MemoryIntegrityAction.MERGE in allowed_actions
        return MemoryIntegrityAdvisorRecommendation(
            action=MemoryIntegrityAction.MERGE,
            target_memory_ids=[existing.memory_id],
            confidence=0.91,
            rationale="The new note is a semantic duplicate of the existing pattern.",
        )

    monkeypatch.setattr(
        memory_integrity_service,
        "_default_integrity_advisor",
        lambda: advisor,
        raising=False,
    )

    decision = await memory_integrity_service.check_memory_write_integrity(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Again missing await",
            summary="Learner again forgot await in a FastAPI route.",
            tags=["await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.7,
        ),
        db_session,
    )

    assert decision.action == MemoryIntegrityAction.MERGE
    assert decision.target_memory_ids == [existing.memory_id]
    assert decision.advisor_used is True

    rows = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user
        )
    )
    notes = list(rows.scalars())
    assert [note.memory_id for note in notes] == [existing.memory_id]
    assert notes[0].status == MemoryStatus.ACTIVE.value


async def _force_integrity_action(monkeypatch, action, *, field_updates=None):
    async def advisor(_payload, candidates, _evidence, _allowed_actions):
        return MemoryIntegrityAdvisorRecommendation(
            action=action,
            target_memory_ids=[row.memory_id for row in candidates],
            confidence=0.95,
            rationale=f"Force {action.value} for executor coverage.",
            field_updates=field_updates or {},
        )

    monkeypatch.setattr(
        memory_integrity_service,
        "_default_integrity_advisor",
        lambda: advisor,
        raising=False,
    )


@pytest.mark.asyncio
async def test_integrity_executor_create_new_uses_shared_write_path(
    db_session, test_user: str
):
    note = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="Python baseline",
            summary="Learner knows Python functions.",
            tags=["python"],
            linked_concepts=["python.functions"],
            evidence_attempt_ids=["attempt-create"],
        ),
        db_session,
    )

    assert note.memory_id
    assert note.evidence_attempt_ids == ["attempt-create"]


@pytest.mark.asyncio
async def test_integrity_executor_update_existing_reinforces_target(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi", "await"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.5,
        ),
        db_session,
    )
    await _force_integrity_action(monkeypatch, MemoryIntegrityAction.UPDATE_EXISTING)

    updated = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Again missing await",
            summary="Learner again forgot await in a FastAPI route.",
            tags=["coroutine"],
            linked_concepts=["missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-await"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.8,
        ),
        db_session,
    )

    assert updated.memory_id == existing.memory_id
    assert set(updated.tags) >= {"fastapi", "await", "coroutine"}
    assert set(updated.linked_concepts) >= {"fastapi.async", "missing await"}
    assert set(updated.evidence_attempt_ids) >= {"attempt-a", "attempt-b"}
    assert updated.salience_score == 0.8


@pytest.mark.asyncio
async def test_integrity_executor_skip_duplicate_returns_target_without_mutation(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.5,
        ),
        db_session,
    )
    await _force_integrity_action(monkeypatch, MemoryIntegrityAction.SKIP_DUPLICATE)

    duplicate = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Again missing await",
            summary="Learner again forgot await in a FastAPI route.",
            tags=["new-tag"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.9,
        ),
        db_session,
    )

    row = await db_session.get(LearnerMemoryNoteModel, existing.memory_id)
    assert duplicate.memory_id == existing.memory_id
    assert row is not None
    assert row.tags == ["fastapi"]
    assert row.evidence_attempt_ids == ["attempt-a"]
    assert row.salience_score == 0.5


@pytest.mark.asyncio
async def test_integrity_executor_keep_both_scoped_creates_separate_note(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in FastAPI DB routes.",
            tags=["fastapi", "await"],
            linked_concepts=["missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
        ),
        db_session,
    )
    await _force_integrity_action(monkeypatch, MemoryIntegrityAction.KEEP_BOTH_SCOPED)

    scoped = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="File I/O missing await",
            summary="Learner forgets await in async file I/O scripts.",
            tags=["python", "await"],
            linked_concepts=["missing await"],
            linked_skillpath_ids=["sp-python-file-io"],
            evidence_attempt_ids=["attempt-b"],
        ),
        db_session,
    )

    original = await db_session.get(LearnerMemoryNoteModel, existing.memory_id)
    assert scoped.memory_id != existing.memory_id
    assert original is not None
    assert original.linked_skillpath_ids == ["sp-fastapi-routing"]
    assert original.evidence_attempt_ids == ["attempt-a"]


@pytest.mark.asyncio
async def test_integrity_executor_merge_single_target_reinforces_target(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.5,
        ),
        db_session,
    )
    await _force_integrity_action(monkeypatch, MemoryIntegrityAction.MERGE)

    merged = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Unawaited coroutine",
            summary="Learner returned an unawaited coroutine in FastAPI.",
            tags=["coroutine"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.7,
        ),
        db_session,
    )

    rows = await db_session.execute(
        select(LearnerMemoryNoteModel).where(
            LearnerMemoryNoteModel.user_id == test_user
        )
    )
    assert merged.memory_id == existing.memory_id
    assert len(list(rows.scalars())) == 1
    assert set(merged.evidence_attempt_ids) >= {"attempt-a", "attempt-b"}


@pytest.mark.asyncio
async def test_integrity_executor_merge_multiple_targets_resolves_duplicates(
    db_session, test_user: str, monkeypatch
):
    primary = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.6,
        ),
        db_session,
    )
    duplicate = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Coroutine not awaited",
            summary="Learner returns coroutine objects without awaiting.",
            tags=["coroutine"],
            linked_concepts=["coroutine"],
            linked_skillpath_ids=["sp-coroutines"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.8,
        ),
        db_session,
    )
    await _force_integrity_action(monkeypatch, MemoryIntegrityAction.MERGE)

    merged = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Again missing await",
            summary="Learner again missed await in FastAPI coroutine code.",
            tags=["await"],
            linked_concepts=["fastapi.async", "coroutine"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-c"],
            salience_score=0.7,
        ),
        db_session,
    )

    duplicate_row = await db_session.get(LearnerMemoryNoteModel, duplicate.memory_id)
    assert merged.memory_id == primary.memory_id
    assert duplicate_row is not None
    assert duplicate_row.status == MemoryStatus.RESOLVED.value
    assert set(merged.tags) >= {"fastapi", "coroutine", "await"}
    assert set(merged.evidence_attempt_ids) >= {"attempt-a", "attempt-b", "attempt-c"}


@pytest.mark.asyncio
async def test_integrity_executor_flag_conflict_creates_note_and_watches_target(
    db_session, test_user: str, monkeypatch
):
    error = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.9,
        ),
        db_session,
    )
    await _force_integrity_action(monkeypatch, MemoryIntegrityAction.FLAG_CONFLICT)

    mastery = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.MASTERY_SIGNAL,
            title="Await mastery",
            summary="Learner now consistently awaits FastAPI dependencies.",
            tags=["fastapi", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.7,
        ),
        db_session,
    )

    error_row = await db_session.get(LearnerMemoryNoteModel, error.memory_id)
    assert mastery.memory_id != error.memory_id
    assert mastery.memory_type == MemoryType.MASTERY_SIGNAL
    assert error_row is not None
    assert error_row.status == MemoryStatus.WATCH.value
    assert error_row.salience_score <= 0.45


@pytest.mark.asyncio
async def test_integrity_executor_applies_safe_title_summary_field_updates(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
        ),
        db_session,
    )
    await _force_integrity_action(
        monkeypatch,
        MemoryIntegrityAction.MERGE,
        field_updates={
            "title": "FastAPI async route missing await",
            "summary": (
                "Learner repeatedly returns coroutine-producing FastAPI calls "
                "without awaiting them first."
            ),
        },
    )

    updated = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Unawaited coroutine",
            summary="Learner again missed await.",
            tags=["await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
        ),
        db_session,
    )

    assert updated.memory_id == existing.memory_id
    assert updated.title == "FastAPI async route missing await"
    assert "coroutine-producing FastAPI calls" in updated.summary


@pytest.mark.asyncio
async def test_integrity_executor_ignores_unsafe_field_updates(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
            salience_score=0.6,
        ),
        db_session,
    )
    await _force_integrity_action(
        monkeypatch,
        MemoryIntegrityAction.MERGE,
        field_updates={
            "user_id": "other-user",
            "memory_type": MemoryType.MASTERY_SIGNAL.value,
            "status": MemoryStatus.RESOLVED.value,
            "salience_score": 0.0,
            "evidence_attempt_ids": ["unsafe-attempt"],
            "embedding": [1.0],
            "search_text": "unsafe search text",
            "created_at": "2026-01-01T00:00:00",
            "title": "FastAPI async route missing await",
        },
    )

    updated = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Again missing await",
            summary="Learner again missed await.",
            tags=["await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
            salience_score=0.7,
        ),
        db_session,
    )

    row = await db_session.get(LearnerMemoryNoteModel, existing.memory_id)
    assert row is not None
    assert updated.title == "FastAPI async route missing await"
    assert row.user_id == test_user
    assert row.memory_type == MemoryType.ERROR_PATTERN.value
    assert row.status == MemoryStatus.ACTIVE.value
    assert row.salience_score == 0.7
    assert "unsafe-attempt" not in row.evidence_attempt_ids
    assert row.search_text != "unsafe search text"


@pytest.mark.asyncio
async def test_integrity_executor_safe_field_updates_refresh_search_text(
    db_session, test_user: str, monkeypatch
):
    existing = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi"],
            linked_concepts=["fastapi.async"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-a"],
        ),
        db_session,
    )
    await _force_integrity_action(
        monkeypatch,
        MemoryIntegrityAction.MERGE,
        field_updates={
            "title": "Coroutine boundary checklist",
            "summary": "Use a boundary checklist before returning FastAPI responses.",
        },
    )

    await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Again missing await",
            summary="Learner again missed await.",
            tags=["await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            evidence_attempt_ids=["attempt-b"],
        ),
        db_session,
    )

    row = await db_session.get(LearnerMemoryNoteModel, existing.memory_id)
    assert row is not None
    assert "Coroutine boundary checklist" in row.search_text
    assert "boundary checklist" in row.search_text


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
async def test_merge_memory_notes_preserves_scope_evidence_and_resolves_duplicates(
    db_session, test_user: str
):
    primary = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="FastAPI context",
            summary="Learner has FastAPI route background.",
            tags=["fastapi"],
            linked_concepts=["fastapi.routing"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            linked_content_ids=["cp-routing"],
            evidence_attempt_ids=["attempt-1"],
            salience_score=0.4,
        ),
        db_session,
    )
    duplicate = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="SQLAlchemy context",
            summary="Learner has async SQLAlchemy background.",
            tags=["sqlalchemy"],
            linked_concepts=["sqlalchemy.async"],
            linked_skillpath_ids=["sp-db-access"],
            linked_content_ids=["cp-db"],
            evidence_attempt_ids=["attempt-2"],
            salience_score=0.9,
        ),
        db_session,
    )

    result = await learning_memory_service.merge_memory_notes(
        MergeMemoryNotesInput(
            user_id=test_user,
            primary_memory_id=primary.memory_id,
            duplicate_memory_ids=[duplicate.memory_id],
            rationale="Unify related backend background notes.",
        ),
        db_session,
    )

    assert result.primary_note.memory_id == primary.memory_id
    assert duplicate.memory_id in result.resolved_memory_ids
    assert set(result.primary_note.tags) >= {"fastapi", "sqlalchemy"}
    assert set(result.primary_note.linked_concepts) >= {
        "fastapi.routing",
        "sqlalchemy.async",
    }
    assert set(result.primary_note.linked_skillpath_ids) >= {
        "sp-fastapi-routing",
        "sp-db-access",
    }
    assert set(result.primary_note.evidence_attempt_ids) >= {"attempt-1", "attempt-2"}
    assert result.primary_note.salience_score == 0.9

    resolved = await db_session.get(LearnerMemoryNoteModel, duplicate.memory_id)
    assert resolved is not None
    assert resolved.status == MemoryStatus.RESOLVED.value


@pytest.mark.asyncio
async def test_resolve_memory_conflict_downgrades_error_when_mastery_wins(
    db_session, test_user: str
):
    error = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            tags=["fastapi", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.75,
        ),
        db_session,
    )
    mastery = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.MASTERY_SIGNAL,
            title="Await mastery",
            summary="Learner now consistently awaits FastAPI dependencies.",
            tags=["fastapi", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.7,
        ),
        db_session,
    )

    result = await learning_memory_service.resolve_memory_conflict(
        ResolveMemoryConflictInput(
            user_id=test_user,
            primary_memory_id=mastery.memory_id,
            conflicting_memory_id=error.memory_id,
            rationale="Recent mastery should downgrade the older error pattern.",
        ),
        db_session,
    )

    assert result.primary_note.status == MemoryStatus.ACTIVE
    assert result.conflicting_note.status == MemoryStatus.WATCH
    assert result.conflicting_note.salience_score < error.salience_score


@pytest.mark.asyncio
async def test_resolve_memory_conflict_downgrades_weaker_preference_signal(
    db_session, test_user: str
):
    active = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.PREFERENCE_SIGNAL,
            title="Prefers examples first",
            summary="Learner prefers examples before abstract explanation.",
            tags=["examples-first"],
            linked_concepts=["teaching.preference"],
            evidence_attempt_ids=["attempt-current"],
            salience_score=0.75,
        ),
        db_session,
    )
    conflicting = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.PREFERENCE_SIGNAL,
            title="Prefers theory first",
            summary="Learner prefers theory before examples.",
            tags=["theory-first"],
            linked_concepts=["teaching.preference"],
            salience_score=0.55,
        ),
        db_session,
    )

    result = await learning_memory_service.resolve_memory_conflict(
        ResolveMemoryConflictInput(
            user_id=test_user,
            primary_memory_id=active.memory_id,
            conflicting_memory_id=conflicting.memory_id,
            rationale="Keep the stronger current preference active.",
        ),
        db_session,
    )

    assert result.primary_note.status == MemoryStatus.ACTIVE
    assert result.conflicting_note.status == MemoryStatus.WATCH
    assert result.action == MemoryIntegrityAction.FLAG_CONFLICT


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


def test_memory_rerank_rejects_invalid_advisor_memory_ids():
    candidate = LearnerMemoryNote(
        memory_id="candidate-1",
        user_id="user-1",
        memory_type=MemoryType.ERROR_PATTERN,
        title="Missing await",
        summary="Learner forgets await in FastAPI routes.",
        tags=["await"],
        linked_concepts=["fastapi.async"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    result = memory_rerank_service.rerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.HINT_GENERATION,
            task_context="FastAPI async route",
            candidate_memories=[candidate],
        ),
        advisor=lambda _request: MemoryRerankResult(
            purpose=MemoryRerankPurpose.HINT_GENERATION,
            selected_memories=[
                {
                    "memory_id": "not-a-candidate",
                    "memory_type": "error_pattern",
                    "title": "Bad",
                    "reason": "Invalid ID",
                }
            ],
            teaching_action=TeachingAction.NORMAL_HINT,
            focused_concepts=[],
            guidance="Invalid selection.",
        ),
    )

    assert result.selected_memory_ids == ["candidate-1"]
    assert result.teaching_action == TeachingAction.QUICK_RECAP_THEN_HINT


def test_memory_rerank_valid_advisor_output_and_purpose_guidance():
    candidate = LearnerMemoryNote(
        memory_id="candidate-1",
        user_id="user-1",
        memory_type=MemoryType.HEURISTIC,
        title="Use contrast examples",
        summary="Show await versus missing await before practice.",
        tags=["contrast"],
        linked_concepts=["fastapi.async"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    result = memory_rerank_service.rerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.CONTENT_GENERATION,
            task_context="Generate FastAPI content",
            candidate_memories=[candidate],
        ),
        advisor=lambda _request: {
            "purpose": "content_generation",
            "selected_memories": [
                {
                    "memory_id": "candidate-1",
                    "memory_type": "heuristic",
                    "title": "Use contrast examples",
                    "reason": "Useful for generated examples.",
                }
            ],
            "teaching_action": "contrast_example",
            "focused_concepts": ["fastapi.async"],
            "guidance": "Add a contrast example.",
        },
    )

    assert result.selected_memory_ids == ["candidate-1"]
    assert result.teaching_action == TeachingAction.CONTRAST_EXAMPLE
    assert "contrast" in result.guidance.lower()


def test_memory_rerank_invalid_schema_falls_back_to_ranked_candidates():
    candidate = LearnerMemoryNote(
        memory_id="candidate-1",
        user_id="user-1",
        memory_type=MemoryType.BACKGROUND,
        title="Python basics",
        summary="Learner knows Python basics.",
        linked_concepts=["python.basics"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    result = memory_rerank_service.rerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.CODE_CORRECTION,
            task_context="Correct code",
            candidate_memories=[candidate],
        ),
        advisor=lambda _request: {"selected_memories": "bad"},
    )

    assert result.selected_memory_ids == ["candidate-1"]
    assert result.purpose == MemoryRerankPurpose.CODE_CORRECTION
    assert result.guidance


@pytest.mark.asyncio
async def test_memory_rerank_awaits_async_advisor_and_validates_ids():
    candidate = LearnerMemoryNote(
        memory_id="candidate-1",
        user_id="user-1",
        memory_type=MemoryType.ERROR_PATTERN,
        title="Missing await",
        summary="Learner forgets await in FastAPI routes.",
        tags=["await"],
        linked_concepts=["fastapi.async"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    async def advisor(_request):
        return {
            "purpose": "hint_generation",
            "selected_memories": [
                {
                    "memory_id": "candidate-1",
                    "memory_type": "error_pattern",
                    "title": "Missing await",
                    "reason": "Relevant repeated mistake.",
                }
            ],
            "teaching_action": "quick_recap_then_hint",
            "focused_concepts": ["fastapi.async"],
            "guidance": "Use this memory to shape the next hint.",
        }

    result = await memory_rerank_service.arerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.HINT_GENERATION,
            task_context="FastAPI async route",
            candidate_memories=[candidate],
        ),
        advisor=advisor,
    )

    assert result.selected_memory_ids == ["candidate-1"]
    assert result.teaching_action == TeachingAction.QUICK_RECAP_THEN_HINT
    assert result.guidance == "Use this memory to shape the next hint."


@pytest.mark.asyncio
async def test_memory_rerank_invokes_default_advisor_when_available(monkeypatch):
    candidate = LearnerMemoryNote(
        memory_id="candidate-1",
        user_id="user-1",
        memory_type=MemoryType.HEURISTIC,
        title="Contrast missing await",
        summary="Use contrast examples for await mistakes.",
        tags=["contrast"],
        linked_concepts=["fastapi.async"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    async def advisor(_request):
        return {
            "purpose": "content_generation",
            "selected_memories": [
                {
                    "memory_id": "candidate-1",
                    "memory_type": "heuristic",
                    "title": "Contrast missing await",
                    "reason": "Advisor-selected contrast heuristic.",
                }
            ],
            "teaching_action": "contrast_example",
            "focused_concepts": ["fastapi.async"],
            "guidance": "Generate a contrast example before the exercise.",
        }

    monkeypatch.setattr(
        memory_rerank_service,
        "_default_rerank_advisor",
        lambda: advisor,
        raising=False,
    )

    result = await memory_rerank_service.arerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.CONTENT_GENERATION,
            task_context="Generate FastAPI async content.",
            candidate_memories=[candidate],
        )
    )

    assert result.selected_memory_ids == ["candidate-1"]
    assert result.teaching_action == TeachingAction.CONTRAST_EXAMPLE
    assert result.guidance == "Generate a contrast example before the exercise."


@pytest.mark.asyncio
async def test_memory_aware_hint_selects_missing_await_memory_over_sql_noise(
    db_session, test_user: str
):
    missing_await = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async FastAPI route handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.8,
        ),
        db_session,
    )
    sql_noise = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.BACKGROUND,
            title="SQL joins",
            summary="Learner has practiced SQL joins.",
            tags=["sql"],
            linked_concepts=["sql.joins"],
            linked_skillpath_ids=["sp-sql"],
            salience_score=0.95,
        ),
        db_session,
    )

    hint = await memory_hint_service.generate_memory_aware_hint(
        HintRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-await",
            task_prompt="Fix the FastAPI route so the async database call is awaited.",
            submitted_code="product = get_product_from_db(product_id)",
            concept_keys=["fastapi.async", "missing await"],
            hint_level=HintLevel.NUDGE,
        ),
        db_session,
    )

    assert missing_await.memory_id in hint.selected_memory_ids
    assert sql_noise.memory_id not in hint.selected_memory_ids
    assert hint.teaching_action == TeachingAction.QUICK_RECAP_THEN_HINT
    assert "await" in hint.hint.lower()
    assert "await get_product_from_db(product_id)" not in hint.hint


@pytest.mark.asyncio
async def test_memory_aware_hint_uses_hint_advisor_and_validates_memory_ids(
    db_session, test_user: str
):
    memory = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async FastAPI route handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.8,
        ),
        db_session,
    )

    async def advisor(request, memory_context, rerank_result):
        assert rerank_result.selected_memory_ids == [memory.memory_id]
        return {
            "hint": "Check which async call still needs `await` before returning.",
            "hint_level": "nudge",
            "teaching_action": "quick_recap_then_hint",
            "selected_memory_ids": [memory.memory_id],
            "selected_memories": [
                {
                    "memory_id": memory.memory_id,
                    "memory_type": "error_pattern",
                    "title": "FastAPI missing await",
                    "reason": "This is the active repeated mistake.",
                }
            ],
            "focused_concepts": ["fastapi.async", "missing await"],
            "quick_recap": "Async functions return awaitable values.",
            "used_memory": True,
        }

    hint = await memory_hint_service.generate_memory_aware_hint(
        HintRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            task_prompt="Fix the FastAPI route so the DB call is awaited.",
            submitted_code="product = get_product_from_db(product_id)",
            concept_keys=["fastapi.async", "missing await"],
            hint_level=HintLevel.NUDGE,
        ),
        db_session,
        hint_advisor=advisor,
    )

    assert hint.hint == "Check which async call still needs `await` before returning."
    assert hint.selected_memory_ids == [memory.memory_id]


@pytest.mark.asyncio
async def test_memory_aware_hint_invokes_default_hint_advisor_when_available(
    db_session, test_user: str, monkeypatch
):
    memory = await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async FastAPI route handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.8,
        ),
        db_session,
    )

    async def advisor(_request, _memory_context, rerank_result):
        return {
            "hint": "Default advisor says to inspect the unresolved async call.",
            "hint_level": "nudge",
            "teaching_action": "quick_recap_then_hint",
            "selected_memory_ids": rerank_result.selected_memory_ids,
            "selected_memories": [
                {
                    "memory_id": memory.memory_id,
                    "memory_type": "error_pattern",
                    "title": "FastAPI missing await",
                }
            ],
            "focused_concepts": ["fastapi.async"],
            "used_memory": True,
        }

    monkeypatch.setattr(
        memory_hint_service,
        "_default_hint_advisor",
        lambda: advisor,
        raising=False,
    )

    hint = await memory_hint_service.generate_memory_aware_hint(
        HintRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            task_prompt="Fix the FastAPI route so the DB call is awaited.",
            submitted_code="product = get_product_from_db(product_id)",
            concept_keys=["fastapi.async", "missing await"],
            hint_level=HintLevel.NUDGE,
        ),
        db_session,
    )

    assert hint.hint == "Default advisor says to inspect the unresolved async call."
    assert hint.selected_memory_ids == [memory.memory_id]


@pytest.mark.asyncio
async def test_memory_aware_hint_falls_back_when_advisor_reveals_solution(
    db_session, test_user: str
):
    await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async FastAPI route handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.8,
        ),
        db_session,
    )

    async def advisor(request, memory_context, rerank_result):
        return {
            "hint": "Use: product = await get_product_from_db(product_id)",
            "hint_level": "nudge",
            "teaching_action": "quick_recap_then_hint",
            "selected_memory_ids": rerank_result.selected_memory_ids,
            "focused_concepts": ["fastapi.async", "missing await"],
            "used_memory": True,
        }

    hint = await memory_hint_service.generate_memory_aware_hint(
        HintRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            task_prompt="Fix the FastAPI route so the DB call is awaited.",
            submitted_code="product = get_product_from_db(product_id)",
            concept_keys=["fastapi.async", "missing await"],
            hint_level=HintLevel.NUDGE,
        ),
        db_session,
        hint_advisor=advisor,
    )

    assert hint.hint != "Use: product = await get_product_from_db(product_id)"
    assert "await get_product_from_db(product_id)" not in hint.hint


@pytest.mark.asyncio
async def test_memory_aware_hint_falls_back_on_invalid_advisor_schema_or_memory_ids(
    db_session, test_user: str
):
    await learning_memory_service.add_memory_note(
        AddMemoryNoteInput(
            user_id=test_user,
            memory_type=MemoryType.ERROR_PATTERN,
            title="FastAPI missing await",
            summary="Learner forgets await in async FastAPI route handlers.",
            tags=["fastapi", "async", "await"],
            linked_concepts=["fastapi.async", "missing await"],
            linked_skillpath_ids=["sp-fastapi-routing"],
            salience_score=0.8,
        ),
        db_session,
    )
    request = HintRequest(
        user_id=test_user,
        skillpath_id="sp-fastapi-routing",
        task_prompt="Fix the FastAPI route so the DB call is awaited.",
        submitted_code="product = get_product_from_db(product_id)",
        concept_keys=["fastapi.async", "missing await"],
        hint_level=HintLevel.NUDGE,
    )

    async def invalid_schema(_request, _memory_context, _rerank_result):
        return {"hint": "This response is missing required structured fields."}

    async def invalid_memory_id(_request, _memory_context, _rerank_result):
        return {
            "hint": "Advisor selected a memory outside the bounded candidate set.",
            "hint_level": "nudge",
            "teaching_action": "quick_recap_then_hint",
            "selected_memory_ids": ["not-a-candidate"],
            "focused_concepts": ["fastapi.async"],
            "used_memory": True,
        }

    schema_fallback = await memory_hint_service.generate_memory_aware_hint(
        request,
        db_session,
        hint_advisor=invalid_schema,
    )
    id_fallback = await memory_hint_service.generate_memory_aware_hint(
        request,
        db_session,
        hint_advisor=invalid_memory_id,
    )

    assert (
        schema_fallback.hint != "This response is missing required structured fields."
    )
    assert id_fallback.hint != (
        "Advisor selected a memory outside the bounded candidate set."
    )
    assert "not-a-candidate" not in id_fallback.selected_memory_ids


@pytest.mark.asyncio
async def test_memory_aware_hint_works_without_memory_and_progresses_levels(
    db_session, test_user: str
):
    nudge = await memory_hint_service.generate_memory_aware_hint(
        HintRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-general",
            task_prompt="Fix the route handler.",
            submitted_code="result = call()",
            concept_keys=["fastapi.routing"],
            hint_level=HintLevel.NUDGE,
        ),
        db_session,
    )
    specific = await memory_hint_service.generate_memory_aware_hint(
        HintRequest(
            user_id=test_user,
            skillpath_id="sp-fastapi-routing",
            content_id="cp-general",
            task_prompt="Fix the route handler.",
            submitted_code="result = call()",
            concept_keys=["fastapi.routing"],
            hint_level=HintLevel.SPECIFIC,
        ),
        db_session,
    )

    assert nudge.selected_memory_ids == []
    assert nudge.hint_level == HintLevel.NUDGE
    assert specific.hint_level == HintLevel.SPECIFIC
    assert len(specific.hint) >= len(nudge.hint)
