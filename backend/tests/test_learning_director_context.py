from datetime import date
from types import SimpleNamespace

import pytest
from app.langgraph.learning_director import agent as learning_director_agent
from app.langgraph.learning_director.agent import inject_user_id, run_planner
from app.schema.entities import GoalSpec, LearningProfile
from langchain.tools import ToolRuntime


class FakeMCPRequest:
    def __init__(self, *, name: str, args: dict, runtime_context):
        self.name = name
        self.args = args
        self.runtime = SimpleNamespace(context=runtime_context)

    def override(self, *, args: dict):
        return FakeMCPRequest(
            name=self.name,
            args=args,
            runtime_context=self.runtime.context,
        )


def _runtime_without_context() -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=None,
        config={},
        stream_writer=lambda _chunk: None,
        tool_call_id=None,
        store=None,
        execution_info=None,
        server_info=None,
    )


def _runtime_with_context(context: dict) -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda _chunk: None,
        tool_call_id=None,
        store=None,
        execution_info=None,
        server_info=None,
    )


@pytest.mark.asyncio
async def test_learning_director_interceptor_allows_explicit_user_id_without_context():
    captured = {}
    request = FakeMCPRequest(
        name="goal_get_goal",
        args={"user_id": "user-123"},
        runtime_context=None,
    )

    async def handler(modified_request):
        captured["args"] = modified_request.args
        return {"ok": True}

    result = await inject_user_id(request, handler)

    assert result == {"ok": True}
    assert captured["args"] == {"user_id": "user-123"}


@pytest.mark.asyncio
async def test_learning_director_interceptor_requires_user_id_when_context_missing():
    request = FakeMCPRequest(
        name="goal_get_goal",
        args={},
        runtime_context=None,
    )

    async def handler(_modified_request):
        raise AssertionError("handler should not be called without a user_id")

    with pytest.raises(ValueError, match="user_id"):
        await inject_user_id(request, handler)


def _goal() -> GoalSpec:
    return GoalSpec(
        title="Learn FastAPI",
        description="Build async FastAPI APIs.",
        target_outcome="Ship tested async routes.",
        deadline=date(2026, 7, 1),
        criteria=["Build CRUD APIs"],
        constraints=["Six hours per week"],
    )


def _profile() -> LearningProfile:
    return LearningProfile(
        baseline_level="intermediate",
        prior_knowledges=["Python", "REST"],
        weak_areas=["async database access"],
        pace_preference="balanced",
        confidence_level="medium",
        needs_recap=True,
        prefers_examples_first=True,
        overload_risk="medium",
    )


@pytest.mark.asyncio
async def test_run_planner_accepts_explicit_user_id_without_runtime_context(
    monkeypatch,
):
    captured = {}

    class FakePlanner:
        def invoke(self, state):
            captured["planner_state"] = state
            return {
                "roadmap_id": "roadmap-123",
                "milestones": [],
                "skillpaths": [],
            }

    async def fake_save_roadmap(**kwargs):
        captured["saved"] = kwargs

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(learning_director_agent, "_planner", FakePlanner())
    monkeypatch.setattr(
        learning_director_agent.roadmap_service,
        "save_roadmap",
        fake_save_roadmap,
    )
    monkeypatch.setattr(learning_director_agent, "get_session", lambda: FakeSession())

    runtime = _runtime_without_context()

    result = await run_planner.ainvoke(
        {
            "goal": _goal(),
            "profile": _profile(),
            "runtime": runtime,
            "user_id": "user-123",
            "goal_id": "goal-fastapi",
        }
    )

    assert result == {"roadmap_id": "roadmap-123"}
    assert captured["saved"]["user_id"] == "user-123"
    assert captured["saved"]["goal_id"] == "goal-fastapi"


@pytest.mark.asyncio
async def test_run_planner_uses_goal_id_from_runtime_context(monkeypatch):
    captured = {}

    class FakePlanner:
        def invoke(self, state):
            return {
                "roadmap_id": "roadmap-123",
                "milestones": [],
                "skillpaths": [],
            }

    async def fake_save_roadmap(**kwargs):
        captured["saved"] = kwargs

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(learning_director_agent, "_planner", FakePlanner())
    monkeypatch.setattr(
        learning_director_agent.roadmap_service,
        "save_roadmap",
        fake_save_roadmap,
    )
    monkeypatch.setattr(learning_director_agent, "get_session", lambda: FakeSession())

    result = await run_planner.ainvoke(
        {
            "goal": _goal(),
            "profile": _profile(),
            "runtime": _runtime_with_context(
                {"user_id": "user-123", "goal_id": "goal-fastapi"}
            ),
        }
    )

    assert result == {"roadmap_id": "roadmap-123"}
    assert captured["saved"]["goal_id"] == "goal-fastapi"


@pytest.mark.asyncio
async def test_run_planner_requires_user_id_when_runtime_context_missing():
    runtime = _runtime_without_context()

    with pytest.raises(ValueError, match="user_id"):
        await run_planner.ainvoke(
            {
                "goal": _goal(),
                "profile": _profile(),
                "runtime": runtime,
            }
        )
