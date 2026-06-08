from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from app.langgraph.discovery_agent.schemas import DiscoveryResponse
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


@asynccontextmanager
async def fake_session():
    yield object()


class FakeDiscoveryAgent:
    def __init__(self):
        self.ainvoke = AsyncMock(
            return_value={
                "structured_response": DiscoveryResponse(
                    message="What is your target outcome?",
                    session_complete=False,
                )
            }
        )


class AgentServerUnavailable:
    pass


def test_create_discovery_conversation(monkeypatch):
    save = AsyncMock(return_value=None)

    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr("app.routers.discovery.save_discovery_conversation", save)

    response = client.post(
        "/v1/discovery/conversations",
        json={"user_id": "user-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    save.assert_awaited_once()
    assert save.await_args.args[0] == "user-123"
    assert save.await_args.args[1] == body["conversation_id"]


def test_send_discovery_message_proxies_to_agent_server_with_thread_and_user(
    monkeypatch,
):
    send_message = AsyncMock(
        return_value=DiscoveryResponse(
            message="What is your target outcome?",
            session_complete=False,
        )
    )
    get_context = AsyncMock(return_value=("user-123", "goal-fastapi"))

    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr(
        "app.routers.discovery.get_discovery_conversation_context", get_context
    )
    monkeypatch.setattr(
        "app.routers.discovery.send_discovery_message_to_agent_server", send_message
    )

    response = client.post(
        "/v1/discovery/conversations/convo-123/messages",
        json={"message": "I want to learn FastAPI."},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "What is your target outcome?"
    send_message.assert_awaited_once_with(
        conversation_id="convo-123",
        user_id="user-123",
        goal_id="goal-fastapi",
        message="I want to learn FastAPI.",
    )


def test_send_discovery_message_returns_503_when_agent_server_unavailable(monkeypatch):
    from app.services.discovery_agent_server import DiscoveryAgentUnavailableError

    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr(
        "app.routers.discovery.get_discovery_conversation_context",
        AsyncMock(return_value=("user-123", None)),
    )
    monkeypatch.setattr(
        "app.routers.discovery.send_discovery_message_to_agent_server",
        AsyncMock(side_effect=DiscoveryAgentUnavailableError("agent server down")),
    )

    response = client.post(
        "/v1/discovery/conversations/convo-123/messages",
        json={"message": "hello"},
    )

    assert response.status_code == 503
    assert "agent server down" in response.json()["detail"]


def test_send_discovery_message_returns_502_when_agent_server_rejects_request(
    monkeypatch,
):
    from app.services.discovery_agent_server import DiscoveryAgentRequestError

    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr(
        "app.routers.discovery.get_discovery_conversation_context",
        AsyncMock(return_value=("user-123", None)),
    )
    monkeypatch.setattr(
        "app.routers.discovery.send_discovery_message_to_agent_server",
        AsyncMock(side_effect=DiscoveryAgentRequestError("Thread not found")),
    )

    response = client.post(
        "/v1/discovery/conversations/convo-123/messages",
        json={"message": "hello"},
    )

    assert response.status_code == 502
    assert "Thread not found" in response.json()["detail"]


def test_send_discovery_message_returns_404_for_unknown_conversation(monkeypatch):
    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr(
        "app.routers.discovery.get_discovery_conversation_context",
        AsyncMock(side_effect=ValueError("Discovery conversation missing")),
    )

    response = client.post(
        "/v1/discovery/conversations/missing/messages",
        json={"message": "hello"},
    )

    assert response.status_code == 404


def test_resume_discovery_conversation_proxies_to_agent_server(monkeypatch):
    resume = AsyncMock(
        return_value=DiscoveryResponse(
            message="Great, I saved that.",
            session_complete=False,
        )
    )

    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr(
        "app.routers.discovery.get_discovery_conversation_context",
        AsyncMock(return_value=("user-123", None)),
    )
    monkeypatch.setattr(
        "app.routers.discovery.resume_discovery_with_agent_server", resume
    )

    response = client.post(
        "/v1/discovery/conversations/convo-123/resume",
        json={"selection": "Backend web development"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Great, I saved that."
    resume.assert_awaited_once_with(
        conversation_id="convo-123",
        user_id="user-123",
        goal_id=None,
        selection="Backend web development",
    )


def test_resume_discovery_conversation_returns_400_without_interrupt(monkeypatch):
    from app.services.discovery_agent_server import DiscoveryResumeError

    monkeypatch.setattr("app.routers.discovery.get_session", fake_session)
    monkeypatch.setattr(
        "app.routers.discovery.get_discovery_conversation_context",
        AsyncMock(return_value=("user-123", None)),
    )
    monkeypatch.setattr(
        "app.routers.discovery.resume_discovery_with_agent_server",
        AsyncMock(side_effect=DiscoveryResumeError("No pending interrupt")),
    )

    response = client.post(
        "/v1/discovery/conversations/convo-123/resume",
        json={"selection": "Backend web development"},
    )

    assert response.status_code == 400
    assert "No pending interrupt" in response.json()["detail"]
