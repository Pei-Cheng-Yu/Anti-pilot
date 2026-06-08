from datetime import date
from pathlib import Path

import pytest
from app.langgraph.discovery_agent import agent as discovery_agent
from app.langgraph.discovery_agent import checkpointing
from app.langgraph.discovery_agent.agent import (
    DISCOVERY_MCP_TOOL_ALLOWLIST,
    discovery_get_goal_status,
    discovery_get_learning_profile_status,
    discovery_save_goal,
    filter_discovery_tools,
)
from app.langgraph.discovery_agent.prompts import DISCOVERY_SYSTEM_PROMPT
from app.langgraph.discovery_agent.schemas import (
    DiscoveryContext,
    DiscoveryResponse,
    UIHints,
    parse_discovery_response,
)
from app.schema.entities import GoalSpec, LearningProfile
from langchain.tools import ToolRuntime


class FakeTool:
    def __init__(self, name: str):
        self.name = name


SKILL_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "langgraph"
    / "discovery_agent"
    / "skills"
    / "discovery-agent"
    / "SKILL.md"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_parse_discovery_response_accepts_json_text():
    response = parse_discovery_response(
        '{"message": "What do you want to learn?", "ui_hints": null, "session_complete": false}'
    )

    assert response == DiscoveryResponse(
        message="What do you want to learn?",
        ui_hints=None,
        session_complete=False,
    )


def test_parse_discovery_response_wraps_unstructured_text():
    response = parse_discovery_response("Tell me your target outcome first.")

    assert response.message == "Tell me your target outcome first."
    assert response.ui_hints is None
    assert response.session_complete is False


def test_ui_hints_requires_options_for_choice_types():
    with pytest.raises(ValueError):
        UIHints(type="single_choice", options=[])

    with pytest.raises(ValueError):
        UIHints(type="multi_choice", options=[])

    assert UIHints(type="text_input").options == []
    assert UIHints(type="confirm", options=["Yes", "No"]).options == ["Yes", "No"]


def test_discovery_prompt_mentions_source_of_truth_tools_and_memory_limits():
    required_phrases = [
        "discovery_get_goal_status",
        "discovery_save_goal",
        "discovery_get_learning_profile_status",
        "learning_profile_save_learning_profile",
        "learning_memory_retrieve_learning_memory",
        "learning_memory_add_memory_note",
        "preference_signal",
        "background",
        "Do not write error_pattern",
        "Do not duplicate the whole GoalSpec",
        "one question at a time",
        "start_async_task",
    ]

    for phrase in required_phrases:
        assert phrase in DISCOVERY_SYSTEM_PROMPT


def test_filter_discovery_tools_enforces_exact_allowlist():
    tools = [
        FakeTool("goal_get_goal"),
        FakeTool("goal_save_goal"),
        FakeTool("roadmap_get_roadmap_full"),
        FakeTool("learning_profile_get_learning_profile"),
        FakeTool("learning_profile_save_learning_profile"),
        FakeTool("learning_memory_retrieve_learning_memory"),
        FakeTool("learning_memory_get_skill_mastery_state"),
        FakeTool("learning_memory_add_memory_note"),
        FakeTool("learning_memory_delete_memory_note"),
    ]

    filtered = filter_discovery_tools(tools)

    assert {tool.name for tool in filtered} == DISCOVERY_MCP_TOOL_ALLOWLIST
    assert "goal_get_goal" not in DISCOVERY_MCP_TOOL_ALLOWLIST
    assert "goal_save_goal" not in DISCOVERY_MCP_TOOL_ALLOWLIST
    assert "learning_profile_get_learning_profile" not in DISCOVERY_MCP_TOOL_ALLOWLIST


def test_discovery_skill_runbook_documents_exact_allowed_tools():
    text = _skill_text()

    for tool_name in DISCOVERY_MCP_TOOL_ALLOWLIST:
        assert f"`{tool_name}`" in text


def test_discovery_skill_runbook_documents_prohibited_tools_and_lifecycle_writes():
    text = _skill_text()
    prohibited_phrases = [
        "Do not call planner tools directly",
        "Do not call content generation tools directly",
        "Do not record coding attempts",
        "Do not update memory notes",
        "Do not delete memory notes",
        "Do not resolve memory notes",
        "`error_pattern`",
        "`mastery_signal`",
        "`heuristic`",
    ]

    for phrase in prohibited_phrases:
        assert phrase in text


def test_discovery_skill_runbook_documents_goal_profile_memory_and_handoff_contracts():
    text = _skill_text()
    required_terms = [
        "one question at a time",
        "`DiscoveryResponse`",
        "`GoalSpec`",
        "`title`",
        "`description`",
        "`target_outcome`",
        "`deadline`",
        "`criteria`",
        "`constraints`",
        "`LearningProfile`",
        "`baseline_level`",
        "`prior_knowledges`",
        "`weak_areas`",
        "`pace_preference`",
        "`confidence_level`",
        "`needs_recap`",
        "`prefers_examples_first`",
        "`overload_risk`",
        "`preference_signal`",
        "`background`",
        "session_complete: true",
        "roadmap job id",
        "roadmap status",
    ]

    for term in required_terms:
        assert term in text


def test_discovery_contract_requires_iso_date_deadline_for_goal_tools():
    text = _skill_text()

    assert "ISO 8601 date" in DISCOVERY_SYSTEM_PROMPT
    assert "YYYY-MM-DD" in DISCOVERY_SYSTEM_PROMPT
    assert "ISO 8601 date" in text
    assert "YYYY-MM-DD" in text


def test_discovery_contract_passes_current_user_id_to_learning_director_handoff():
    text = _skill_text()

    assert "CURRENT_USER_ID" in DISCOVERY_SYSTEM_PROMPT
    assert "CURRENT_USER_ID" in text


def test_discovery_context_preserves_conversation_id_for_goal_binding():
    assert "conversation_id" in DiscoveryContext.__optional_keys__


def test_discovery_contract_requires_non_empty_followup_after_missing_entities():
    text = _skill_text()
    required_phrases = [
        "exists: false",
        "normal for a new discovery conversation",
        "Do not return an empty message",
    ]

    for phrase in required_phrases:
        assert phrase in DISCOVERY_SYSTEM_PROMPT
        assert phrase in text


def _runtime(
    user_id: str,
    *,
    goal_id: str | None = None,
    conversation_id: str | None = None,
) -> ToolRuntime:
    context = {"user_id": user_id}
    if goal_id is not None:
        context["goal_id"] = goal_id
    if conversation_id is not None:
        context["conversation_id"] = conversation_id
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


class FakeSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return None


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
async def test_discovery_goal_status_returns_missing_without_throwing(monkeypatch):
    async def fake_get_goal(user_id, session):
        raise ValueError(f"No goal found for user {user_id}")

    monkeypatch.setattr(discovery_agent, "get_session", lambda: FakeSession())
    monkeypatch.setattr(discovery_agent.goal_service, "get_goal", fake_get_goal)

    result = await discovery_get_goal_status.ainvoke({"runtime": _runtime("user-123")})

    assert result == {"exists": False, "goal": None}


@pytest.mark.asyncio
async def test_discovery_goal_status_returns_existing_goal(monkeypatch):
    async def fake_get_goal(user_id, session):
        return _goal()

    monkeypatch.setattr(discovery_agent, "get_session", lambda: FakeSession())
    monkeypatch.setattr(discovery_agent.goal_service, "get_goal", fake_get_goal)

    result = await discovery_get_goal_status.ainvoke({"runtime": _runtime("user-123")})

    assert result["exists"] is True
    assert result["goal"]["title"] == "Learn FastAPI"
    assert result["goal"]["deadline"] == "2026-07-01"


@pytest.mark.asyncio
async def test_discovery_save_goal_generates_goal_id_and_binds_conversation(
    monkeypatch,
):
    captured = {}

    async def fake_save_goal(user_id, goal, session, goal_id=None):
        captured["save"] = {
            "user_id": user_id,
            "goal": goal,
            "goal_id": goal_id,
        }
        return goal

    async def fake_bind_conversation(conversation_id, user_id, goal_id, session):
        captured["bind"] = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "goal_id": goal_id,
        }

    monkeypatch.setattr(discovery_agent, "get_session", lambda: FakeSession())
    monkeypatch.setattr(discovery_agent.goal_service, "save_goal", fake_save_goal)
    monkeypatch.setattr(
        discovery_agent.discovery_service,
        "bind_discovery_conversation_goal",
        fake_bind_conversation,
    )

    result = await discovery_save_goal.ainvoke(
        {
            "goal": _goal(),
            "runtime": _runtime("user-123", conversation_id="convo-123"),
        }
    )

    assert result["goal_id"]
    assert captured["save"]["user_id"] == "user-123"
    assert captured["save"]["goal_id"] == result["goal_id"]
    assert captured["bind"] == {
        "conversation_id": "convo-123",
        "user_id": "user-123",
        "goal_id": result["goal_id"],
    }


@pytest.mark.asyncio
async def test_discovery_save_goal_reuses_runtime_goal_id(monkeypatch):
    captured = {}

    async def fake_save_goal(user_id, goal, session, goal_id=None):
        captured["goal_id"] = goal_id
        return goal

    async def fake_bind_conversation(conversation_id, user_id, goal_id, session):
        raise AssertionError("already-bound goal should not need rebinding")

    monkeypatch.setattr(discovery_agent, "get_session", lambda: FakeSession())
    monkeypatch.setattr(discovery_agent.goal_service, "save_goal", fake_save_goal)
    monkeypatch.setattr(
        discovery_agent.discovery_service,
        "bind_discovery_conversation_goal",
        fake_bind_conversation,
    )

    result = await discovery_save_goal.ainvoke(
        {
            "goal": _goal(),
            "runtime": _runtime(
                "user-123",
                goal_id="goal-existing",
                conversation_id="convo-123",
            ),
        }
    )

    assert result["goal_id"] == "goal-existing"
    assert captured["goal_id"] == "goal-existing"


@pytest.mark.asyncio
async def test_discovery_learning_profile_status_returns_missing_without_throwing(
    monkeypatch,
):
    async def fake_get_learning_profile(user_id, session):
        raise ValueError(f"No learning profile found for user {user_id}")

    monkeypatch.setattr(discovery_agent, "get_session", lambda: FakeSession())
    monkeypatch.setattr(
        discovery_agent.learning_profile_service,
        "get_learning_profile",
        fake_get_learning_profile,
    )

    result = await discovery_get_learning_profile_status.ainvoke(
        {"runtime": _runtime("user-123")}
    )

    assert result == {"exists": False, "learning_profile": None}


@pytest.mark.asyncio
async def test_discovery_learning_profile_status_returns_existing_profile(monkeypatch):
    async def fake_get_learning_profile(user_id, session):
        return _profile()

    monkeypatch.setattr(discovery_agent, "get_session", lambda: FakeSession())
    monkeypatch.setattr(
        discovery_agent.learning_profile_service,
        "get_learning_profile",
        fake_get_learning_profile,
    )

    result = await discovery_get_learning_profile_status.ainvoke(
        {"runtime": _runtime("user-123")}
    )

    assert result["exists"] is True
    assert result["learning_profile"]["baseline_level"] == "intermediate"


@pytest.mark.asyncio
async def test_create_discovery_agent_includes_skill_directory(monkeypatch):
    captured_kwargs = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get_tools(self):
            return [FakeTool("goal_get_goal")]

    def fake_create_deep_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(discovery_agent, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(discovery_agent, "create_deep_agent", fake_create_deep_agent)

    await discovery_agent.create_discovery_agent(
        checkpointer=None,
        use_custom_checkpointer=False,
    )

    assert captured_kwargs["skills"] == [discovery_agent.SKILLS_DIR]


@pytest.mark.asyncio
async def test_create_discovery_agent_uses_configured_model(monkeypatch):
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
        "DISCOVERY_AGENT_MODEL", "google_genai:gemini-3.1-flash-lite-preview"
    )
    monkeypatch.setattr(discovery_agent, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(discovery_agent, "create_deep_agent", fake_create_deep_agent)

    await discovery_agent.create_discovery_agent(
        checkpointer=None,
        use_custom_checkpointer=False,
    )

    assert captured_kwargs["model"] == "google_genai:gemini-3.1-flash-lite-preview"


def test_checkpoint_database_url_uses_psycopg_scheme(monkeypatch):
    monkeypatch.setattr(checkpointing.settings, "POSTGRES_USER", "user")
    monkeypatch.setattr(checkpointing.settings, "POSTGRES_PASSWORD", "pass")
    monkeypatch.setattr(checkpointing.settings, "POSTGRES_HOST", "db")
    monkeypatch.setattr(checkpointing.settings, "POSTGRES_PORT", "5432")
    monkeypatch.setattr(checkpointing.settings, "POSTGRES_DB", "app")

    assert (
        checkpointing.checkpoint_database_url() == "postgresql://user:pass@db:5432/app"
    )
