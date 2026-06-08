from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import httpx
import pytest
from app.db.model import (
    DiscoveryConversationModel,
    GoalModel,
    LearnerMemoryNoteModel,
    LearningContentModel,
    LearningProfileModel,
    MilestoneModel,
    RoadmapModel,
    SkillPathModel,
    UserModel,
)
from app.db.session import get_session
from app.services.discovery_agent_server import DISCOVERY_FALLBACK_MESSAGE
from sqlalchemy import delete, exists, select

pytestmark = pytest.mark.live_llm


def _skip_unless_live_enabled() -> None:
    if os.getenv("RUN_LIVE_DISCOVERY_E2E_TESTS") != "1":
        pytest.skip(
            "Set RUN_LIVE_DISCOVERY_E2E_TESTS=1 to run discovery e2e smoke tests."
        )
    if not any(
        os.getenv(name)
        for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
    ):
        pytest.skip("Set Google/Gemini API credentials to run discovery e2e tests.")


async def _cleanup_user(user_id: str) -> None:
    async with get_session() as session:
        roadmap_ids = list(
            (
                await session.execute(
                    select(RoadmapModel.roadmap_id).where(
                        RoadmapModel.user_id == user_id
                    )
                )
            ).scalars()
        )
        if roadmap_ids:
            milestone_ids = list(
                (
                    await session.execute(
                        select(MilestoneModel.milestone_id).where(
                            MilestoneModel.roadmap_id.in_(roadmap_ids)
                        )
                    )
                ).scalars()
            )
            if milestone_ids:
                skillpath_ids = list(
                    (
                        await session.execute(
                            select(SkillPathModel.skillpath_id).where(
                                SkillPathModel.milestone_id.in_(milestone_ids)
                            )
                        )
                    ).scalars()
                )
                if skillpath_ids:
                    await session.execute(
                        delete(LearningContentModel).where(
                            LearningContentModel.skillpath_id.in_(skillpath_ids)
                        )
                    )
                await session.execute(
                    delete(SkillPathModel).where(
                        SkillPathModel.milestone_id.in_(milestone_ids)
                    )
                )
            await session.execute(
                delete(MilestoneModel).where(MilestoneModel.roadmap_id.in_(roadmap_ids))
            )
            await session.execute(
                delete(RoadmapModel).where(RoadmapModel.roadmap_id.in_(roadmap_ids))
            )
        await session.execute(
            delete(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == user_id
            )
        )
        await session.execute(
            delete(LearningProfileModel).where(LearningProfileModel.user_id == user_id)
        )
        await session.execute(delete(GoalModel).where(GoalModel.user_id == user_id))
        await session.execute(
            delete(DiscoveryConversationModel).where(
                DiscoveryConversationModel.user_id == user_id
            )
        )
        await session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await session.commit()


async def _fetch_discovery_outputs(user_id: str) -> dict:
    async with get_session() as session:
        goal = (
            await session.execute(select(GoalModel).where(GoalModel.user_id == user_id))
        ).scalar_one_or_none()
        profile = (
            await session.execute(
                select(LearningProfileModel).where(
                    LearningProfileModel.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        memory_notes = list(
            (
                await session.execute(
                    select(LearnerMemoryNoteModel).where(
                        LearnerMemoryNoteModel.user_id == user_id
                    )
                )
            ).scalars()
        )
        roadmap = (
            await session.execute(
                select(RoadmapModel).where(RoadmapModel.user_id == user_id)
            )
        ).scalar_one_or_none()

        has_milestone = False
        has_skillpath = False
        has_content = False
        if roadmap is not None:
            has_milestone = await session.scalar(
                select(exists().where(MilestoneModel.roadmap_id == roadmap.roadmap_id))
            )
            has_skillpath = await session.scalar(
                select(
                    exists()
                    .where(MilestoneModel.roadmap_id == roadmap.roadmap_id)
                    .where(SkillPathModel.milestone_id == MilestoneModel.milestone_id)
                )
            )
            has_content = await session.scalar(
                select(
                    exists()
                    .where(MilestoneModel.roadmap_id == roadmap.roadmap_id)
                    .where(SkillPathModel.milestone_id == MilestoneModel.milestone_id)
                    .where(
                        LearningContentModel.skillpath_id == SkillPathModel.skillpath_id
                    )
                )
            )

    return {
        "goal": goal,
        "profile": profile,
        "memory_notes": memory_notes,
        "roadmap": roadmap,
        "has_milestone": bool(has_milestone),
        "has_skillpath": bool(has_skillpath),
        "has_content": bool(has_content),
    }


async def _wait_for_persisted_roadmap(user_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        last = await _fetch_discovery_outputs(user_id)
        if (
            last["goal"] is not None
            and last["profile"] is not None
            and last["roadmap"] is not None
            and last["has_milestone"]
            and last["has_skillpath"]
            and last["has_content"]
        ):
            return last
        await asyncio.sleep(5)
    return last


def test_live_discovery_workflow_persists_goal_profile_memory_roadmap_and_content():
    _skip_unless_live_enabled()

    base_url = os.getenv("DISCOVERY_E2E_BASE_URL", "http://localhost:8000")
    timeout_seconds = int(os.getenv("DISCOVERY_E2E_TIMEOUT_SECONDS", "240"))
    user_id = f"live-discovery-{uuid4()}"
    conversation_id = None
    last_response: dict | None = None

    async def run() -> None:
        nonlocal conversation_id, last_response
        await _cleanup_user(user_id)
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=500.0) as client:
                created = await client.post(
                    "/v1/discovery/conversations",
                    json={"user_id": user_id},
                )
                created.raise_for_status()
                conversation_id = created.json()["conversation_id"]

                messages = [
                    (
                        "I want to learn FastAPI async backend development well "
                        "enough to build reliable API routes with async database "
                        "access in four weeks. I prefer examples first and hands-on "
                        "practice."
                    ),
                    (
                        "My goal is to build a small production-style FastAPI app "
                        "with SQLAlchemy async sessions, Alembic migrations, and "
                        "tested route handlers."
                    ),
                    (
                        "I am intermediate in Python, know basic REST APIs and SQL, "
                        "but I am weak at async/await and dependency injection. I can "
                        "study six hours per week."
                    ),
                    (
                        "Please save that goal and profile. I want balanced pacing, "
                        "medium confidence, frequent recaps, examples first, and "
                        "medium overload risk."
                    ),
                    "Yes, start roadmap generation now.",
                ]

                for message in messages:
                    response = await client.post(
                        f"/v1/discovery/conversations/{conversation_id}/messages",
                        json={"message": message},
                    )
                    response.raise_for_status()
                    last_response = response.json()
                    print({"phase": "discovery_response", "response": last_response})
                    assert last_response.get("message") != DISCOVERY_FALLBACK_MESSAGE
                    if last_response.get("session_complete"):
                        break

            outputs = await _wait_for_persisted_roadmap(user_id, timeout_seconds)
            print(
                {
                    "phase": "discovery_outputs",
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "last_response": last_response,
                    "goal": bool(outputs["goal"]),
                    "profile": bool(outputs["profile"]),
                    "memory_types": [
                        note.memory_type for note in outputs["memory_notes"]
                    ],
                    "roadmap": bool(outputs["roadmap"]),
                    "has_milestone": outputs["has_milestone"],
                    "has_skillpath": outputs["has_skillpath"],
                    "has_content": outputs["has_content"],
                }
            )

            goal = outputs["goal"]
            profile = outputs["profile"]
            assert goal is not None
            assert goal.title
            assert goal.description
            assert goal.target_outcome
            assert goal.deadline
            assert goal.criteria
            assert goal.constraints

            assert profile is not None
            assert profile.baseline_level
            assert profile.prior_knowledges or profile.weak_areas
            assert profile.pace_preference
            assert profile.confidence_level
            assert profile.overload_risk

            assert {note.memory_type for note in outputs["memory_notes"]} <= {
                "preference_signal",
                "background",
            }

            assert last_response is not None
            assert last_response.get("session_complete") is True
            assert last_response.get("roadmap_job_id")
            assert outputs["roadmap"] is not None
            assert outputs["has_milestone"] is True
            assert outputs["has_skillpath"] is True
            assert outputs["has_content"] is True
        finally:
            if os.getenv("DISCOVERY_E2E_KEEP_DATA") != "1":
                await _cleanup_user(user_id)

    try:
        asyncio.run(run())
    except Exception:
        print(
            {
                "failure_hint": "Inspect backend, mcp, and agent-server logs; check LangSmith for Discovery Agent tool calls.",
                "user_id": user_id,
                "conversation_id": conversation_id,
                "last_response": last_response,
            }
        )
        raise
