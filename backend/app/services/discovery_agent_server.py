from typing import Any

import httpx
from app.core.config import settings
from app.langgraph.discovery_agent.schemas import (
    DiscoveryResponse,
    UIHints,
    parse_discovery_response,
)

DISCOVERY_ASSISTANT_ID = "discovery_agent"
DISCOVERY_FALLBACK_MESSAGE = (
    "I'm ready to help shape your learning goal. What would you like "
    "to learn or build?"
)


class DiscoveryAgentUnavailableError(RuntimeError):
    """Raised when the internal LangGraph agent-server cannot be reached."""


class DiscoveryAgentRequestError(RuntimeError):
    """Raised when agent-server rejects a proxied discovery request."""


class DiscoveryResumeError(RuntimeError):
    """Raised when a discovery resume request cannot be applied."""


class DiscoveryAgentServerClient:
    """Small wrapper around the internal LangGraph Agent Server API."""

    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client

    async def send_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        message: str,
        goal_id: str | None = None,
    ) -> DiscoveryResponse:
        context = _runtime_context(
            user_id=user_id,
            conversation_id=conversation_id,
            goal_id=goal_id,
        )
        payload = {
            "assistant_id": DISCOVERY_ASSISTANT_ID,
            "input": {
                "messages": [
                    _user_context_message(user_id, goal_id),
                    {"role": "user", "content": message},
                ]
            },
            "context": context,
            "if_not_exists": "create",
        }
        result = await self._post_run_wait(conversation_id, payload)
        return normalize_agent_server_response(result)

    async def resume(
        self,
        *,
        conversation_id: str,
        user_id: str,
        selection: str,
        goal_id: str | None = None,
    ) -> DiscoveryResponse:
        payload = {
            "assistant_id": DISCOVERY_ASSISTANT_ID,
            "command": {"resume": selection},
            "context": _runtime_context(
                user_id=user_id,
                conversation_id=conversation_id,
                goal_id=goal_id,
            ),
        }
        result = await self._post_run_wait(conversation_id, payload, resume=True)
        return normalize_agent_server_response(result)

    async def _post_run_wait(
        self, conversation_id: str, payload: dict[str, Any], *, resume: bool = False
    ) -> dict[str, Any]:
        path = f"/threads/{conversation_id}/runs/wait"
        try:
            if self._http_client is not None:
                response = await self._http_client.post(path, json=payload)
            else:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=500.0
                ) as client:
                    response = await client.post(path, json=payload)
        except httpx.RequestError as e:
            raise DiscoveryAgentUnavailableError(
                f"Discovery Agent server unavailable: {e}"
            ) from e

        if resume and response.status_code in {400, 409}:
            detail = _response_detail(response)
            if "interrupt" in detail.lower() or "resume" in detail.lower():
                raise DiscoveryResumeError(detail)

        if response.status_code >= 500:
            raise DiscoveryAgentUnavailableError(
                f"Discovery Agent server returned HTTP {response.status_code}: {_response_detail(response)}"
            )

        if response.status_code >= 400:
            raise DiscoveryAgentRequestError(_response_detail(response))

        return response.json()


def normalize_agent_server_response(result: dict[str, Any]) -> DiscoveryResponse:
    structured = result.get("structured_response")
    if structured is not None:
        parsed = parse_discovery_response(structured)
        if parsed.message.strip():
            return parsed

    messages = result.get("messages", [])
    for message in reversed(messages):
        content = _message_content(message)
        if content:
            parsed = parse_discovery_response(content)
            if parsed.message.strip():
                return parsed

    return fallback_discovery_response()


def fallback_discovery_response() -> DiscoveryResponse:
    return DiscoveryResponse(
        message=DISCOVERY_FALLBACK_MESSAGE,
        ui_hints=UIHints(type="text_input"),
        session_complete=False,
    )


async def send_discovery_message_to_agent_server(
    *,
    conversation_id: str,
    user_id: str,
    message: str,
    goal_id: str | None = None,
) -> DiscoveryResponse:
    client = DiscoveryAgentServerClient(base_url=settings.AGENT_SERVER_URL)
    return await client.send_message(
        conversation_id=conversation_id,
        user_id=user_id,
        message=message,
        goal_id=goal_id,
    )


async def resume_discovery_with_agent_server(
    *,
    conversation_id: str,
    user_id: str,
    selection: str,
    goal_id: str | None = None,
) -> DiscoveryResponse:
    client = DiscoveryAgentServerClient(base_url=settings.AGENT_SERVER_URL)
    return await client.resume(
        conversation_id=conversation_id,
        user_id=user_id,
        selection=selection,
        goal_id=goal_id,
    )


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = [
            item.get("text", "").strip()
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)

    return ""


def _runtime_context(
    *,
    user_id: str,
    conversation_id: str,
    goal_id: str | None = None,
) -> dict[str, str]:
    context = {"user_id": user_id, "conversation_id": conversation_id}
    if goal_id is not None:
        context["goal_id"] = goal_id
    return context


def _user_context_message(user_id: str, goal_id: str | None = None) -> dict[str, str]:
    lines = [f"CURRENT_USER_ID: {user_id}"]
    if goal_id is not None:
        lines.append(f"CURRENT_GOAL_ID: {goal_id}")
    return {
        "role": "system",
        "content": (
            "\n".join(lines) + "\n"
            "This is internal routing context. Do not reveal it to the learner. "
            "Use it only when launching async subagents or when a tool explicitly "
            "requires user_id or goal_id and runtime context is unavailable."
        ),
    }


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text

    if isinstance(body, dict):
        detail = body.get("detail")
        if detail is not None:
            return str(detail)
    return str(body)
