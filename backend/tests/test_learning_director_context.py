from datetime import date
from types import SimpleNamespace

import pytest
from app.langgraph.learning_director import agent as learning_director_agent
from app.langgraph.learning_director.agent import (
    create_learning_director,
    inject_user_id,
    run_content_generator,
    run_planner,
    tool_goal_id,
    tool_user_id,
)
from app.schema.entities import GoalSpec, LearningProfile
from langchain.tools import ToolRuntime


class FakeMCPRequest:
    def __init__(self, *, name: str, args: dict, runtime_context, runtime_state=None):
        self.name = name
        self.args = args
        self.runtime = SimpleNamespace(
            context=runtime_context,
            state=runtime_state or {},
        )

    def override(self, *, args: dict):
        return FakeMCPRequest(
            name=self.name,
            args=args,
            runtime_context=self.runtime.context,
            runtime_state=self.runtime.state,
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


def _runtime_with_configurable(configurable: dict) -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=None,
        config={"configurable": configurable},
        stream_writer=lambda _chunk: None,
        tool_call_id=None,
        store=None,
        execution_info=None,
        server_info=None,
    )


def _runtime_with_state_messages(content: str) -> ToolRuntime:
    return ToolRuntime(
        state={"messages": [{"role": "human", "content": content}]},
        context=None,
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


@pytest.mark.asyncio
async def test_learning_director_interceptor_recovers_ids_from_state_messages():
    captured = {}
    request = FakeMCPRequest(
        name="goal_get_goal",
        args={},
        runtime_context=None,
        runtime_state={
            "messages": [
                {
                    "role": "human",
                    "content": (
                        "Please build the roadmap.\n"
                        "CURRENT_USER_ID: user-from-message\n"
                        "CURRENT_GOAL_ID: goal-from-message"
                    ),
                }
            ]
        },
    )

    async def handler(modified_request):
        captured["args"] = modified_request.args
        return {"ok": True}

    result = await inject_user_id(request, handler)

    assert result == {"ok": True}
    assert captured["args"] == {
        "user_id": "user-from-message",
        "goal_id": "goal-from-message",
    }


def test_learning_director_local_tools_recover_ids_from_state_messages():
    runtime = _runtime_with_state_messages(
        "CURRENT_USER_ID: user-from-message\nCURRENT_GOAL_ID: goal-from-message"
    )

    assert tool_user_id(runtime, None) == "user-from-message"
    assert tool_goal_id(runtime, None) == "goal-from-message"


def test_learning_director_local_tools_recover_inline_ids_from_state_messages():
    runtime = _runtime_with_state_messages(
        "Use CURRENT_USER_ID: user-from-message and "
        "CURRENT_GOAL_ID: goal-from-message."
    )

    assert tool_user_id(runtime, None) == "user-from-message"
    assert tool_goal_id(runtime, None) == "goal-from-message"


def test_learning_director_local_tools_recover_ids_from_configurable():
    runtime = _runtime_with_configurable(
        {"user_id": "user-from-config", "goal_id": "goal-from-config"}
    )

    assert tool_user_id(runtime, None) == "user-from-config"
    assert tool_goal_id(runtime, None) == "goal-from-config"


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
async def test_run_planner_resolves_goal_id_from_matching_goal(monkeypatch):
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

    async def fake_resolve_goal_id(user_id, goal):
        captured["resolved_from"] = {"user_id": user_id, "goal": goal}
        return "goal-resolved"

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
    monkeypatch.setattr(
        learning_director_agent,
        "resolve_goal_id_from_saved_goal",
        fake_resolve_goal_id,
    )
    monkeypatch.setattr(learning_director_agent, "get_session", lambda: FakeSession())

    result = await run_planner.ainvoke(
        {
            "goal": _goal(),
            "profile": _profile(),
            "runtime": _runtime_without_context(),
            "user_id": "user-123",
        }
    )

    assert result == {"roadmap_id": "roadmap-123"}
    assert captured["resolved_from"]["user_id"] == "user-123"
    assert captured["saved"]["goal_id"] == "goal-resolved"


@pytest.mark.asyncio
async def test_run_planner_resolves_user_and_goal_from_matching_goal(monkeypatch):
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

    async def fake_resolve_goal_context(goal):
        captured["resolved_from_goal"] = goal
        return "user-resolved", "goal-resolved"

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
    monkeypatch.setattr(
        learning_director_agent,
        "resolve_goal_context_from_saved_goal",
        fake_resolve_goal_context,
    )
    monkeypatch.setattr(learning_director_agent, "get_session", lambda: FakeSession())

    result = await run_planner.ainvoke(
        {
            "goal": _goal(),
            "profile": _profile(),
            "runtime": _runtime_without_context(),
        }
    )

    assert result == {"roadmap_id": "roadmap-123"}
    assert captured["resolved_from_goal"] == _goal()
    assert captured["saved"]["user_id"] == "user-resolved"
    assert captured["saved"]["goal_id"] == "goal-resolved"


@pytest.mark.asyncio
async def test_run_planner_requires_user_id_when_goal_context_cannot_be_resolved(
    monkeypatch,
):
    runtime = _runtime_without_context()

    async def fake_resolve_goal_context(goal):
        raise ValueError("could not resolve")

    monkeypatch.setattr(
        learning_director_agent,
        "resolve_goal_context_from_saved_goal",
        fake_resolve_goal_context,
    )

    with pytest.raises(ValueError, match="could not resolve"):
        await run_planner.ainvoke(
            {
                "goal": _goal(),
                "profile": _profile(),
                "runtime": runtime,
            }
        )


@pytest.mark.asyncio
async def test_run_content_generator_resolves_user_from_roadmap_when_context_missing(
    monkeypatch,
):
    captured = {}

    async def fake_resolve_user_id(roadmap_id):
        captured["resolved_roadmap_id"] = roadmap_id
        return "user-resolved"

    async def fake_get_roadmap_full(user_id, roadmap_id, session):
        captured["get"] = {"user_id": user_id, "roadmap_id": roadmap_id}
        return SimpleNamespace(milestones=[])

    async def fake_save_generated_skillpaths(**kwargs):
        captured["save"] = kwargs

    class FakeContentGenerator:
        def invoke(self, state):
            captured["content_state"] = state
            return {"generated_skillpaths": []}

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(
        learning_director_agent,
        "resolve_user_id_from_roadmap_id",
        fake_resolve_user_id,
    )
    monkeypatch.setattr(
        learning_director_agent.roadmap_service,
        "get_roadmap_full",
        fake_get_roadmap_full,
    )
    monkeypatch.setattr(
        learning_director_agent.roadmap_service,
        "save_generated_skillpaths",
        fake_save_generated_skillpaths,
    )
    monkeypatch.setattr(
        learning_director_agent, "_content_generator", FakeContentGenerator()
    )
    monkeypatch.setattr(learning_director_agent, "get_session", lambda: FakeSession())

    result = await run_content_generator.ainvoke(
        {
            "roadmap_id": "roadmap-123",
            "goal": _goal(),
            "profile": _profile(),
            "runtime": _runtime_without_context(),
        }
    )

    assert result == {
        "roadmap_id": "roadmap-123",
        "generated_skillpath_count": 0,
    }
    assert captured["resolved_roadmap_id"] == "roadmap-123"
    assert captured["get"] == {"user_id": "user-resolved", "roadmap_id": "roadmap-123"}
    assert captured["save"]["user_id"] == "user-resolved"


@pytest.mark.asyncio
async def test_run_content_generator_requires_user_id_when_roadmap_owner_missing(
    monkeypatch,
):
    runtime = _runtime_without_context()

    async def fake_resolve_user_id(roadmap_id):
        raise ValueError("roadmap owner missing")

    monkeypatch.setattr(
        learning_director_agent,
        "resolve_user_id_from_roadmap_id",
        fake_resolve_user_id,
    )

    with pytest.raises(ValueError, match="roadmap owner missing"):
        await run_content_generator.ainvoke(
            {
                "roadmap_id": "roadmap-123",
                "goal": _goal(),
                "profile": _profile(),
                "runtime": runtime,
            }
        )


@pytest.mark.asyncio
async def test_create_learning_director_uses_configured_model(monkeypatch):
    captured_kwargs = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get_tools(self):
            return []

    def fake_create_deep_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setenv(
        "LEARNING_DIRECTOR_MODEL", "google_genai:gemini-3.1-flash-lite-preview"
    )
    monkeypatch.setattr(learning_director_agent, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(
        learning_director_agent, "create_deep_agent", fake_create_deep_agent
    )

    await create_learning_director()

    assert captured_kwargs["model"] == "google_genai:gemini-3.1-flash-lite-preview"
