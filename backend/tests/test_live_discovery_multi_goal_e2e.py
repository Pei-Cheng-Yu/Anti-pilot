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
from sqlalchemy import delete, select

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
            delete(DiscoveryConversationModel).where(
                DiscoveryConversationModel.user_id == user_id
            )
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
        await session.execute(delete(UserModel).where(UserModel.user_id == user_id))
        await session.commit()


async def _fetch_multi_goal_snapshot(user_id: str) -> dict:
    async with get_session() as session:
        goals = list(
            (
                await session.execute(
                    select(GoalModel)
                    .where(GoalModel.user_id == user_id)
                    .order_by(GoalModel.id)
                )
            ).scalars()
        )
        conversations = list(
            (
                await session.execute(
                    select(DiscoveryConversationModel)
                    .where(DiscoveryConversationModel.user_id == user_id)
                    .order_by(DiscoveryConversationModel.created_at)
                )
            ).scalars()
        )
        roadmaps = list(
            (
                await session.execute(
                    select(RoadmapModel)
                    .where(RoadmapModel.user_id == user_id)
                    .order_by(RoadmapModel.roadmap_id)
                )
            ).scalars()
        )
        content_goal_ids = set(
            (
                await session.execute(
                    select(RoadmapModel.goal_id)
                    .join(
                        MilestoneModel,
                        MilestoneModel.roadmap_id == RoadmapModel.roadmap_id,
                    )
                    .join(
                        SkillPathModel,
                        SkillPathModel.milestone_id == MilestoneModel.milestone_id,
                    )
                    .join(
                        LearningContentModel,
                        LearningContentModel.skillpath_id
                        == SkillPathModel.skillpath_id,
                    )
                    .where(
                        RoadmapModel.user_id == user_id,
                        RoadmapModel.goal_id.is_not(None),
                    )
                    .distinct()
                )
            ).scalars()
        )

    return {
        "goals": goals,
        "conversations": conversations,
        "roadmaps": roadmaps,
        "content_goal_ids": content_goal_ids,
    }


async def _wait_for_two_goal_roadmaps(user_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        last = await _fetch_multi_goal_snapshot(user_id)
        goal_ids = {goal.goal_id for goal in last["goals"]}
        roadmap_goal_ids = {
            roadmap.goal_id for roadmap in last["roadmaps"] if roadmap.goal_id
        }
        content_goal_ids = last.get("content_goal_ids", set())
        if (
            len(goal_ids) >= 2
            and len(roadmap_goal_ids & goal_ids) >= 2
            and len(content_goal_ids & goal_ids) >= 2
        ):
            return last
        await asyncio.sleep(5)
    return last


async def _start_conversation(
    client: httpx.AsyncClient, user_id: str, goal_id: str | None = None
) -> str:
    body = {"user_id": user_id}
    if goal_id:
        body["goal_id"] = goal_id
    created = await client.post("/v1/discovery/conversations", json=body)
    created.raise_for_status()
    conversation_id = created.json()["conversation_id"]
    print(
        {
            "phase": "conversation_created",
            "conversation_id": conversation_id,
            "goal_id": goal_id,
        }
    )
    return conversation_id


async def _send_messages_until_complete(
    client: httpx.AsyncClient, conversation_id: str, messages: list[str]
) -> dict:
    last_response: dict = {}
    for message in messages:
        response = await client.post(
            f"/v1/discovery/conversations/{conversation_id}/messages",
            json={"message": message},
        )
        response.raise_for_status()
        last_response = response.json()
        print(
            {
                "phase": "discovery_response",
                "conversation_id": conversation_id,
                "response": last_response,
            }
        )
        assert last_response.get("message") != DISCOVERY_FALLBACK_MESSAGE
        if last_response.get("session_complete"):
            break
    return last_response


def test_live_discovery_supports_two_goals_and_goal_bound_discussion():
    _skip_unless_live_enabled()

    base_url = os.getenv("DISCOVERY_E2E_BASE_URL", "http://localhost:8000")
    timeout_seconds = int(os.getenv("DISCOVERY_E2E_TIMEOUT_SECONDS", "300"))
    user_id = f"live-multigoal-{uuid4()}"
    first_conversation_id: str | None = None
    second_conversation_id: str | None = None
    bound_conversation_id: str | None = None
    first_goal_id: str | None = None
    second_goal_id: str | None = None

    async def run() -> None:
        nonlocal first_conversation_id
        nonlocal second_conversation_id
        nonlocal bound_conversation_id
        nonlocal first_goal_id
        nonlocal second_goal_id

        await _cleanup_user(user_id)
        completed_successfully = False
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=500.0) as client:
                first_conversation_id = await _start_conversation(client, user_id)
                first_response = await _send_messages_until_complete(
                    client,
                    first_conversation_id,
                    [
                        (
                            "I want to learn FastAPI async backend development in "
                            "four weeks. I know Python and basic REST APIs, but I "
                            "am weak at async database access. Please shape this "
                            "as one concrete learning goal."
                        ),
                        (
                            "Target outcome: build a small production-style FastAPI "
                            "API with async SQLAlchemy sessions, Alembic migrations, "
                            "dependency injection, and tested route handlers. I can "
                            "study six hours per week and like examples first."
                        ),
                        (
                            "Please save this FastAPI goal and profile, then start "
                            "roadmap generation."
                        ),
                    ],
                )

                second_conversation_id = await _start_conversation(client, user_id)
                second_response = await _send_messages_until_complete(
                    client,
                    second_conversation_id,
                    [
                        (
                            "Now create a separate learning goal. I want to learn "
                            "PostgreSQL query tuning and indexing, not FastAPI. I "
                            "already know basic SQL but need practical performance "
                            "debugging skills."
                        ),
                        (
                            "Target outcome: inspect slow queries, read EXPLAIN "
                            "plans, choose useful indexes, and tune common API-backed "
                            "queries in five weeks. I can study four hours per week."
                        ),
                        (
                            "Please save this PostgreSQL performance goal separately "
                            "and start roadmap generation."
                        ),
                    ],
                )

                assert first_response.get("session_complete") is True
                assert second_response.get("session_complete") is True

                snapshot = await _wait_for_two_goal_roadmaps(user_id, timeout_seconds)
                goals = snapshot["goals"]
                conversations = snapshot["conversations"]
                roadmaps = snapshot["roadmaps"]

                first_bound = next(
                    convo
                    for convo in conversations
                    if convo.conversation_id == first_conversation_id
                )
                second_bound = next(
                    convo
                    for convo in conversations
                    if convo.conversation_id == second_conversation_id
                )
                first_goal_id = first_bound.goal_id
                second_goal_id = second_bound.goal_id

                print(
                    {
                        "phase": "multi_goal_snapshot",
                        "user_id": user_id,
                        "goals": [
                            {
                                "goal_id": goal.goal_id,
                                "title": goal.title,
                                "description": goal.description,
                            }
                            for goal in goals
                        ],
                        "conversations": [
                            {
                                "conversation_id": convo.conversation_id,
                                "goal_id": convo.goal_id,
                            }
                            for convo in conversations
                        ],
                        "roadmaps": [
                            {
                                "roadmap_id": roadmap.roadmap_id,
                                "goal_id": roadmap.goal_id,
                                "title": roadmap.title,
                            }
                            for roadmap in roadmaps
                        ],
                        "content_goal_ids": sorted(snapshot["content_goal_ids"]),
                    }
                )

                assert first_goal_id
                assert second_goal_id
                assert first_goal_id != second_goal_id
                assert len({goal.goal_id for goal in goals}) >= 2
                assert {roadmap.goal_id for roadmap in roadmaps if roadmap.goal_id} >= {
                    first_goal_id,
                    second_goal_id,
                }
                assert snapshot["content_goal_ids"] >= {
                    first_goal_id,
                    second_goal_id,
                }

                bound_conversation_id = await _start_conversation(
                    client, user_id, goal_id=first_goal_id
                )
                bound_response = await _send_messages_until_complete(
                    client,
                    bound_conversation_id,
                    [
                        (
                            "Let's discuss the FastAPI goal again. Keep this "
                            "conversation bound to that goal and help me refine the "
                            "pacing if needed."
                        )
                    ],
                )
                assert bound_response.get("message")

                refreshed = await _fetch_multi_goal_snapshot(user_id)
                bound_row = next(
                    convo
                    for convo in refreshed["conversations"]
                    if convo.conversation_id == bound_conversation_id
                )
                print(
                    {
                        "phase": "bound_discussion_snapshot",
                        "bound_conversation_id": bound_conversation_id,
                        "expected_goal_id": first_goal_id,
                        "actual_goal_id": bound_row.goal_id,
                        "response": bound_response,
                    }
                )
                assert bound_row.goal_id == first_goal_id
                completed_successfully = True
        finally:
            if completed_successfully and os.getenv("DISCOVERY_E2E_KEEP_DATA") != "1":
                await _cleanup_user(user_id)
            elif not completed_successfully:
                print(
                    {
                        "phase": "preserved_failed_live_data",
                        "reason": (
                            "Skipping cleanup because async roadmap/content "
                            "generation may still be running."
                        ),
                        "user_id": user_id,
                    }
                )

    try:
        asyncio.run(run())
    except Exception:
        print(
            {
                "failure_hint": (
                    "Inspect backend, mcp, and agent-server logs; check LangSmith "
                    "for Discovery Agent tool calls and goal_id context."
                ),
                "user_id": user_id,
                "first_conversation_id": first_conversation_id,
                "second_conversation_id": second_conversation_id,
                "bound_conversation_id": bound_conversation_id,
                "first_goal_id": first_goal_id,
                "second_goal_id": second_goal_id,
            }
        )
        raise
