from app.db.session import get_session
from app.schema.entities import LearningProfile
from app.services import learning_profile as service
from fastmcp import FastMCP

learning_profile_mcp = FastMCP("learning_profile")


@learning_profile_mcp.tool()
async def save_learning_profile(
    user_id: str, profile: LearningProfile
) -> LearningProfile:
    """
    Save or replace a user's learning profile.
    Called by Google ADK after collecting profile details from the user.
    Creates the user record if it doesn't exist yet.
    """
    async with get_session() as session:
        return await service.save_learning_profile(user_id, profile, session)


@learning_profile_mcp.tool()
async def get_learning_profile(user_id: str) -> LearningProfile:
    """
    Fetch a user's learning profile.
    Called by the learning director agent before running the planner.
    """
    async with get_session() as session:
        return await service.get_learning_profile(user_id, session)
