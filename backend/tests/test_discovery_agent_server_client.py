import httpx
import pytest
from app.langgraph.discovery_agent.schemas import DiscoveryResponse
from app.services.discovery_agent_server import (
    DiscoveryAgentRequestError,
    DiscoveryAgentServerClient,
    DiscoveryAgentUnavailableError,
    DiscoveryResumeError,
    normalize_agent_server_response,
)


@pytest.mark.asyncio
async def test_send_message_posts_turn_to_thread_runs_wait_with_user_context():
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        body = request.read().decode()
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "structured_response": {
                    "message": "What outcome do you want?",
                    "session_complete": False,
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="http://agent-server:2024", transport=transport
    ) as http_client:
        client = DiscoveryAgentServerClient(
            base_url="http://agent-server:2024",
            http_client=http_client,
        )

        response = await client.send_message(
            conversation_id="convo-123",
            user_id="user-123",
            goal_id="goal-fastapi",
            message="I want to learn FastAPI.",
        )

    assert response == DiscoveryResponse(
        message="What outcome do you want?",
        session_complete=False,
    )
    assert captured["method"] == "POST"
    assert captured["path"] == "/threads/convo-123/runs/wait"
    assert '"assistant_id":"discovery_agent"' in captured["body"]
    assert '"role":"system"' in captured["body"]
    assert "CURRENT_USER_ID: user-123" in captured["body"]
    assert '"role":"user"' in captured["body"]
    assert '"content":"I want to learn FastAPI."' in captured["body"]
    assert (
        '"context":{"user_id":"user-123","conversation_id":"convo-123","goal_id":"goal-fastapi"}'
        in captured["body"]
    )
    assert "CURRENT_GOAL_ID: goal-fastapi" in captured["body"]
    assert '"config"' not in captured["body"]
    assert '"if_not_exists":"create"' in captured["body"]


@pytest.mark.asyncio
async def test_resume_posts_command_to_same_thread():
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "messages": [
                    {
                        "role": "assistant",
                        "content": '{"message": "Great, I saved that.", "session_complete": false}',
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="http://agent-server:2024", transport=transport
    ) as http_client:
        client = DiscoveryAgentServerClient(
            base_url="http://agent-server:2024",
            http_client=http_client,
        )

        response = await client.resume(
            conversation_id="convo-123",
            user_id="user-123",
            goal_id="goal-fastapi",
            selection="Backend web development",
        )

    assert response.message == "Great, I saved that."
    assert captured["path"] == "/threads/convo-123/runs/wait"
    assert '"command":{"resume":"Backend web development"}' in captured["body"]
    assert (
        '"context":{"user_id":"user-123","conversation_id":"convo-123","goal_id":"goal-fastapi"}'
        in captured["body"]
    )


@pytest.mark.asyncio
async def test_unreachable_agent_server_raises_unavailable():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="http://agent-server:2024", transport=transport
    ) as http_client:
        client = DiscoveryAgentServerClient(
            base_url="http://agent-server:2024",
            http_client=http_client,
        )

        with pytest.raises(DiscoveryAgentUnavailableError):
            await client.send_message(
                conversation_id="convo-123",
                user_id="user-123",
                message="hello",
            )


@pytest.mark.asyncio
async def test_agent_server_bad_request_raises_request_error_with_detail():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"detail": "Thread not found"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="http://agent-server:2024", transport=transport
    ) as http_client:
        client = DiscoveryAgentServerClient(
            base_url="http://agent-server:2024",
            http_client=http_client,
        )

        with pytest.raises(DiscoveryAgentRequestError) as exc:
            await client.send_message(
                conversation_id="convo-123",
                user_id="user-123",
                message="hello",
            )

    assert "Thread not found" in str(exc.value)


@pytest.mark.asyncio
async def test_resume_without_pending_interrupt_raises_resume_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"detail": "No pending interrupt for thread"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="http://agent-server:2024", transport=transport
    ) as http_client:
        client = DiscoveryAgentServerClient(
            base_url="http://agent-server:2024",
            http_client=http_client,
        )

        with pytest.raises(DiscoveryResumeError):
            await client.resume(
                conversation_id="convo-123",
                user_id="user-123",
                selection="yes",
            )


def test_normalize_agent_server_response_uses_message_when_structured_response_empty():
    response = normalize_agent_server_response(
        {
            "structured_response": {
                "message": "",
                "session_complete": False,
            },
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        '{"message": "What outcome would make this goal feel done?", '
                        '"ui_hints": {"type": "text_input", "options": []}, '
                        '"session_complete": false}'
                    ),
                }
            ],
        }
    )

    assert response.message == "What outcome would make this goal feel done?"
    assert response.ui_hints is not None
    assert response.ui_hints.type == "text_input"


def test_normalize_agent_server_response_returns_discovery_fallback_when_empty():
    response = normalize_agent_server_response(
        {
            "structured_response": {
                "message": "",
                "session_complete": False,
            },
            "messages": [],
        }
    )

    assert response.message
    assert response.ui_hints is not None
    assert response.ui_hints.type == "text_input"
    assert response.session_complete is False
