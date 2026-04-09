from app.db.session import get_session
from app.schema.entities import MilestoneItem, RoadmapFull, SkillPathItem
from app.services import roadmap as service
from fastmcp import FastMCP

roadmap_mcp = FastMCP("roadmap")


@roadmap_mcp.tool()
async def get_roadmap_full(user_id: str, roadmap_id: str) -> RoadmapFull:
    """
    Fetch the full roadmap as a nested structure for one user.
    Returns all milestones with their skillpaths nested inside, ordered by order_index.
    Use this to review the roadmap after planning.
    """
    async with get_session() as session:
        return await service.get_roadmap_full(user_id, roadmap_id, session)


@roadmap_mcp.tool()
async def update_milestone(
    user_id: str,
    milestone_id: str,
    title: str | None = None,
    description: str | None = None,
    objective: str | None = None,
    estimated_hours: float | None = None,
    need_modification: bool | None = None,
    revision_reason: str | None = None,
) -> MilestoneItem:
    """
    Patch one or more fields on a user's milestone directly in DB.
    Use this during review to fix issues without rerunning the planner.
    Only pass the fields you want to change.
    """
    fields = {
        k: v
        for k, v in {
            "title": title,
            "description": description,
            "objective": objective,
            "estimated_hours": estimated_hours,
            "need_modification": need_modification,
            "revision_reason": revision_reason,
        }.items()
        if v is not None
    }
    async with get_session() as session:
        return await service.update_milestone(user_id, milestone_id, session, **fields)


@roadmap_mcp.tool()
async def update_skillpath(
    user_id: str,
    skillpath_id: str,
    title: str | None = None,
    description: str | None = None,
    estimated_hours: float | None = None,
    need_modification: bool | None = None,
    revision_reason: str | None = None,
    need_generation: bool | None = None,
) -> SkillPathItem:
    """
    Patch one or more fields on a user's skillpath directly in DB.
    Use this during review to fix issues without rerunning the planner.
    Only pass the fields you want to change.
    """
    fields = {
        k: v
        for k, v in {
            "title": title,
            "description": description,
            "estimated_hours": estimated_hours,
            "need_modification": need_modification,
            "revision_reason": revision_reason,
            "need_generation": need_generation,
        }.items()
        if v is not None
    }
    async with get_session() as session:
        return await service.update_skillpath(user_id, skillpath_id, session, **fields)
