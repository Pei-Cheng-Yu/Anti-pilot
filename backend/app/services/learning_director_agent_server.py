"""Thin httpx client for starting/polling a Learning Director run on the
internal LangGraph agent-server. Mirrors discovery_agent_server.py, but uses the
background run + poll variant so the FastAPI request never blocks on generation.
"""

from typing import Any

import httpx
from app.core.config import settings

LEARNING_DIRECTOR_ASSISTANT_ID = "learning_director"


class AgentServerUnavailableError(RuntimeError):
    """Raised when the internal LangGraph agent-server cannot be reached."""


class AgentServerRequestError(RuntimeError):
    """Raised when the agent-server rejects a proxied request."""


def _customize_message(
    roadmap_id: str, milestone_id: str, instructions: str
) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            f"Customize milestone {milestone_id} in roadmap {roadmap_id}: {instructions}"
        ),
    }


async def _request(
    method: str, path: str, *, json: dict[str, Any] | None = None
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            base_url=settings.AGENT_SERVER_URL, timeout=30.0
        ) as client:
            response = await client.request(method, path, json=json)
    except httpx.RequestError as e:
        raise AgentServerUnavailableError(f"Agent server unavailable: {e}") from e

    if response.status_code >= 500:
        raise AgentServerUnavailableError(
            f"Agent server returned HTTP {response.status_code}: {_detail(response)}"
        )
    if response.status_code >= 400:
        raise AgentServerRequestError(_detail(response))
    return response.json()


async def start_customize_run(
    *,
    roadmap_id: str,
    milestone_id: str,
    instructions: str,
    user_id: str,
    thread_id: str,
) -> dict[str, Any]:
    """Start a background learning_director run that customizes one milestone."""
    payload = {
        "assistant_id": LEARNING_DIRECTOR_ASSISTANT_ID,
        "input": {
            "messages": [_customize_message(roadmap_id, milestone_id, instructions)]
        },
        "context": {"user_id": user_id},
        "if_not_exists": "create",
    }
    return await _request("POST", f"/threads/{thread_id}/runs", json=payload)


async def get_customize_run(*, thread_id: str, run_id: str) -> dict[str, Any]:
    """Poll the status of a previously started run."""
    return await _request("GET", f"/threads/{thread_id}/runs/{run_id}")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict) and body.get("detail") is not None:
        return str(body["detail"])
    return str(body)
