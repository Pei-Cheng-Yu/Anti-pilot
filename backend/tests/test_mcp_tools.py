"""
Tests for MCP tools using FastMCP's in-memory client.
No running server needed — connects directly to the mcp instance.

Run with:
    pytest backend/tests/test_mcp_tools.py -v

Requires:
    pip install pytest pytest-asyncio
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from app.mcp.server import mcp
from app.mcp.tools import learning_memory as learning_memory_tools
from app.schema.entities import (
    CodeCorrectionResult,
    CodeSubmissionResult,
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    MilestoneWithSkillPaths,
    RoadmapFull,
    SkillPathItem,
)
from app.schema.enums import AttemptCorrectness
from app.services import memory_service
from app.validators.schemas import CodeValidationResult
from fastmcp import Client

# --- Fixtures ---


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


# --- Helpers ---


def result_data(result):
    def unwrap(value):
        if value is None:
            return None
        if hasattr(value, "root"):
            return unwrap(value.root)
        if hasattr(value, "model_dump"):
            return unwrap(value.model_dump(mode="json"))
        if isinstance(value, dict):
            if "result" in value and len(value) == 1:
                return unwrap(value["result"])
            return {k: unwrap(v) for k, v in value.items()}
        if isinstance(value, list):
            return [unwrap(v) for v in value]
        return value

    return unwrap(result.structured_content)


def make_goal() -> GoalSpec:
    return GoalSpec(
        title="Learn FastAPI",
        description="Build REST APIs with FastAPI from scratch.",
        target_outcome="Build a production-style FastAPI project.",
        deadline=date(2026, 6, 30),
        criteria=["Can build CRUD endpoints", "Understands validation"],
        constraints=["6 hours per week"],
    )


def make_profile() -> LearningProfile:
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


def make_roadmap_full() -> RoadmapFull:
    sp = SkillPathItem(
        skillpath_id="sp-001",
        milestone_id="m-001",
        title="HTTP Basics",
        description="Learn HTTP fundamentals",
        estimated_hours=3.0,
        status="ready",
        need_generation=True,
        need_modification=False,
    )
    m = MilestoneWithSkillPaths(
        milestone_id="m-001",
        roadmap_uuid="roadmap-abc",
        title="Foundations",
        description="Core concepts",
        objective="Understand HTTP and Python async",
        estimated_hours=10.0,
        order_index=1,
        skillpaths=[sp],
    )
    return RoadmapFull(
        roadmap_id="roadmap-abc",
        version=1,
        summary="FastAPI learning roadmap",
        target_outcome="Build a production-style FastAPI project.",
        milestones=[m],
    )


def make_milestone_item() -> MilestoneItem:
    return MilestoneItem(
        roadmap_uuid="roadmap-abc",
        milestone_id="m-001",
        title="Foundations",
        description="Core concepts",
        objective="Understand HTTP and Python async",
        estimated_hours=10.0,
        order_index=1,
        status="ready",
    )


def make_skillpath_item() -> SkillPathItem:
    return SkillPathItem(
        skillpath_id="sp-001",
        milestone_id="m-001",
        title="HTTP Basics",
        description="Learn HTTP fundamentals",
        estimated_hours=3.0,
        status="ready",
        need_generation=True,
        need_modification=False,
    )


# --- Tool registration ---


async def test_all_tools_registered(client: Client):
    tools = await client.list_tools()
    names = {t.name for t in tools}

    expected = {
        "code_correction_submit_code_attempt",
        "code_correction_process_code_correction",
        "goal_save_goal",
        "goal_get_goal",
        "learning_profile_save_learning_profile",
        "learning_profile_get_learning_profile",
        "roadmap_get_roadmap_full",
        "roadmap_update_milestone",
        "roadmap_update_skillpath",
    }
    assert expected.issubset(names)


def test_learning_memory_mcp_uses_public_memory_service():
    assert learning_memory_tools.service is memory_service
    assert not hasattr(learning_memory_tools, "hint_service")


async def test_submit_code_attempt_tool_accepts_validation_request(client: Client):
    validation = CodeValidationResult(
        correctness=AttemptCorrectness.RUNTIME_ERROR,
        has_serious_blocker=True,
        blocker_reason="Un-awaited coroutine",
        runtime_error="RuntimeWarning: coroutine was never awaited",
        validation_strategy="fake_validator",
        feedback_summary="Missing await.",
        detected_concepts=["fastapi.async"],
        detected_mistakes=["missing await"],
        confidence_score=0.9,
    )
    correction = CodeCorrectionResult(
        inferred_correctness=AttemptCorrectness.RUNTIME_ERROR,
        feedback_summary="Missing await.",
        retrieval_context={
            "recent_attempts": [],
            "active_error_patterns": [],
            "mastery_signals": [],
            "teaching_heuristics": [],
            "background_notes": [],
            "relevant_notes": [],
        },
        persistence_result={
            "attempt": {
                "attempt_id": "attempt-1",
                "user_id": "user-123",
                "skillpath_id": "sp-1",
                "content_id": "cp-1",
                "submitted_code": "async def route(): pass",
                "language": "python",
                "correctness": "runtime_error",
                "feedback_summary": "Missing await.",
                "detected_concepts": ["fastapi.async"],
                "detected_mistakes": ["missing await"],
                "test_results": [],
                "submitted_at": "2026-05-19T00:00:00",
            },
            "updated_notes": [],
        },
        suggested_focus=["missing await"],
    )
    submission = CodeSubmissionResult(validation=validation, correction=correction)

    with patch(
        "app.services.code_correction.submit_code_attempt",
        new=AsyncMock(return_value=submission),
    ) as submit:
        result = await client.call_tool(
            "code_correction_submit_code_attempt",
            {
                "request": {
                    "user_id": "user-123",
                    "skillpath_id": "sp-1",
                    "content_id": "cp-1",
                    "language": "python",
                    "coding_problem_prompt": "Await fetch_user().",
                    "submitted_code": "async def route(): pass",
                    "runtime_error": "RuntimeWarning: coroutine was never awaited",
                }
            },
        )

    submit.assert_awaited_once()
    data = result_data(result)
    assert data["validation"]["validation_strategy"] == "fake_validator"
    assert data["correction"]["inferred_correctness"] == "runtime_error"


# --- Goal tools ---


async def test_save_goal(client: Client):
    goal = make_goal()

    with patch("app.services.goal.save_goal", new=AsyncMock(return_value=goal)):
        result = await client.call_tool(
            "goal_save_goal",
            {
                "user_id": "user-123",
                "goal": goal.model_dump(mode="json"),
            },
        )
        data = result_data(result)
        assert data["title"] == "Learn FastAPI"
        assert data["criteria"] == [
            "Can build CRUD endpoints",
            "Understands validation",
        ]


async def test_get_goal(client: Client):
    goal = make_goal()

    with patch("app.services.goal.get_goal", new=AsyncMock(return_value=goal)):
        result = await client.call_tool("goal_get_goal", {"user_id": "user-123"})
        data = result_data(result)
        assert data["title"] == "Learn FastAPI"
        assert data["target_outcome"] == "Build a production-style FastAPI project."


async def test_get_goal_not_found(client: Client):
    with patch(
        "app.services.goal.get_goal",
        new=AsyncMock(side_effect=ValueError("No goal found for user unknown")),
    ):
        with pytest.raises(Exception, match="No goal found"):
            await client.call_tool("goal_get_goal", {"user_id": "unknown"})


# --- Learning profile tools ---


async def test_save_learning_profile(client: Client):
    profile = make_profile()

    with patch(
        "app.services.learning_profile.save_learning_profile",
        new=AsyncMock(return_value=profile),
    ):
        result = await client.call_tool(
            "learning_profile_save_learning_profile",
            {
                "user_id": "user-123",
                "profile": profile.model_dump(mode="json"),
            },
        )
        data = result_data(result)
        assert data["baseline_level"] == "intermediate"
        assert data["pace_preference"] == "balanced"


async def test_get_learning_profile(client: Client):
    profile = make_profile()

    with patch(
        "app.services.learning_profile.get_learning_profile",
        new=AsyncMock(return_value=profile),
    ):
        result = await client.call_tool(
            "learning_profile_get_learning_profile", {"user_id": "user-123"}
        )
        data = result_data(result)
        assert data["overload_risk"] == "low"
        assert data["prefers_examples_first"] is True


# --- Roadmap tools ---


async def test_get_roadmap_full(client: Client):
    roadmap = make_roadmap_full()

    with patch(
        "app.services.roadmap.get_roadmap_full", new=AsyncMock(return_value=roadmap)
    ):
        result = await client.call_tool(
            "roadmap_get_roadmap_full",
            {
                "user_id": "user-123",
                "roadmap_id": "roadmap-abc",
            },
        )
        data = result_data(result)
        assert data["roadmap_id"] == "roadmap-abc"
        assert len(data["milestones"]) == 1
        assert data["milestones"][0]["title"] == "Foundations"
        assert data["milestones"][0]["skillpaths"][0]["title"] == "HTTP Basics"


async def test_update_milestone(client: Client):
    updated = make_milestone_item()
    updated.objective = "Understand HTTP, routing, and async patterns in Python"

    with patch(
        "app.services.roadmap.update_milestone", new=AsyncMock(return_value=updated)
    ):
        result = await client.call_tool(
            "roadmap_update_milestone",
            {
                "user_id": "user-123",
                "milestone_id": "m-001",
                "objective": "Understand HTTP, routing, and async patterns in Python",
            },
        )
        data = result_data(result)
        assert "async patterns" in data["objective"]


async def test_update_skillpath_hours(client: Client):
    updated = make_skillpath_item()
    updated.estimated_hours = 2.0

    with patch(
        "app.services.roadmap.update_skillpath", new=AsyncMock(return_value=updated)
    ):
        result = await client.call_tool(
            "roadmap_update_skillpath",
            {
                "user_id": "user-123",
                "skillpath_id": "sp-001",
                "estimated_hours": 2.0,
            },
        )
        data = result_data(result)
        assert data["estimated_hours"] == 2.0
