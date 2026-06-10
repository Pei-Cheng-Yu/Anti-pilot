"""Live LLM tests for skillpath completion and planner memory injection.

These exercise the REAL advisors / LLM (no injected fakes), against the real DB.
They are gated and skipped by default. To run:

    cd backend
    RUN_LIVE_AGENT_MEMORY_TESTS=1 \
    ENABLE_SKILLPATH_COMPLETION_ADVISOR=1 \
    ENABLE_MEMORY_INTEGRITY_ADVISOR=1 \
    GOOGLE_API_KEY=... \
    ../venv/bin/python -m pytest tests/test_live_planner_completion_memory.py -q -s

Each test seeds memory/attempts/skillpaths, runs the real workflow, asserts the
observable DB + return-value effects, then cleans up. Watch LangSmith for the
advisor reasoning (see the module docstring assertions for what to expect).
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db import session as db_session_module
from app.db.model import (
    CodingProblemAttemptModel,
    LearnerMemoryNoteModel,
    MilestoneModel,
    RoadmapModel,
    SkillMasteryStateModel,
    SkillPathModel,
    UserModel,
)
from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.schema.entities import AddMemoryNoteInput, GoalSpec, LearningProfile
from app.schema.enums import AttemptCorrectness, MasteryStatus, MemoryStatus, MemoryType
from app.services import learning_memory as learning_memory_service
from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

pytestmark = pytest.mark.live_llm

_ZERO_EMBEDDING = [0.0] * 3072


def _skip_unless_live_enabled() -> None:
    if os.getenv("RUN_LIVE_AGENT_MEMORY_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_AGENT_MEMORY_TESTS=1 to run live LLM tests.")
    if not any(
        os.getenv(name)
        for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
    ):
        pytest.skip("Set Google/Gemini API credentials to run live LLM tests.")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ===========================================================================
# Test 1: live skillpath completion workflow
# ===========================================================================


async def _seed_completion() -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    user_id = f"live-complete-{uuid4()}"
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    skillpath_id = f"sp-complete-{uuid4()}"
    error_note_id = f"mem-err-{uuid4()}"
    now = _now()

    async with sf() as session:
        session.add(UserModel(user_id=user_id))
        session.add(
            RoadmapModel(
                roadmap_id=roadmap_id,
                user_id=user_id,
                version=1,
                summary="Live completion roadmap",
                target_outcome="Verify completion workflow",
                assumptions=[],
            )
        )
        session.add(
            MilestoneModel(
                milestone_id=milestone_id,
                roadmap_id=roadmap_id,
                title="Async fundamentals",
                description="async/await",
                objective="Use await correctly",
                estimated_hours=4.0,
                order_index=1,
                dependency_titles=[],
                prerequisite_milestone_ids=[],
                status="generated",
                need_modification=False,
                revision_reason=None,
            )
        )
        session.add(
            SkillPathModel(
                skillpath_id=skillpath_id,
                milestone_id=milestone_id,
                title="Async/await in Python",
                description="Write and await coroutines correctly.",
                estimated_hours=2.0,
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
        # Flush so the skillpath row exists before inserting attempts/notes that
        # FK-reference it (no ORM relationship defines the insert order otherwise).
        await session.flush()
        # One correct + one incorrect attempt → "mastered" is permitted by the guard
        # (it requires >=1 correct attempt), but the advisor judges actual strength.
        session.add(
            CodingProblemAttemptModel(
                attempt_id=f"att-correct-{uuid4()}",
                user_id=user_id,
                skillpath_id=skillpath_id,
                content_id="cp-1",
                submitted_code="async def f():\n    return await g()",
                language="python",
                correctness=AttemptCorrectness.CORRECT.value,
                feedback_summary="Correct use of await.",
                detected_concepts=["asyncio.basics", "await_usage"],
                detected_mistakes=[],
                compile_error=None,
                runtime_error=None,
                score=0.95,
                test_results=[],
                submitted_at=now,
            )
        )
        session.add(
            CodingProblemAttemptModel(
                attempt_id=f"att-wrong-{uuid4()}",
                user_id=user_id,
                skillpath_id=skillpath_id,
                content_id="cp-1",
                submitted_code="def f():\n    return g()",
                language="python",
                correctness=AttemptCorrectness.INCORRECT.value,
                feedback_summary="Missing await; coroutine not awaited.",
                detected_concepts=["await_usage"],
                detected_mistakes=["missing await"],
                compile_error=None,
                runtime_error="coroutine was never awaited",
                score=0.2,
                test_results=[],
                submitted_at=now,
            )
        )
        # An active error_pattern note scoped to the same skillpath/concepts. The
        # mastery_signal write should conflict with it → executor moves it to watch.
        session.add(
            LearnerMemoryNoteModel(
                memory_id=error_note_id,
                user_id=user_id,
                memory_type=MemoryType.ERROR_PATTERN.value,
                title="Forgets await on coroutines",
                summary="Learner forgets to await coroutine-producing calls.",
                tags=["async", "await"],
                linked_concepts=["await_usage"],
                linked_skillpath_ids=[skillpath_id],
                linked_content_ids=[],
                evidence_attempt_ids=[],
                embedding=_ZERO_EMBEDDING,
                search_text="forgets await coroutine async await_usage",
                salience_score=0.9,
                status=MemoryStatus.ACTIVE.value,
                created_at=now,
                last_seen_at=now,
            )
        )
        await session.commit()
    await engine.dispose()
    return {
        "user_id": user_id,
        "roadmap_id": roadmap_id,
        "milestone_id": milestone_id,
        "skillpath_id": skillpath_id,
        "error_note_id": error_note_id,
    }


async def _run_completion(seed: dict):
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as session:
        result = await learning_memory_service.mark_skillpath_completed(
            seed["user_id"], seed["skillpath_id"], session
        )
        # Re-read the error_pattern note's status from the DB.
        err = (
            await session.execute(
                select(LearnerMemoryNoteModel).where(
                    LearnerMemoryNoteModel.memory_id == seed["error_note_id"]
                )
            )
        ).scalar_one()
        err_status = err.status
    await engine.dispose()
    return result, err_status


async def _cleanup(seed: dict) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    user_id = seed["user_id"]
    async with sf() as session:
        for model in (
            CodingProblemAttemptModel,
            SkillMasteryStateModel,
            LearnerMemoryNoteModel,
        ):
            await session.execute(delete(model).where(model.user_id == user_id))
        await session.execute(
            delete(SkillPathModel).where(
                SkillPathModel.skillpath_id == seed["skillpath_id"]
            )
        )
        await session.execute(
            delete(MilestoneModel).where(
                MilestoneModel.milestone_id == seed["milestone_id"]
            )
        )
        await session.execute(
            delete(RoadmapModel).where(RoadmapModel.roadmap_id == seed["roadmap_id"])
        )
        await session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await session.commit()
    await engine.dispose()


def test_live_mark_skillpath_completed_full_workflow(monkeypatch):
    _skip_unless_live_enabled()
    monkeypatch.setenv("ENABLE_SKILLPATH_COMPLETION_ADVISOR", "1")

    seed = asyncio.run(_seed_completion())
    try:
        result, err_status = asyncio.run(_run_completion(seed))

        # 1. Skillpath always marked completed.
        assert result.skillpath.status == "completed"
        # 2. The real advisor ran (flag enabled + credentials present).
        assert result.advisor_used is True
        # 3. Mastery status is a valid enum value; guard allows mastered only
        #    because a correct attempt exists (we seeded one).
        assert result.mastery_state.status in set(MasteryStatus)
        # 4. A mastery_signal note was written with a salience in range.
        assert result.mastery_signal.memory_type == MemoryType.MASTERY_SIGNAL
        assert 0.0 <= result.mastery_signal.salience_score <= 1.0
        # 5. The conflicting error_pattern went through the integrity lifecycle.
        #    With the LLM integrity advisor ON, whether it moves to `watch` is the
        #    advisor's pedagogical call (mastering the skillpath broadly does not
        #    necessarily resolve a specific mistake), so we accept active or watch.
        #    The deterministic FLAG_CONFLICT -> watch guarantee is asserted in the
        #    offline unit test test_active_error_pattern_moves_to_watch_on_completion.
        assert err_status in {MemoryStatus.ACTIVE.value, MemoryStatus.WATCH.value}
        print(f"\n[live] error_pattern status after completion: {err_status}")
        print(
            f"[live] suggested_mastery={result.mastery_state.status.value} "
            f"salience={result.mastery_signal.salience_score} "
            f"advisor_used={result.advisor_used}"
        )
    finally:
        asyncio.run(_cleanup(seed))


# ===========================================================================
# Test 2: live roadmap generation with predefined memory in the DB
# ===========================================================================


async def _seed_planner_memory() -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    user_id = f"live-planner-{uuid4()}"
    # A prior skillpath + mastery state so the linked_skillpath_ids bridge has data.
    prior_roadmap_id = f"roadmap-{uuid4()}"
    prior_milestone_id = f"milestone-{uuid4()}"
    prior_skillpath_id = f"sp-prior-{uuid4()}"
    now = _now()

    async with sf() as session:
        session.add(UserModel(user_id=user_id))
        session.add(
            RoadmapModel(
                roadmap_id=prior_roadmap_id,
                user_id=user_id,
                version=1,
                summary="Prior roadmap",
                target_outcome="prior",
                assumptions=[],
            )
        )
        session.add(
            MilestoneModel(
                milestone_id=prior_milestone_id,
                roadmap_id=prior_roadmap_id,
                title="Python basics",
                description="d",
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
        session.add(
            SkillPathModel(
                skillpath_id=prior_skillpath_id,
                milestone_id=prior_milestone_id,
                title="Python fundamentals",
                description="d",
                estimated_hours=1.0,
                prerequisite_skillpath_ids=[],
                learning_objectives=["python.basics"],
                status="completed",
                need_generation=False,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
                practice_mode=None,
            )
        )
        session.add(
            SkillMasteryStateModel(
                user_id=user_id,
                skillpath_id=prior_skillpath_id,
                status=MasteryStatus.MASTERED.value,
                mastery_score=0.9,
                successful_attempts=4,
                failed_attempts=0,
                strong_concepts=["python.basics", "variables", "loops"],
                weak_concepts=[],
                last_updated_at=now,
            )
        )
        # Persist the structural rows first so add_memory_note (which commits) has
        # the user/skillpath in place.
        await session.commit()

    # Write the predefined notes through the REAL service so each gets a real
    # Google embedding + search_text (exactly like production). Topically distinct
    # notes spanning the goal domain so milestone-level queries differentiate.
    note_inputs = [
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.MASTERY_SIGNAL,
            title="Strong on Python basics",
            summary="Learner has mastered Python fundamentals: variables, loops, and functions.",
            tags=["python", "basics", "variables", "loops"],
            linked_concepts=["python.basics", "variables", "loops"],
            linked_skillpath_ids=[prior_skillpath_id],
            salience_score=0.95,
        ),
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Struggles with async/await",
            summary="Learner repeatedly forgets to await coroutines and confuses sync vs async code.",
            tags=["async", "await", "asyncio", "concurrency"],
            linked_concepts=["python.async", "await_usage", "concurrency"],
            salience_score=0.9,
        ),
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Confuses HTTP status codes",
            summary="Learner often returns 200 for errors and mixes up 4xx vs 5xx status codes in APIs.",
            tags=["http", "status", "rest", "api"],
            linked_concepts=["http.status_codes", "rest.api", "error_handling"],
            salience_score=0.8,
        ),
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.BACKGROUND,
            title="Comfortable with SQL SELECT queries",
            summary="Learner already writes basic SQL SELECT/JOIN queries from a prior data course.",
            tags=["sql", "database", "select", "join"],
            linked_concepts=["sql.select", "sql.join", "database.basics"],
            salience_score=0.7,
        ),
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.ERROR_PATTERN,
            title="Skips writing tests",
            summary="Learner tends to skip unit tests and struggles with pytest fixtures and assertions.",
            tags=["testing", "pytest", "tdd"],
            linked_concepts=["testing.pytest", "testing.fixtures", "tdd"],
            salience_score=0.75,
        ),
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.HEURISTIC,
            title="Learns best with small incremental exercises",
            summary="Break new backend concepts into small runnable steps; the learner retains more that way.",
            tags=["teaching", "incremental", "pacing"],
            linked_concepts=["teaching.incremental"],
            salience_score=0.65,
        ),
        AddMemoryNoteInput(
            user_id=user_id,
            memory_type=MemoryType.PREFERENCE_SIGNAL,
            title="Prefers concrete examples first",
            summary="Learner prefers a concrete code example before the abstract explanation.",
            tags=["preference", "examples"],
            linked_concepts=["teaching.preference"],
            salience_score=0.7,
        ),
    ]
    async with sf() as session:
        for note_input in note_inputs:
            await learning_memory_service.add_memory_note(note_input, session)
    await engine.dispose()
    return {
        "user_id": user_id,
        "prior_roadmap_id": prior_roadmap_id,
        "prior_milestone_id": prior_milestone_id,
        "prior_skillpath_id": prior_skillpath_id,
    }


async def _cleanup_planner(seed: dict) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    user_id = seed["user_id"]
    async with sf() as session:
        for model in (SkillMasteryStateModel, LearnerMemoryNoteModel):
            await session.execute(delete(model).where(model.user_id == user_id))
        # The planner-generated roadmap (if persisted) plus the seeded prior one.
        await session.execute(
            delete(SkillPathModel).where(
                SkillPathModel.skillpath_id == seed["prior_skillpath_id"]
            )
        )
        await session.execute(
            delete(MilestoneModel).where(
                MilestoneModel.milestone_id == seed["prior_milestone_id"]
            )
        )
        await session.execute(
            delete(RoadmapModel).where(RoadmapModel.user_id == user_id)
        )
        await session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await session.commit()
    await engine.dispose()


def _planner_goal() -> GoalSpec:
    return GoalSpec(
        title="Become a Python backend developer",
        description=(
            "Go from Python fundamentals to building async backend services with "
            "FastAPI and databases."
        ),
        target_outcome="Build a production-style async FastAPI backend.",
        deadline=date(2026, 12, 31),
        criteria=["Build async APIs", "Use a database", "Write tests"],
        constraints=["6 hours per week"],
    )


def _planner_profile() -> LearningProfile:
    return LearningProfile(
        baseline_level="intermediate",
        prior_knowledges=["Python basics"],
        weak_areas=["async programming"],
        pace_preference="balanced",
        confidence_level="medium",
        needs_recap=False,
        prefers_examples_first=True,
        overload_risk="low",
    )


def test_live_planner_injects_predefined_memory(monkeypatch):
    _skip_unless_live_enabled()

    seed = asyncio.run(_seed_planner_memory())
    try:
        # Dispose the shared engine so the graph's per-node asyncio.run gets a
        # clean event loop / connection (mirrors the content-graph live test).
        asyncio.run(db_session_module.engine.dispose())

        graph = build_planner_graph()
        result = graph.invoke(
            {
                "goal_spec": _planner_goal(),
                "learning_profile": _planner_profile(),
                "user_id": seed["user_id"],
            }
        )

        # The graph ran end to end.
        assert result.get("milestones"), "planner should generate milestones"
        assert result.get("skillpaths"), "planner should generate skillpaths"

        # Goal-level memory was retrieved and stored in state.
        goal_ctx = result.get("goal_memory_context")
        assert goal_ctx is not None, "goal_memory_context should be populated"
        # The seeded notes are retrievable (keyword/scope), so at least one bucket
        # is non-empty.
        all_notes = (
            goal_ctx.relevant_notes
            + goal_ctx.active_error_patterns
            + goal_ctx.mastery_signals
            + goal_ctx.background_notes
        )
        assert all_notes, "seeded notes should surface in goal-level retrieval"

        # The linked_skillpath_ids bridge surfaced the prior skillpath's mastery
        # state even though no skillpath_id was supplied to retrieval.
        assert seed["prior_skillpath_id"] in goal_ctx.linked_mastery_states

        # Milestone-level contexts were accumulated via the reducer (one per
        # milestone that ran a worker).
        assert isinstance(result.get("milestone_memory_contexts"), dict)
    finally:
        asyncio.run(_cleanup_planner(seed))
