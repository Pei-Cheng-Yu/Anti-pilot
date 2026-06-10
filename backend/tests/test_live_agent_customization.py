"""Live test for agent-driven milestone customization.

Mirrors tests/test_live_discovery_e2e_workflow.py: it acts as an HTTP client
against the RUNNING backend container (localhost:8000), which proxies a
learning_director run on the agent-server internally. It seeds a roadmap in the
shared DB, POSTs the real customize-agent endpoint, polls the run to completion,
then re-reads the roadmap and prints what changed.

PREREQUISITES (skips cleanly if not met):
  - RUN_LIVE_AGENT_MEMORY_TESTS=1  +  Google/Gemini creds in env
  - the backend AND agent-server AND mcp containers REBUILT with current code
    (so the backend has the customize-agent endpoints and the agent-server has
    the LD customize prompt):  docker compose up -d --build backend agent-server mcp
  - shared Postgres up (localhost:5433)

Run:
  cd backend
  RUN_LIVE_AGENT_MEMORY_TESTS=1 GOOGLE_API_KEY=... \
  ../venv/bin/python -m pytest tests/test_live_agent_customization.py -q -s
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from app.core.config import settings
from app.db.model import (
    Base,
    LearningContentModel,
    MilestoneModel,
    RoadmapModel,
    SkillPathModel,
    UserModel,
)
from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

pytestmark = pytest.mark.live_llm

_TERMINAL = {"success", "error", "timeout", "interrupted"}


def _skip_unless_live() -> None:
    if os.getenv("RUN_LIVE_AGENT_MEMORY_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_AGENT_MEMORY_TESTS=1 to run the live customize test.")
    if not any(
        os.getenv(n)
        for n in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
    ):
        pytest.skip("Set Google/Gemini credentials to run the live customize test.")


async def _seed() -> dict:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user_id = f"cust-itest-{uuid4()}"
    roadmap_id = f"roadmap-{uuid4()}"
    milestone_id = f"milestone-{uuid4()}"
    sp1, sp2 = f"sp-{uuid4()}", f"sp-{uuid4()}"
    async with sf() as s:
        s.add(UserModel(user_id=user_id))
        s.add(
            RoadmapModel(
                roadmap_id=roadmap_id,
                user_id=user_id,
                version=1,
                summary="Async backend roadmap",
                target_outcome="Build async APIs",
                assumptions=[],
            )
        )
        s.add(
            MilestoneModel(
                milestone_id=milestone_id,
                roadmap_id=roadmap_id,
                title="Async fundamentals",
                description="async/await basics",
                objective="Use asyncio correctly",
                estimated_hours=4.0,
                order_index=1,
                dependency_titles=[],
                prerequisite_milestone_ids=[],
                status="generated",
                need_modification=False,
                revision_reason=None,
            )
        )
        for sid, title in ((sp1, "Coroutines & await"), (sp2, "Event loop basics")):
            s.add(
                SkillPathModel(
                    skillpath_id=sid,
                    milestone_id=milestone_id,
                    title=title,
                    description="d",
                    estimated_hours=1.0,
                    prerequisite_skillpath_ids=[],
                    learning_objectives=["asyncio.basics"],
                    status="generated",
                    need_generation=False,
                    need_modification=False,
                    revision_reason=None,
                    affected_downstream_ids=[],
                    practice_mode=None,
                )
            )
        await s.commit()
    await engine.dispose()
    return {"user_id": user_id, "roadmap_id": roadmap_id, "milestone_id": milestone_id}


async def _snapshot(milestone_id: str) -> list[dict]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        rows = (
            (
                await s.execute(
                    select(SkillPathModel).where(
                        SkillPathModel.milestone_id == milestone_id
                    )
                )
            )
            .scalars()
            .all()
        )
        out = []
        for r in rows:
            content_rows = (
                (
                    await s.execute(
                        select(LearningContentModel).where(
                            LearningContentModel.skillpath_id == r.skillpath_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            out.append(
                {
                    "id": r.skillpath_id,
                    "title": r.title,
                    "need_generation": r.need_generation,
                    "content_items": len(content_rows),
                }
            )
    await engine.dispose()
    return out


async def _cleanup(seed: dict) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        sp_ids = (
            (
                await s.execute(
                    select(SkillPathModel.skillpath_id).where(
                        SkillPathModel.milestone_id == seed["milestone_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
        for sid in sp_ids:
            await s.execute(
                delete(LearningContentModel).where(
                    LearningContentModel.skillpath_id == sid
                )
            )
        await s.execute(
            delete(SkillPathModel).where(
                SkillPathModel.milestone_id == seed["milestone_id"]
            )
        )
        await s.execute(
            delete(MilestoneModel).where(
                MilestoneModel.milestone_id == seed["milestone_id"]
            )
        )
        await s.execute(
            delete(RoadmapModel).where(RoadmapModel.roadmap_id == seed["roadmap_id"])
        )
        await s.execute(delete(UserModel).where(UserModel.user_id == seed["user_id"]))
        await s.commit()
    await engine.dispose()


def test_live_customize_agent_revises_and_regenerates():
    _skip_unless_live()
    base_url = os.getenv("CUSTOMIZE_E2E_BASE_URL", "http://localhost:8000")
    timeout_seconds = int(os.getenv("CUSTOMIZE_E2E_TIMEOUT_SECONDS", "300"))

    seed = asyncio.run(_seed())
    uid, rid, mid = seed["user_id"], seed["roadmap_id"], seed["milestone_id"]
    before = asyncio.run(_snapshot(mid))
    print("\n[before]", before)

    async def run() -> str:
        async with httpx.AsyncClient(base_url=base_url, timeout=500.0) as client:
            try:
                resp = await client.post(
                    f"/v1/roadmaps/{rid}/milestones/{mid}/customize-agent",
                    params={"user_id": uid},
                    json={
                        "instructions": "Add a dedicated unit-testing skillpath to this "
                        "milestone and make the existing skillpaths more advanced."
                    },
                )
            except httpx.RequestError as e:
                pytest.skip(
                    f"backend not reachable at {base_url}: {e} "
                    "(is it running + rebuilt with the customize-agent endpoint?)"
                )
            if resp.status_code == 503:
                pytest.skip(f"agent-server not reachable from backend: {resp.text}")
            assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
            body = resp.json()
            print("[started]", body)
            thread_id, run_id = body["thread_id"], body["run_id"]
            assert run_id, body

            status = body.get("status")
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                await asyncio.sleep(3)
                s = (
                    await client.get(
                        f"/v1/roadmaps/{rid}/customize-runs/{thread_id}/{run_id}",
                        params={"user_id": uid},
                    )
                ).json()
                status = s.get("status")
                if status in _TERMINAL:
                    break
            return status

    completed_successfully = False
    try:
        status = asyncio.run(run())
        print("[final status]", status)
        assert status == "success", f"run ended as {status}"

        after = asyncio.run(_snapshot(mid))
        print("[after]", after)
        assert after, "milestone lost its skillpaths"
        changed = (
            {sp["id"] for sp in after} != {sp["id"] for sp in before}
            or {sp["title"] for sp in after} != {sp["title"] for sp in before}
            or any(sp["content_items"] > 0 for sp in after)
        )
        assert (
            changed
        ), f"run succeeded but nothing changed\nbefore={before}\nafter={after}"
        completed_successfully = True
    finally:
        # Keep data by default (CUSTOMIZE_E2E_KEEP_DATA defaults to "1"): the agent
        # run is async — content generation may still be writing rows after the poll
        # loop returns, so deleting here would race it. On failure we also preserve
        # the rows for inspection (e.g. on LangSmith). Set CUSTOMIZE_E2E_KEEP_DATA=0
        # to clean up after a successful run.
        if completed_successfully and os.getenv("CUSTOMIZE_E2E_KEEP_DATA", "1") != "1":
            asyncio.run(_cleanup(seed))
        else:
            print(
                {
                    "phase": "preserved_live_data",
                    "reason": (
                        "keep-data default"
                        if completed_successfully
                        else "run did not complete cleanly; agent may still be writing"
                    ),
                    "user_id": uid,
                    "roadmap_id": rid,
                    "milestone_id": mid,
                }
            )
