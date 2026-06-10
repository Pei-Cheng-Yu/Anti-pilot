"""Tests for the skillpath completion advisor and service.

Advisor/schema tests are fully isolated (no DB, no live LLM). Service tests use
the shared Postgres DB fixture pattern and the deterministic fallback path so
they never require live LLM credentials.
"""

from datetime import UTC, datetime

import pytest
from app.schema.entities import (
    CodingProblemAttempt,
    SkillMasteryState,
    SkillpathCompletionAdvisorOutput,
    SkillPathItem,
)
from app.schema.enums import AttemptCorrectness, MasteryStatus
from pydantic import ValidationError


def _skillpath(**overrides) -> SkillPathItem:
    base = dict(
        skillpath_id="sp-async-1",
        milestone_id="m-1",
        title="Async fundamentals",
        description="Learn async/await in Python.",
        estimated_hours=3.0,
        learning_objectives=["asyncio.basics", "await_usage"],
        status="generated",
    )
    base.update(overrides)
    return SkillPathItem(**base)


def _mastery(**overrides) -> SkillMasteryState:
    base = dict(
        user_id="user-1",
        skillpath_id="sp-async-1",
        status=MasteryStatus.PRACTICING,
        mastery_score=0.4,
        successful_attempts=1,
        failed_attempts=1,
        strong_concepts=["asyncio.basics"],
        weak_concepts=["await_usage"],
        last_updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    base.update(overrides)
    return SkillMasteryState(**base)


def _attempt(
    correctness=AttemptCorrectness.CORRECT, **overrides
) -> CodingProblemAttempt:
    base = dict(
        attempt_id="att-1",
        user_id="user-1",
        skillpath_id="sp-async-1",
        content_id="c-1",
        submitted_code="async def f(): ...",
        language="python",
        correctness=correctness,
        feedback_summary="ok",
        detected_concepts=["asyncio.basics"],
        submitted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    base.update(overrides)
    return CodingProblemAttempt(**base)


def test_completion_advisor_output_accepts_valid_payload():
    out = SkillpathCompletionAdvisorOutput(
        suggested_mastery_status=MasteryStatus.PRACTICING,
        mastery_signal_salience=0.6,
        signal_strength="moderate",
        reasoning="Two correct attempts on core concepts.",
    )
    assert out.suggested_mastery_status is MasteryStatus.PRACTICING
    assert out.mastery_signal_salience == 0.6
    assert out.signal_strength == "moderate"


def test_completion_advisor_output_rejects_out_of_range_salience():
    with pytest.raises(ValidationError):
        SkillpathCompletionAdvisorOutput(
            suggested_mastery_status=MasteryStatus.MASTERED,
            mastery_signal_salience=1.5,
            signal_strength="strong",
            reasoning="x",
        )


def test_completion_advisor_output_rejects_invalid_signal_strength():
    with pytest.raises(ValidationError):
        SkillpathCompletionAdvisorOutput(
            suggested_mastery_status=MasteryStatus.PRACTICING,
            mastery_signal_salience=0.5,
            signal_strength="extreme",
            reasoning="x",
        )


def test_completion_advisor_prompt_contains_evidence_and_mastered_rule():
    from app.advisors import memory_advisors

    prompt = memory_advisors.build_skillpath_completion_prompt(
        _skillpath(),
        _mastery(),
        [_attempt(AttemptCorrectness.CORRECT), _attempt(AttemptCorrectness.INCORRECT)],
    )
    # Skillpath content
    assert "Async fundamentals" in prompt
    assert "await_usage" in prompt
    # Mastery evidence
    assert "practicing" in prompt.lower()
    # Attempt correctness summary present
    assert "correct" in prompt.lower()
    # The mastered-requires-evidence instruction
    assert "mastered" in prompt.lower()


@pytest.mark.asyncio
async def test_completion_advisor_parses_structured_response_from_fake_agent():
    from app.advisors import memory_advisors

    class FakeAgent:
        async def ainvoke(self, _payload):
            return {
                "structured_response": {
                    "suggested_mastery_status": "practicing",
                    "mastery_signal_salience": 0.55,
                    "signal_strength": "moderate",
                    "reasoning": "One correct, one incorrect attempt.",
                }
            }

    out = await memory_advisors.advise_skillpath_completion(
        _skillpath(),
        _mastery(),
        [_attempt(AttemptCorrectness.CORRECT)],
        agent_factory=lambda **_kwargs: FakeAgent(),
    )
    assert out.suggested_mastery_status is MasteryStatus.PRACTICING
    assert out.mastery_signal_salience == 0.55
    assert out.signal_strength == "moderate"


# ----------------------------------------------------------------------------
# Service tests (DB-backed; deterministic/injected advisor — no live LLM)
# ----------------------------------------------------------------------------

from uuid import uuid4  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.model import (  # noqa: E402
    Base,
    CodingProblemAttemptModel,
    LearnerMemoryNoteModel,
    MilestoneModel,
    RoadmapModel,
    SkillMasteryStateModel,
    SkillPathModel,
    UserModel,
)
from app.schema.enums import MemoryStatus, MemoryType  # noqa: E402
from app.services import learning_memory as lm_service  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


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
async def seeded(db_session):
    user_id = f"complete-itest-{uuid4()}"
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    skillpath_id = f"sp-complete-{uuid4()}"
    db_session.add(UserModel(user_id=user_id))
    db_session.add(
        RoadmapModel(
            roadmap_id=roadmap_id,
            user_id=user_id,
            version=1,
            summary="Completion test roadmap",
            target_outcome="Validate completion flow",
            assumptions=[],
        )
    )
    db_session.add(
        MilestoneModel(
            milestone_id=milestone_id,
            roadmap_id=roadmap_id,
            title="Async",
            description="m",
            objective="o",
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
            title="Async fundamentals",
            description="Learn async/await.",
            estimated_hours=1.0,
            prerequisite_skillpath_ids=[],
            learning_objectives=["asyncio.basics", "await_usage"],
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
        yield user_id, skillpath_id
    finally:
        for model, col in (
            (CodingProblemAttemptModel, "user_id"),
            (SkillMasteryStateModel, "user_id"),
            (LearnerMemoryNoteModel, "user_id"),
        ):
            await db_session.execute(
                delete(model).where(getattr(model, col) == user_id)
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


def _seed_attempt(db_session, user_id, skillpath_id, correctness):
    db_session.add(
        CodingProblemAttemptModel(
            attempt_id=f"att-{uuid4()}",
            user_id=user_id,
            skillpath_id=skillpath_id,
            content_id="c-1",
            submitted_code="async def f(): ...",
            language="python",
            correctness=correctness.value,
            feedback_summary="ok",
            detected_concepts=["asyncio.basics"],
            detected_mistakes=[],
            compile_error=None,
            runtime_error=None,
            score=None,
            test_results=[],
            submitted_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )


def _advisor_returning(status, salience=0.9, strength="strong"):
    async def _advisor(skillpath, mastery_state, attempts):
        return SkillpathCompletionAdvisorOutput(
            suggested_mastery_status=status,
            mastery_signal_salience=salience,
            signal_strength=strength,
            reasoning="test",
        )

    return _advisor


async def _mastery_status(db_session, user_id, skillpath_id):
    row = (
        await db_session.execute(
            select(SkillMasteryStateModel).where(
                SkillMasteryStateModel.user_id == user_id,
                SkillMasteryStateModel.skillpath_id == skillpath_id,
            )
        )
    ).scalar_one_or_none()
    return row.status if row else None


async def _mastery_signal_count(db_session, user_id):
    rows = (
        (
            await db_session.execute(
                select(LearnerMemoryNoteModel).where(
                    LearnerMemoryNoteModel.user_id == user_id,
                    LearnerMemoryNoteModel.memory_type
                    == MemoryType.MASTERY_SIGNAL.value,
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


@pytest.mark.asyncio
async def test_mark_completed_sets_skillpath_status_completed(seeded, db_session):
    user_id, skillpath_id = seeded
    result = await lm_service.mark_skillpath_completed(
        user_id,
        skillpath_id,
        db_session,
        completion_advisor=_advisor_returning(MasteryStatus.PRACTICING),
    )
    assert result.skillpath.status == "completed"


@pytest.mark.asyncio
async def test_no_attempts_blocks_mastered(seeded, db_session):
    user_id, skillpath_id = seeded
    await lm_service.mark_skillpath_completed(
        user_id,
        skillpath_id,
        db_session,
        completion_advisor=_advisor_returning(MasteryStatus.MASTERED),
    )
    assert await _mastery_status(db_session, user_id, skillpath_id) == "practicing"


@pytest.mark.asyncio
async def test_correct_attempt_honors_mastered(seeded, db_session):
    user_id, skillpath_id = seeded
    _seed_attempt(db_session, user_id, skillpath_id, AttemptCorrectness.CORRECT)
    await db_session.commit()
    await lm_service.mark_skillpath_completed(
        user_id,
        skillpath_id,
        db_session,
        completion_advisor=_advisor_returning(MasteryStatus.MASTERED),
    )
    assert await _mastery_status(db_session, user_id, skillpath_id) == "mastered"


@pytest.mark.asyncio
async def test_all_incorrect_blocks_mastered(seeded, db_session):
    user_id, skillpath_id = seeded
    _seed_attempt(db_session, user_id, skillpath_id, AttemptCorrectness.INCORRECT)
    await db_session.commit()
    await lm_service.mark_skillpath_completed(
        user_id,
        skillpath_id,
        db_session,
        completion_advisor=_advisor_returning(MasteryStatus.MASTERED),
    )
    assert await _mastery_status(db_session, user_id, skillpath_id) == "in_progress"


@pytest.mark.asyncio
async def test_invalid_advisor_output_falls_back_to_practicing(seeded, db_session):
    user_id, skillpath_id = seeded

    async def _broken_advisor(skillpath, mastery_state, attempts):
        raise ValueError("advisor blew up")

    await lm_service.mark_skillpath_completed(
        user_id,
        skillpath_id,
        db_session,
        completion_advisor=_broken_advisor,
    )
    assert await _mastery_status(db_session, user_id, skillpath_id) == "practicing"


@pytest.mark.asyncio
async def test_flag_disabled_uses_deterministic_fallback(
    seeded, db_session, monkeypatch
):
    user_id, skillpath_id = seeded
    monkeypatch.delenv("ENABLE_SKILLPATH_COMPLETION_ADVISOR", raising=False)
    # No completion_advisor injected, flag off -> deterministic fallback, no LLM call.
    result = await lm_service.mark_skillpath_completed(
        user_id, skillpath_id, db_session
    )
    assert result.skillpath.status == "completed"
    assert await _mastery_status(db_session, user_id, skillpath_id) == "practicing"
    assert await _mastery_signal_count(db_session, user_id) == 1


@pytest.mark.asyncio
async def test_idempotent_no_duplicate_mastery_signal(seeded, db_session):
    user_id, skillpath_id = seeded
    # A mastery signal is evidenced by attempts; with evidence the integrity
    # lifecycle deterministically dedups (update_existing) on repeat completion.
    _seed_attempt(db_session, user_id, skillpath_id, AttemptCorrectness.CORRECT)
    await db_session.commit()
    advisor = _advisor_returning(MasteryStatus.PRACTICING)
    await lm_service.mark_skillpath_completed(
        user_id, skillpath_id, db_session, completion_advisor=advisor
    )
    await lm_service.mark_skillpath_completed(
        user_id, skillpath_id, db_session, completion_advisor=advisor
    )
    assert await _mastery_signal_count(db_session, user_id) == 1


@pytest.mark.asyncio
async def test_mcp_tool_delegates_to_service(monkeypatch):
    """The MCP tool calls the service with the provided args."""
    import app.mcp.tools.learning_memory as mcp_tools

    captured = {}

    async def _fake_service(user_id, skillpath_id, session):
        captured["args"] = (user_id, skillpath_id)
        return object()

    monkeypatch.setattr(
        mcp_tools.service, "mark_skillpath_completed", _fake_service, raising=False
    )

    await mcp_tools.mark_skillpath_completed(user_id="u-1", skillpath_id="sp-1")
    assert captured["args"] == ("u-1", "sp-1")


@pytest.mark.asyncio
async def test_active_error_pattern_moves_to_watch_on_completion(seeded, db_session):
    """A mastery_signal conflicting with an active error_pattern (same scope)
    moves the error_pattern to watch via the integrity lifecycle (deterministic).
    """
    user_id, skillpath_id = seeded
    db_session.add(
        LearnerMemoryNoteModel(
            memory_id=f"note-{uuid4()}",
            user_id=user_id,
            memory_type=MemoryType.ERROR_PATTERN.value,
            title="Forgets await",
            summary="Learner forgets await on async calls.",
            tags=["await"],
            linked_concepts=["await_usage"],
            linked_skillpath_ids=[skillpath_id],
            linked_content_ids=[],
            evidence_attempt_ids=[],
            embedding=None,
            search_text="forgets await",
            salience_score=0.8,
            status=MemoryStatus.ACTIVE.value,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await db_session.commit()

    await lm_service.mark_skillpath_completed(
        user_id,
        skillpath_id,
        db_session,
        completion_advisor=_advisor_returning(MasteryStatus.PRACTICING),
    )

    rows = (
        (
            await db_session.execute(
                select(LearnerMemoryNoteModel).where(
                    LearnerMemoryNoteModel.user_id == user_id,
                    LearnerMemoryNoteModel.memory_type
                    == MemoryType.ERROR_PATTERN.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows, "error_pattern note should still exist"
    assert all(r.status == MemoryStatus.WATCH.value for r in rows)
