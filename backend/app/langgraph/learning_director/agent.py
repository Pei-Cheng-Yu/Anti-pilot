import asyncio
import os
from typing import TypedDict

from app.db.session import get_session
from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.schema.entities import GoalSpec, LearningProfile
from app.services import roadmap as roadmap_service
from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

load_dotenv()

# Build planner graph once at startup.
_planner = build_planner_graph()

# MCP server URL where app/mcp/server.py is running.
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")


class LearningDirectorContext(TypedDict):
    user_id: str


@tool(parse_docstring=True)
async def run_planner(
    goal: GoalSpec,
    profile: LearningProfile,
    runtime: ToolRuntime[LearningDirectorContext],
) -> dict:
    """Run the full roadmap planner and persist the result.

    Use this after fetching the user's goal and learning profile.

    Args:
        goal: The user's learning goal.
        profile: The user's learning profile.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _planner.invoke({"goal_spec": goal, "learning_profile": profile}),
    )

    roadmap_id = result["roadmap_uuid"]
    roadmap = result.get("roadmap")
    user_id = runtime.context["user_id"]

    async with get_session() as session:
        await roadmap_service.save_roadmap(
            user_id=user_id,
            roadmap_id=roadmap_id,
            version=roadmap.version if roadmap else 1,
            summary=roadmap.summary if roadmap else "",
            target_outcome=roadmap.target_outcome if roadmap else goal.target_outcome,
            assumptions=roadmap.assumptions if roadmap else [],
            milestones=result["milestones"],
            skillpaths=result["skillpaths"],
            session=session,
        )

    return {"roadmap_id": roadmap_id}


async def inject_user_id(
    request: MCPToolCallRequest,
    handler,
):
    """Inject runtime user_id into MCP tool calls that accept a user_id argument."""
    runtime = request.runtime
    user_id = runtime.context["user_id"]
    managed_tool_prefixes = ("goal_", "learning_profile_", "roadmap_")

    if request.name.startswith(managed_tool_prefixes):
        modified_request = request.override(args={**request.args, "user_id": user_id})
        return await handler(modified_request)

    return await handler(request)


_SYSTEM_PROMPT = """You are a learning director.

Generate personalized learning roadmaps using the available tools.
Use MCP tools for saved user data and roadmap updates.
Any MCP tool that needs user_id receives it automatically from runtime context.
"""


async def create_learning_director():
    """Create the learning director deep agent using MCP tools plus a local planner tool."""
    client = MultiServerMCPClient(
        {
            "anti-pilot": {
                "transport": "http",
                "url": MCP_SERVER_URL,
            }
        },
        tool_interceptors=[inject_user_id],
    )
    mcp_tools = await client.get_tools()
    return create_deep_agent(
        model="google_genai:gemini-2.5-flash-lite",
        system_prompt=_SYSTEM_PROMPT,
        context_schema=LearningDirectorContext,
        skills=[SKILLS_DIR],
        tools=[run_planner, *mcp_tools],
    )
