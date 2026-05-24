from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.adk_agents.content_generator.agent import generate_skillpath_content
from app.adk_agents.content_generator.schemas import AdkContentGenerationRequest
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
from app.langgraph.content_generation.graphs.generate_learning_content.graph import (
    build_learning_content_graph,
)
from app.schema.entities import (
    ContentGenerationPlan,
    GoalSpec,
    LearnerMemoryNote,
    LearningMemoryContext,
    LearningProfile,
    MilestoneItem,
    SkillPathItem,
    TestCaseResult,
)
from app.schema.enums import AttemptCorrectness, ExampleStyle, MemoryType, PracticeMode
from app.services import code_correction as code_correction_service
from app.validators.deepagent_validator import validate_code_submission
from app.validators.schemas import CodeValidationRequest
from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

pytestmark = pytest.mark.live_llm

FAKE_CONTENT_MARKER = "Short article for the skill path."


def _redacted_json(value) -> str:
    payload = value.model_dump(mode="json")

    def redact(item):
        if isinstance(item, dict):
            return {key: redact(val) for key, val in item.items() if key != "embedding"}
        if isinstance(item, list):
            return [redact(val) for val in item]
        return item

    return json.dumps(redact(payload), indent=2)


def _skip_unless_live_enabled() -> None:
    if os.getenv("RUN_LIVE_AGENT_MEMORY_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_AGENT_MEMORY_TESTS=1 to run live LLM smoke tests.")
    if not any(
        os.getenv(name)
        for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
    ):
        pytest.skip("Set Google/Gemini API credentials to run live LLM smoke tests.")


async def _dispose_shared_db_engine() -> None:
    # LangGraph workers call async DB code through asyncio.run in worker threads.
    # Disposing between live graph invocations prevents asyncpg connections from
    # being reused by a different event loop.
    await db_session_module.engine.dispose()


def _memory_context() -> LearningMemoryContext:
    created_at = datetime.now(timezone.utc)
    async_error = LearnerMemoryNote(
        memory_id="live-mem-fastapi-await",
        user_id="live-memory-user",
        memory_type=MemoryType.ERROR_PATTERN,
        title="FastAPI route missing await",
        summary=(
            "Learner repeatedly forgets to await async database calls in FastAPI "
            "route handlers, causing coroutine runtime warnings."
        ),
        tags=["fastapi", "async", "await", "route"],
        linked_concepts=["fastapi.async", "fastapi.routing", "missing await"],
        linked_skillpath_ids=["sp-live-fastapi-routing"],
        evidence_attempt_ids=["live-attempt-1", "live-attempt-2"],
        salience_score=0.95,
        created_at=created_at,
    )
    heuristic = LearnerMemoryNote(
        memory_id="live-mem-fastapi-await-heuristic",
        user_id="live-memory-user",
        memory_type=MemoryType.HEURISTIC,
        title="Trace async boundaries before returning",
        summary=(
            "When generating practice, include a reminder to mark async functions "
            "and await coroutine-producing calls before returning the response."
        ),
        tags=["fastapi", "async", "teaching"],
        linked_concepts=["fastapi.async", "missing await"],
        linked_skillpath_ids=["sp-live-fastapi-routing"],
        evidence_attempt_ids=["live-attempt-1", "live-attempt-2"],
        salience_score=0.85,
        created_at=created_at,
    )
    return LearningMemoryContext(
        active_error_patterns=[async_error],
        teaching_heuristics=[heuristic],
        relevant_notes=[async_error, heuristic],
    )


def _content_request() -> AdkContentGenerationRequest:
    return AdkContentGenerationRequest(
        goal=GoalSpec(
            title="Learn FastAPI Backend Development",
            description="Build reliable FastAPI APIs with async database access.",
            target_outcome="Implement route handlers that correctly await I/O.",
            deadline=date(2026, 6, 30),
            criteria=["Write async routes", "Handle database calls correctly"],
            constraints=["Prefer hands-on practice"],
        ),
        profile=LearningProfile(
            baseline_level="intermediate",
            prior_knowledges=["Python basics", "HTTP basics"],
            weak_areas=["async programming"],
            pace_preference="balanced",
            confidence_level="medium",
            needs_recap=True,
            prefers_examples_first=True,
            overload_risk="low",
        ),
        milestone=MilestoneItem(
            roadmap_uuid="roadmap-live-memory",
            milestone_id="milestone-live-fastapi",
            title="Build FastAPI APIs",
            description="Implement route handlers and async I/O patterns.",
            objective="Use FastAPI route handlers correctly.",
            estimated_hours=6.0,
            order_index=1,
            status="ready",
        ),
        skillpath=SkillPathItem(
            skillpath_id="sp-live-fastapi-routing",
            milestone_id="milestone-live-fastapi",
            title="FastAPI Async Route Handlers",
            description="Write route handlers that await async database calls.",
            estimated_hours=2.0,
            learning_objectives=["Use await in async FastAPI routes"],
            status="ready",
            need_generation=True,
            practice_mode=PracticeMode.CODING_PROBLEM,
        ),
        content_plan=ContentGenerationPlan(
            article_depth=None,
            example_style=ExampleStyle.EXAMPLE_FIRST,
            include_recap=True,
        ),
        learning_memory_context=_memory_context(),
    )


def _live_goal() -> GoalSpec:
    return GoalSpec(
        title="Learn FastAPI Backend Development",
        description="Build reliable FastAPI APIs with async database access.",
        target_outcome="Implement route handlers that correctly await I/O.",
        deadline=date(2026, 6, 30),
        criteria=["Write async routes", "Handle database calls correctly"],
        constraints=["Prefer hands-on practice"],
    )


def _live_profile() -> LearningProfile:
    return LearningProfile(
        baseline_level="intermediate",
        prior_knowledges=["Python basics", "HTTP basics"],
        weak_areas=["async programming"],
        pace_preference="balanced",
        confidence_level="medium",
        needs_recap=True,
        prefers_examples_first=True,
        overload_risk="low",
    )


async def _seed_live_graph_memory() -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = f"live-graph-memory-{uuid4()}"
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    skillpath_id = f"sp-live-fastapi-routing-{uuid4()}"
    error_memory_id = f"mem-live-fastapi-await-{uuid4()}"
    heuristic_memory_id = f"mem-live-fastapi-await-heuristic-{uuid4()}"

    async with session_factory() as session:
        session.add(UserModel(user_id=user_id))
        session.add(
            RoadmapModel(
                roadmap_id=roadmap_id,
                user_id=user_id,
                version=1,
                summary="Live graph memory smoke roadmap",
                target_outcome="Verify live graph memory retrieval and ADK generation.",
                assumptions=[],
            )
        )
        session.add(
            MilestoneModel(
                milestone_id=milestone_id,
                roadmap_id=roadmap_id,
                title="Build FastAPI APIs",
                description="Implement route handlers and async I/O patterns.",
                objective="Use FastAPI route handlers correctly.",
                estimated_hours=6.0,
                order_index=1,
                dependency_titles=[],
                prerequisite_milestone_ids=[],
                status="ready",
                need_modification=False,
                revision_reason=None,
            )
        )
        session.add(
            SkillPathModel(
                skillpath_id=skillpath_id,
                milestone_id=milestone_id,
                title="FastAPI Async Route Handlers",
                description="Write route handlers that await async database calls.",
                estimated_hours=2.0,
                prerequisite_skillpath_ids=[],
                learning_objectives=[
                    "Use await in async FastAPI routes",
                    "Avoid un-awaited coroutine runtime warnings",
                ],
                status="ready",
                need_generation=True,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
                practice_mode=PracticeMode.CODING_PROBLEM.value,
            )
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        zero_embedding = [0.0] * 3072
        session.add_all(
            [
                LearnerMemoryNoteModel(
                    memory_id=error_memory_id,
                    user_id=user_id,
                    memory_type=MemoryType.ERROR_PATTERN.value,
                    title="FastAPI route missing await",
                    summary=(
                        "Learner repeatedly forgets to await async database calls "
                        "inside FastAPI route handlers."
                    ),
                    tags=["fastapi", "async", "await", "route"],
                    linked_concepts=[
                        "fastapi.async",
                        "fastapi.routing",
                        "missing await",
                    ],
                    linked_skillpath_ids=[skillpath_id],
                    linked_content_ids=["cp-live-fastapi-await"],
                    evidence_attempt_ids=["live-attempt-1", "live-attempt-2"],
                    embedding=zero_embedding,
                    search_text=(
                        "FastAPI route missing await async route handler "
                        "fastapi.async fastapi.routing missing await"
                    ),
                    salience_score=0.95,
                    status="active",
                    created_at=now,
                    last_seen_at=now,
                ),
                LearnerMemoryNoteModel(
                    memory_id=heuristic_memory_id,
                    user_id=user_id,
                    memory_type=MemoryType.HEURISTIC.value,
                    title="Trace async boundaries before returning",
                    summary=(
                        "When generating practice, remind the learner to identify "
                        "coroutine-producing calls and await them before returning."
                    ),
                    tags=["fastapi", "async", "teaching"],
                    linked_concepts=["fastapi.async", "missing await"],
                    linked_skillpath_ids=[skillpath_id],
                    linked_content_ids=[],
                    evidence_attempt_ids=["live-attempt-1", "live-attempt-2"],
                    embedding=zero_embedding,
                    search_text=(
                        "Trace async boundaries await coroutine-producing calls "
                        "fastapi.async missing await"
                    ),
                    salience_score=0.85,
                    status="active",
                    created_at=now,
                    last_seen_at=now,
                ),
            ]
        )
        await session.commit()

    await engine.dispose()
    return {
        "user_id": user_id,
        "roadmap_id": roadmap_id,
        "milestone_id": milestone_id,
        "skillpath_id": skillpath_id,
        "error_memory_id": error_memory_id,
        "heuristic_memory_id": heuristic_memory_id,
    }


async def _cleanup_live_graph_memory(seed: dict) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            delete(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == seed["user_id"]
            )
        )
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
        await session.execute(
            delete(UserModel).where(UserModel.user_id == seed["user_id"])
        )
        await session.commit()
    await engine.dispose()


async def _seed_product_path_memory_flow() -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = f"live-product-memory-{uuid4()}"
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    skillpath_id = f"sp-product-fastapi-routing-{uuid4()}"
    content_id = f"cp-product-fastapi-await-{uuid4()}"

    async with session_factory() as session:
        session.add(UserModel(user_id=user_id))
        session.add(
            RoadmapModel(
                roadmap_id=roadmap_id,
                user_id=user_id,
                version=1,
                summary="Live product-path memory smoke roadmap",
                target_outcome=(
                    "Verify a bad learner attempt creates memory and later "
                    "content generation retrieves it."
                ),
                assumptions=[],
            )
        )
        session.add(
            MilestoneModel(
                milestone_id=milestone_id,
                roadmap_id=roadmap_id,
                title="Build FastAPI APIs",
                description="Implement route handlers and async I/O patterns.",
                objective="Use FastAPI route handlers correctly.",
                estimated_hours=6.0,
                order_index=1,
                dependency_titles=[],
                prerequisite_milestone_ids=[],
                status="ready",
                need_modification=False,
                revision_reason=None,
            )
        )
        session.add(
            SkillPathModel(
                skillpath_id=skillpath_id,
                milestone_id=milestone_id,
                title="FastAPI Async Route Handlers",
                description="Write route handlers that await async database calls.",
                estimated_hours=2.0,
                prerequisite_skillpath_ids=[],
                learning_objectives=[
                    "Use await in async FastAPI routes",
                    "Avoid un-awaited coroutine runtime warnings",
                ],
                status="ready",
                need_generation=True,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
                practice_mode=PracticeMode.CODING_PROBLEM.value,
            )
        )
        await session.commit()

    await engine.dispose()
    return {
        "user_id": user_id,
        "roadmap_id": roadmap_id,
        "milestone_id": milestone_id,
        "skillpath_id": skillpath_id,
        "content_id": content_id,
    }


async def _cleanup_product_path_memory_flow(seed: dict) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            delete(CodingProblemAttemptModel).where(
                CodingProblemAttemptModel.user_id == seed["user_id"]
            )
        )
        await session.execute(
            delete(SkillMasteryStateModel).where(
                SkillMasteryStateModel.user_id == seed["user_id"]
            )
        )
        await session.execute(
            delete(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == seed["user_id"]
            )
        )
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
        await session.execute(
            delete(UserModel).where(UserModel.user_id == seed["user_id"])
        )
        await session.commit()
    await engine.dispose()


async def _run_product_path_bad_attempt(seed: dict):
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        initial_notes = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == seed["user_id"]
            )
        )
        assert list(initial_notes.scalars()) == []

        # Exercise the exposed product boundary without starting the MCP server:
        # validate code, convert validation evidence, persist attempt, update memory.
        submission_result = await code_correction_service.submit_code_attempt(
            CodeValidationRequest(
                user_id=seed["user_id"],
                skillpath_id=seed["skillpath_id"],
                content_id=seed["content_id"],
                language="python",
                coding_problem_prompt=(
                    "Implement an async FastAPI route handler that awaits "
                    "fetch_user() before returning the response."
                ),
                submitted_code=(
                    "async def get_user(user_id: str):\n"
                    "    user = fetch_user(user_id)\n"
                    "    return {'user': user}\n"
                ),
                runtime_error=(
                    "RuntimeWarning: coroutine 'fetch_user' was never awaited"
                ),
                test_results=[
                    TestCaseResult(
                        name="awaits fetch_user",
                        passed=False,
                        message="coroutine was never awaited",
                    )
                ],
                detected_concepts=["fastapi.async", "fastapi.routing"],
                detected_mistakes=["missing await", "unawaited coroutine"],
            ),
            session,
        )

        persisted_attempts = await session.execute(
            select(CodingProblemAttemptModel).where(
                CodingProblemAttemptModel.user_id == seed["user_id"],
                CodingProblemAttemptModel.content_id == seed["content_id"],
            )
        )
        attempts = list(persisted_attempts.scalars())

        persisted_notes = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == seed["user_id"]
            )
        )
        notes = list(persisted_notes.scalars())

    await engine.dispose()
    return submission_result, attempts, notes


async def _run_product_path_success_follow_up(seed: dict):
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        submission_result = await code_correction_service.submit_code_attempt(
            CodeValidationRequest(
                user_id=seed["user_id"],
                skillpath_id=seed["skillpath_id"],
                content_id=seed["content_id"],
                language="python",
                coding_problem_prompt=(
                    "Implement an async FastAPI route handler that awaits "
                    "fetch_user() before returning the response."
                ),
                submitted_code=(
                    "async def get_user(user_id: str):\n"
                    "    user = await fetch_user(user_id)\n"
                    "    return {'user': user}\n"
                ),
                test_results=[
                    TestCaseResult(
                        name="awaits fetch_user",
                        passed=True,
                        message="fetch_user was awaited before returning",
                    )
                ],
            ),
            session,
        )

        persisted_attempts = await session.execute(
            select(CodingProblemAttemptModel)
            .where(
                CodingProblemAttemptModel.user_id == seed["user_id"],
                CodingProblemAttemptModel.content_id == seed["content_id"],
            )
            .order_by(CodingProblemAttemptModel.submitted_at.asc())
        )
        attempts = list(persisted_attempts.scalars())

        persisted_notes = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == seed["user_id"]
            )
        )
        notes = list(persisted_notes.scalars())

    await engine.dispose()
    return submission_result, attempts, notes


def _live_graph_state(seed: dict) -> dict:
    milestone = MilestoneItem(
        roadmap_uuid=seed["roadmap_id"],
        milestone_id=seed["milestone_id"],
        title="Build FastAPI APIs",
        description="Implement route handlers and async I/O patterns.",
        objective="Use FastAPI route handlers correctly.",
        estimated_hours=6.0,
        order_index=1,
        status="ready",
        need_modification=False,
        revision_reason=None,
    )
    skillpath = SkillPathItem(
        skillpath_id=seed["skillpath_id"],
        milestone_id=seed["milestone_id"],
        title="FastAPI Async Route Handlers",
        description="Write route handlers that await async database calls.",
        estimated_hours=2.0,
        prerequisite_skillpath_ids=[],
        learning_objectives=[
            "Use await in async FastAPI routes",
            "Avoid un-awaited coroutine runtime warnings",
        ],
        status="ready",
        need_generation=True,
        need_modification=False,
        practice_mode=PracticeMode.CODING_PROBLEM,
    )
    return {
        "user_id": seed["user_id"],
        "goal_spec": _live_goal(),
        "learning_profile": _live_profile(),
        "milestones": [milestone],
        "skillpaths": [skillpath],
        "content_drafts": [],
        "content_plan": ContentGenerationPlan(
            article_depth=None,
            example_style=ExampleStyle.EXAMPLE_FIRST,
            include_recap=True,
        ),
    }


def test_live_learning_content_graph_retrieves_memory_and_invokes_adk():
    _skip_unless_live_enabled()
    seed = asyncio.run(_seed_live_graph_memory())
    try:
        graph = build_learning_content_graph()
        result = graph.invoke(deepcopy(_live_graph_state(seed)))

        diagnostics = result["learning_memory_retrieval_diagnostics_by_skillpath"]
        memory_contexts = result["learning_memory_contexts_by_skillpath"]
        generated_skillpath = result["generated_skillpaths"][0]
        rendered = generated_skillpath.model_dump_json().lower()

        print("\n=== LIVE GRAPH MEMORY DIAGNOSTICS ===")
        print(diagnostics[seed["skillpath_id"]].model_dump_json(indent=2))
        print("\n=== LIVE GRAPH MEMORY CONTEXT ===")
        print(_redacted_json(memory_contexts[seed["skillpath_id"]]))
        print("\n=== LIVE GRAPH GENERATED CONTENT ===")
        print(rendered[:4000])

        assert diagnostics[seed["skillpath_id"]].status == "retrieved"
        memory_context = memory_contexts[seed["skillpath_id"]]
        assert any(
            note.memory_id == seed["error_memory_id"]
            for note in memory_context.active_error_patterns
        )
        assert FAKE_CONTENT_MARKER.lower() not in rendered
        assert generated_skillpath.learning_contents
        assert any(term in rendered for term in ("await", "async", "route handler"))
    finally:
        asyncio.run(_dispose_shared_db_engine())
        asyncio.run(_cleanup_live_graph_memory(seed))


def test_live_product_path_bad_attempt_creates_memory_then_content_graph_uses_it():
    _skip_unless_live_enabled()
    seed = asyncio.run(_seed_product_path_memory_flow())
    try:
        submission_result, attempts, notes = asyncio.run(
            _run_product_path_bad_attempt(seed)
        )
        correction_result = submission_result.correction

        error_notes = [
            note for note in notes if note.memory_type == MemoryType.ERROR_PATTERN.value
        ]

        print("\n=== LIVE PRODUCT PATH VALIDATION RESULT ===")
        print(_redacted_json(submission_result.validation))
        print("\n=== LIVE PRODUCT PATH CORRECTION RESULT ===")
        print(_redacted_json(correction_result))
        print("\n=== LIVE PRODUCT PATH PERSISTED ATTEMPT ===")
        print(
            json.dumps(
                {
                    "attempt_id": attempts[0].attempt_id,
                    "correctness": attempts[0].correctness,
                    "runtime_error": attempts[0].runtime_error,
                    "detected_concepts": attempts[0].detected_concepts,
                    "detected_mistakes": attempts[0].detected_mistakes,
                },
                indent=2,
            )
        )
        print("\n=== LIVE PRODUCT PATH CREATED MEMORY NOTES ===")
        print(
            json.dumps(
                [
                    {
                        "memory_id": note.memory_id,
                        "memory_type": note.memory_type,
                        "title": note.title,
                        "summary": note.summary,
                        "tags": note.tags,
                        "linked_concepts": note.linked_concepts,
                        "evidence_attempt_ids": note.evidence_attempt_ids,
                    }
                    for note in notes
                ],
                indent=2,
            )
        )

        assert correction_result.inferred_correctness in {
            AttemptCorrectness.INCORRECT,
            AttemptCorrectness.RUNTIME_ERROR,
        }
        assert len(attempts) == 1
        assert attempts[0].attempt_id == (
            correction_result.persistence_result.attempt.attempt_id
        )
        assert error_notes
        assert attempts[0].attempt_id in error_notes[0].evidence_attempt_ids
        assert any(
            term in " ".join(error_notes[0].linked_concepts).lower()
            for term in ("await", "coroutine", "fastapi.async")
        )

        success_result, follow_up_attempts, follow_up_notes = asyncio.run(
            _run_product_path_success_follow_up(seed)
        )
        updated_error_notes = [
            note
            for note in follow_up_notes
            if note.memory_type == MemoryType.ERROR_PATTERN.value
        ]
        watched_note = next(
            note
            for note in updated_error_notes
            if note.memory_id == error_notes[0].memory_id
        )

        print("\n=== LIVE PRODUCT PATH SUCCESS FOLLOW-UP RESULT ===")
        print(_redacted_json(success_result))
        print("\n=== LIVE PRODUCT PATH UPDATED ERROR PATTERN ===")
        print(
            json.dumps(
                {
                    "memory_id": watched_note.memory_id,
                    "status": watched_note.status,
                    "salience_score": watched_note.salience_score,
                    "evidence_attempt_ids": watched_note.evidence_attempt_ids,
                },
                indent=2,
            )
        )

        assert len(follow_up_attempts) == 2
        assert (
            success_result.correction.inferred_correctness == AttemptCorrectness.CORRECT
        )
        assert watched_note.status == "watch"
        assert watched_note.salience_score < error_notes[0].salience_score
        assert follow_up_attempts[-1].attempt_id in watched_note.evidence_attempt_ids

        asyncio.run(_dispose_shared_db_engine())
        graph = build_learning_content_graph()
        result = graph.invoke(deepcopy(_live_graph_state(seed)))

        diagnostics = result["learning_memory_retrieval_diagnostics_by_skillpath"]
        memory_contexts = result["learning_memory_contexts_by_skillpath"]
        generated_skillpath = result["generated_skillpaths"][0]
        rendered = generated_skillpath.model_dump_json().lower()

        print("\n=== LIVE PRODUCT PATH MEMORY DIAGNOSTICS ===")
        print(diagnostics[seed["skillpath_id"]].model_dump_json(indent=2))
        print("\n=== LIVE PRODUCT PATH MEMORY CONTEXT ===")
        print(_redacted_json(memory_contexts[seed["skillpath_id"]]))
        print("\n=== LIVE PRODUCT PATH GENERATED CONTENT ===")
        print(rendered[:4000])

        assert diagnostics[seed["skillpath_id"]].status == "retrieved"
        retrieved_context = memory_contexts[seed["skillpath_id"]]
        assert any(
            note.memory_id == error_notes[0].memory_id
            for note in retrieved_context.active_error_patterns
        )
        retrieved_error = next(
            note
            for note in retrieved_context.active_error_patterns
            if note.memory_id == error_notes[0].memory_id
        )
        assert retrieved_error.status.value == "watch"
        assert FAKE_CONTENT_MARKER.lower() not in rendered
        assert generated_skillpath.learning_contents
        assert any(
            term in rendered
            for term in ("await", "async", "coroutine", "route handler")
        )
    finally:
        asyncio.run(_dispose_shared_db_engine())
        asyncio.run(_cleanup_product_path_memory_flow(seed))


def test_live_content_generation_uses_seeded_memory_context():
    _skip_unless_live_enabled()
    request = _content_request()
    print("\n=== SEEDED LEARNING MEMORY CONTEXT ===")
    print(_redacted_json(request.learning_memory_context))

    output = generate_skillpath_content(request)
    rendered = output.model_dump_json().lower()

    assert output.article.title
    assert output.coding_problem is not None
    assert any(term in rendered for term in ("await", "async", "route handler"))


@pytest.mark.asyncio
async def test_live_validator_uses_external_runtime_evidence():
    _skip_unless_live_enabled()

    result = await validate_code_submission(
        CodeValidationRequest(
            user_id="live-memory-user",
            skillpath_id="sp-live-fastapi-routing",
            content_id="cp-live-fastapi-await",
            language="python",
            coding_problem_prompt=(
                "Implement an async FastAPI route handler that awaits fetch_user()."
            ),
            submitted_code=(
                "async def get_user():\n"
                "    user = fetch_user()\n"
                "    return {'user': user}\n"
            ),
            runtime_error="RuntimeWarning: coroutine 'fetch_user' was never awaited",
            stderr="coroutine 'fetch_user' was never awaited",
            test_results=[
                TestCaseResult(
                    name="awaits fetch_user",
                    passed=False,
                    message="Coroutine was returned without await.",
                )
            ],
        ),
        backend=None,
    )

    rendered = result.model_dump_json().lower()
    assert result.feedback_summary
    assert result.validation_strategy
    assert any(term in rendered for term in ("await", "runtime", "external"))
