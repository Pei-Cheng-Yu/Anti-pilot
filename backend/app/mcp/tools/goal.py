from app.db.session import get_session
from app.schema.entities import GoalSpec
from app.services import goal as service
from fastmcp import FastMCP

goal_mcp = FastMCP("goal")


@goal_mcp.tool()
async def save_goal(
    user_id: str, goal: GoalSpec, goal_id: str | None = None
) -> GoalSpec:
    """
    Save or replace a user's learning goal.
    Called by Google ADK after collecting goal details from the user.
    Creates the user record if it doesn't exist yet.
    """
    async with get_session() as session:
        return await service.save_goal(user_id, goal, session, goal_id=goal_id)


@goal_mcp.tool()
async def get_goal(user_id: str, goal_id: str | None = None) -> GoalSpec:
    """
    Fetch a user's learning goal.
    Called by the learning director agent before running the planner.
    """
    async with get_session() as session:
        return await service.get_goal(user_id, session, goal_id=goal_id)
