import asyncio
import uuid
from typing import Literal

from app.db.model import RoadmapModel
from app.db.session import get_session
from app.langgraph.content_generation.graphs.generate_learning_content.graph import (
    build_learning_content_graph,
)
from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.schema.entities import (
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    RoadmapFull,
    RoadmapItem,
    SkillPathItem,
)
from app.services import goal as goal_service
from app.services import learning_profile as learning_profile_service
from app.services import roadmap as roadmap_service
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select

load_dotenv()

DEFAULT_USER_ID = "default-user"
_content_generator = build_learning_content_graph()

app = FastAPI(title="AntiCopilot Unified API", version="0.1.0")

from app.routers.reviews import router as reviews_router
from app.routers.signals import router as signals_router

app.include_router(reviews_router)
app.include_router(signals_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateGoalRequest(BaseModel):
    goal_spec: GoalSpec
    learning_profile: LearningProfile
    user_id: str = DEFAULT_USER_ID


class CreateGoalResponse(BaseModel):
    roadmap_id: str
    roadmap: RoadmapItem
    milestones: list[MilestoneItem]
    skillpaths: list[SkillPathItem]


class GenerateContentResponse(BaseModel):
    roadmap_id: str
    generated_skillpath_count: int
    roadmap: RoadmapFull


def _milestones_for_generation(roadmap: RoadmapFull) -> list[MilestoneItem]:
    return [
        MilestoneItem.model_validate(
            milestone.model_dump(exclude={"skillpaths", "recaps"})
        )
        for milestone in roadmap.milestones
    ]


def _skillpaths_from_roadmap(roadmap: RoadmapFull) -> list[SkillPathItem]:
    return [
        skillpath
        for milestone in roadmap.milestones
        for skillpath in milestone.skillpaths
    ]


async def _load_generation_context(
    user_id: str, roadmap_id: str
) -> tuple[GoalSpec, LearningProfile, RoadmapFull]:
    async with get_session() as session:
        try:
            goal = await goal_service.get_goal(user_id, session)
        except ValueError as e:
            raise HTTPException(
                status_code=404,
                detail=f"Goal not found for user {user_id}; create a goal before generating roadmap content.",
            ) from e

        try:
            profile = await learning_profile_service.get_learning_profile(
                user_id, session
            )
        except ValueError as e:
            raise HTTPException(
                status_code=404,
                detail=f"Learning profile not found for user {user_id}; create a learning profile before generating roadmap content.",
            ) from e

        try:
            roadmap = await roadmap_service.get_roadmap_full(
                user_id, roadmap_id, session
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Roadmap not found") from e

    return goal, profile, roadmap


async def _run_content_generation(
    goal: GoalSpec,
    profile: LearningProfile,
    roadmap: RoadmapFull,
    skillpaths: list[SkillPathItem],
) -> list[SkillPathItem]:
    if not skillpaths:
        return []

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _content_generator.invoke(
            {
                "goal_spec": goal,
                "learning_profile": profile,
                "milestones": _milestones_for_generation(roadmap),
                "skillpaths": skillpaths,
                "content_drafts": [],
            }
        ),
    )
    return result.get("generated_skillpaths", [])


async def _persist_generated_content(
    user_id: str, roadmap_id: str, generated_skillpaths: list[SkillPathItem]
) -> RoadmapFull:
    async with get_session() as session:
        await roadmap_service.save_generated_skillpaths(
            user_id=user_id,
            skillpaths=generated_skillpaths,
            session=session,
        )
        return await roadmap_service.get_roadmap_full(user_id, roadmap_id, session)


@app.get("/")
async def root():
    return {"status": "online", "message": "AntiCopilot API is running"}


@app.post("/v1/goals", response_model=CreateGoalResponse)
async def create_goal(request: CreateGoalRequest):
    """
    Generate a roadmap through LangGraph and persist it through the SQLAlchemy service layer.
    """
    roadmap_id = str(uuid.uuid4())
    planner = build_planner_graph()
    initial_state = {
        "goal_spec": request.goal_spec,
        "learning_profile": request.learning_profile,
        "roadmap_id": roadmap_id,
        "roadmap": None,
        "milestones": [],
        "skillpaths": [],
        "milestone_revision_count": 0,
        "skillpath_drafts": [],
        "skillpaths_review": [],
        "skillpath_revisions": [],
    }

    try:
        final_state = planner.invoke(initial_state)
        roadmap = final_state["roadmap"]
        milestones = final_state["milestones"]
        skillpaths = final_state["skillpaths"]

        async with get_session() as session:
            await goal_service.save_goal(request.user_id, request.goal_spec, session)
            await learning_profile_service.save_learning_profile(
                request.user_id, request.learning_profile, session
            )
            await roadmap_service.save_roadmap(
                user_id=request.user_id,
                roadmap_id=roadmap_id,
                title=roadmap.title,
                version=roadmap.version,
                summary=roadmap.summary,
                target_outcome=roadmap.target_outcome,
                assumptions=roadmap.assumptions,
                milestones=milestones,
                skillpaths=skillpaths,
                session=session,
            )

        return {
            "roadmap_id": roadmap_id,
            "roadmap": roadmap,
            "milestones": milestones,
            "skillpaths": skillpaths,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/roadmaps")
async def list_roadmaps(user_id: str = Query(default=DEFAULT_USER_ID)):
    """
    List saved roadmaps for one user.
    """
    try:
        async with get_session() as session:
            result = await session.execute(
                select(RoadmapModel).where(RoadmapModel.user_id == user_id)
            )
            return [
                {
                    "roadmap_id": row.roadmap_id,
                    "title": row.title,
                    "version": row.version,
                    "summary": row.summary,
                    "target_outcome": row.target_outcome,
                    "assumptions": row.assumptions or [],
                }
                for row in result.scalars()
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/v1/roadmaps/{roadmap_id}", response_model=RoadmapFull)
async def get_roadmap(
    roadmap_id: str, user_id: str = Query(default=DEFAULT_USER_ID)
):
    """
    Fetch a roadmap and nested milestones, skillpaths, and generated content.
    """
    try:
        async with get_session() as session:
            return await roadmap_service.get_roadmap_full(user_id, roadmap_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Roadmap not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/v1/roadmaps/{roadmap_id}/generate-content",
    response_model=GenerateContentResponse,
)
async def generate_roadmap_content(
    roadmap_id: str, user_id: str = Query(default=DEFAULT_USER_ID)
):
    """
    Generate learner-facing content for the next pending skillpath.
    """
    goal, profile, roadmap = await _load_generation_context(user_id, roadmap_id)
    pending_skillpaths = [
        skillpath
        for skillpath in _skillpaths_from_roadmap(roadmap)
        if skillpath.need_generation
    ]

    if len(pending_skillpaths) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Roadmap has multiple pending skillpaths. Generate one skillpath per request to avoid long-running HTTP calls.",
                "pending_skillpath_ids": [
                    skillpath.skillpath_id for skillpath in pending_skillpaths
                ],
                "endpoint": f"/v1/roadmaps/{roadmap_id}/skillpaths/{{skillpath_id}}/generate-content",
            },
        )

    generated_skillpaths = await _run_content_generation(
        goal, profile, roadmap, pending_skillpaths[:1]
    )
    refreshed = await _persist_generated_content(
        user_id, roadmap_id, generated_skillpaths
    )

    return GenerateContentResponse(
        roadmap_id=roadmap_id,
        generated_skillpath_count=len(generated_skillpaths),
        roadmap=refreshed,
    )


@app.post(
    "/v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/generate-content",
    response_model=GenerateContentResponse,
)
async def generate_skillpath_content(
    roadmap_id: str,
    skillpath_id: str,
    user_id: str = Query(default=DEFAULT_USER_ID),
    force: bool = Query(default=False),
):
    """
    Generate learner-facing content for one skillpath.
    """
    goal, profile, roadmap = await _load_generation_context(user_id, roadmap_id)
    skillpath = next(
        (
            item
            for item in _skillpaths_from_roadmap(roadmap)
            if item.skillpath_id == skillpath_id
        ),
        None,
    )
    if not skillpath:
        raise HTTPException(status_code=404, detail="Skillpath not found")

    selected = []
    if skillpath.need_generation or force:
        selected = [skillpath.model_copy(update={"need_generation": True})]

    generated_skillpaths = await _run_content_generation(
        goal, profile, roadmap, selected
    )
    refreshed = await _persist_generated_content(
        user_id, roadmap_id, generated_skillpaths
    )

    return GenerateContentResponse(
        roadmap_id=roadmap_id,
        generated_skillpath_count=len(generated_skillpaths),
        roadmap=refreshed,
    )


class UpdateSkillpathStatusRequest(BaseModel):
    status: Literal["ready", "generated", "revising", "completed", "revised"]


@app.post(
    "/v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/status",
    response_model=RoadmapFull,
)
async def update_skillpath_status(
    roadmap_id: str,
    skillpath_id: str,
    request: UpdateSkillpathStatusRequest,
    user_id: str = Query(default=DEFAULT_USER_ID),
):
    """
    Set a skillpath's lifecycle status. Idempotent — re-posting the same value
    is a no-op. Returns the refreshed roadmap so callers can sync with one
    merge pattern (same as generate-content). Transition legality is currently
    enforced by the frontend, not the backend.
    """
    async with get_session() as session:
        try:
            await roadmap_service.update_skillpath(
                user_id, skillpath_id, session, status=request.status
            )
            return await roadmap_service.get_roadmap_full(
                user_id, roadmap_id, session
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
