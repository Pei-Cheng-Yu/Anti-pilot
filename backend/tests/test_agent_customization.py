"""Tests for agent-driven milestone customization (FastAPI wrapping a
learning_director run on the agent-server). Isolated — httpx + the agent-server
client are faked; no live agent-server / LLM needed.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from app.main import DEFAULT_USER_ID, app
from app.schema.entities import MilestoneWithSkillPaths, RoadmapFull
from fastapi.testclient import TestClient

client = TestClient(app)


@asynccontextmanager
async def fake_session():
    from unittest.mock import MagicMock

    yield MagicMock()


def _roadmap_with_milestone(roadmap_id="r1", milestone_id="m1") -> RoadmapFull:
    return RoadmapFull(
        roadmap_id=roadmap_id,
        title="T",
        version=1,
        summary="s",
        target_outcome="o",
        assumptions=[],
        milestones=[
            MilestoneWithSkillPaths(
                roadmap_id=roadmap_id,
                milestone_id=milestone_id,
                title="M1",
                description="d",
                objective="o",
                estimated_hours=1,
                order_index=1,
                skillpaths=[],
            )
        ],
    )


# ---------------------------------------------------------------------------
# agent-server client (mock httpx)
# ---------------------------------------------------------------------------


def _patch_httpx(monkeypatch, capture, *, status_code=200, payload=None):
    import app.services.learning_director_agent_server as mod

    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self.text = ""

        def json(self):
            return (
                payload
                if payload is not None
                else {"run_id": "run-1", "status": "pending"}
            )

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, path, json=None):
            capture["method"] = method
            capture["path"] = path
            capture["json"] = json
            return _Resp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", _Client)


@pytest.mark.asyncio
async def test_start_customize_run_posts_expected_payload(monkeypatch):
    import app.services.learning_director_agent_server as mod

    cap = {}
    _patch_httpx(monkeypatch, cap)
    run = await mod.start_customize_run(
        roadmap_id="r1",
        milestone_id="m1",
        instructions="make it more advanced",
        user_id="u1",
        thread_id="t1",
    )
    assert cap["method"] == "POST"
    assert cap["path"] == "/threads/t1/runs"
    body = cap["json"]
    assert body["assistant_id"] == "learning_director"
    assert body["context"] == {"user_id": "u1"}
    msg = body["input"]["messages"][0]["content"]
    assert "m1" in msg and "r1" in msg and "make it more advanced" in msg
    assert run["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_get_customize_run_gets_expected_path(monkeypatch):
    import app.services.learning_director_agent_server as mod

    cap = {}
    _patch_httpx(monkeypatch, cap, payload={"run_id": "run-1", "status": "running"})
    run = await mod.get_customize_run(thread_id="t1", run_id="run-1")
    assert cap["method"] == "GET"
    assert cap["path"] == "/threads/t1/runs/run-1"
    assert run["status"] == "running"


# ---------------------------------------------------------------------------
# endpoints (mock the agent-server client)
# ---------------------------------------------------------------------------


def test_customize_agent_starts_run(monkeypatch):
    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full",
        AsyncMock(return_value=_roadmap_with_milestone("r1", "m1")),
    )
    started = AsyncMock(return_value={"run_id": "run-9", "status": "pending"})
    monkeypatch.setattr("app.main.ld_agent_server.start_customize_run", started)

    resp = client.post(
        "/v1/roadmaps/r1/milestones/m1/customize-agent",
        json={"instructions": "add a testing skillpath"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (
        body["run_id"] == "run-9" and body["status"] == "pending" and body["thread_id"]
    )
    # instruction + ids forwarded to the client
    kwargs = started.await_args.kwargs
    assert kwargs["roadmap_id"] == "r1" and kwargs["milestone_id"] == "m1"
    assert kwargs["instructions"] == "add a testing skillpath"
    assert kwargs["user_id"] == DEFAULT_USER_ID


def test_customize_agent_unknown_milestone_404(monkeypatch):
    monkeypatch.setattr("app.main.get_session", fake_session)
    monkeypatch.setattr(
        "app.main.roadmap_service.get_roadmap_full",
        AsyncMock(return_value=_roadmap_with_milestone("r1", "m1")),
    )
    boom = AsyncMock()
    monkeypatch.setattr("app.main.ld_agent_server.start_customize_run", boom)

    resp = client.post(
        "/v1/roadmaps/r1/milestones/m-unknown/customize-agent",
        json={"instructions": "x"},
    )
    assert resp.status_code == 404
    boom.assert_not_awaited()


def test_customize_run_status_proxied(monkeypatch):
    monkeypatch.setattr(
        "app.main.ld_agent_server.get_customize_run",
        AsyncMock(return_value={"run_id": "run-9", "status": "running"}),
    )
    resp = client.get("/v1/roadmaps/r1/customize-runs/t1/run-9")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
