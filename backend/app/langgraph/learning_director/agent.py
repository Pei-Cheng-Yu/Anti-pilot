import asyncio
import os
import re
from typing import NotRequired, TypedDict

from app.db.session import get_session
from app.langgraph.content_generation.graphs.generate_learning_content.graph import (
    build_learning_content_graph,
)
from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.schema.entities import GoalSpec, LearningProfile, MilestoneItem
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
_content_generator = build_learning_content_graph()

# MCP server URL where app/mcp/server.py is running.
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/mcp")
LEARNING_DIRECTOR_MODEL = "google_genai:gemini-3.1-flash-lite-preview"
SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")


class LearningDirectorContext(TypedDict):
    user_id: str
    goal_id: NotRequired[str]


def learning_director_model() -> str:
    return os.getenv("LEARNING_DIRECTOR_MODEL", LEARNING_DIRECTOR_MODEL)


def _message_content(message) -> str:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _context_marker_from_state(state: dict | None, marker: str) -> str | None:
    if not state:
        return None

    pattern = re.compile(rf"\b{re.escape(marker)}:\s*([^\s,;)]+)")
    for message in reversed(state.get("messages", [])):
        for line in _message_content(message).splitlines():
            match = pattern.search(line.strip())
            if match:
                return match.group(1).rstrip(".")
    return None


def _configurable_value(runtime: ToolRuntime[LearningDirectorContext], key: str):
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable")
    if isinstance(configurable, dict):
        return configurable.get(key)
    return None


def _mcp_tool_accepts_top_level_user_id(tool_name: str) -> bool:
    top_level_memory_tools = {
        "learning_memory_get_skill_mastery_state",
        "learning_memory_update_memory_note",
        "learning_memory_resolve_memory_note",
        "learning_memory_delete_memory_note",
    }
    return (
        tool_name.startswith(("goal_", "learning_profile_", "roadmap_"))
        or tool_name in top_level_memory_tools
    )


def planner_roadmap_id(result: dict) -> str:
    roadmap_id = result.get("roadmap_id") or result.get("roadmap_uuid")
    if not roadmap_id:
        raise ValueError("Planner result did not include roadmap_id or roadmap_uuid.")
    return roadmap_id


def tool_user_id(
    runtime: ToolRuntime[LearningDirectorContext], user_id: str | None
) -> str:
    context = runtime.context or {}
    resolved_user_id = (
        context.get("user_id")
        or user_id
        or _configurable_value(runtime, "user_id")
        or _context_marker_from_state(runtime.state, "CURRENT_USER_ID")
    )
    if not resolved_user_id:
        raise ValueError(
            "Learning Director tools require user_id from runtime context or "
            "explicit tool arguments."
        )
    return resolved_user_id


def tool_goal_id(
    runtime: ToolRuntime[LearningDirectorContext], goal_id: str | None
) -> str:
    context = runtime.context or {}
    resolved_goal_id = (
        context.get("goal_id")
        or goal_id
        or _configurable_value(runtime, "goal_id")
        or _context_marker_from_state(runtime.state, "CURRENT_GOAL_ID")
    )
    if not resolved_goal_id:
        raise ValueError(
            "Learning Director planner requires goal_id from runtime context or "
            "explicit tool arguments."
        )
    return resolved_goal_id


@tool(parse_docstring=True)
async def run_planner(
    goal: GoalSpec,
    profile: LearningProfile,
    runtime: ToolRuntime[LearningDirectorContext],
    user_id: str | None = None,
    goal_id: str | None = None,
) -> dict:
    """Run the full roadmap planner and persist the result.

    Use this after fetching the user's goal and learning profile.

    Args:
        goal: The user's learning goal.
        profile: The user's learning profile.
        user_id: The current user ID, only needed when runtime context is unavailable.
        goal_id: The current goal ID, only needed when runtime context is unavailable.
    """
    resolved_user_id = tool_user_id(runtime, user_id)
    resolved_goal_id = tool_goal_id(runtime, goal_id)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _planner.invoke({"goal_spec": goal, "learning_profile": profile}),
    )

    roadmap_id = planner_roadmap_id(result)
    roadmap = result.get("roadmap")

    async with get_session() as session:
        await roadmap_service.save_roadmap(
            user_id=resolved_user_id,
            goal_id=resolved_goal_id,
            roadmap_id=roadmap_id,
            title=roadmap.title if roadmap else goal.title,
            version=roadmap.version if roadmap else 1,
            summary=roadmap.summary if roadmap else "",
            target_outcome=roadmap.target_outcome if roadmap else goal.target_outcome,
            assumptions=roadmap.assumptions if roadmap else [],
            milestones=result["milestones"],
            skillpaths=result["skillpaths"],
            session=session,
        )

    return {"roadmap_id": roadmap_id}


@tool(parse_docstring=True)
async def run_content_generator(
    roadmap_id: str,
    goal: GoalSpec,
    profile: LearningProfile,
    runtime: ToolRuntime[LearningDirectorContext],
    user_id: str | None = None,
) -> dict:
    """Generate and persist learning content for skillpaths in a saved roadmap.

    Use this after the roadmap has been generated and reviewed.

    Args:
        roadmap_id: The saved roadmap ID to generate learning content for.
        goal: The user's learning goal.
        profile: The user's learning profile.
        user_id: The current user ID, only needed when runtime context is unavailable.
    """
    resolved_user_id = tool_user_id(runtime, user_id)

    async with get_session() as session:
        roadmap = await roadmap_service.get_roadmap_full(
            resolved_user_id, roadmap_id, session
        )

    milestones = [
        MilestoneItem.model_validate(
            milestone.model_dump(exclude={"skillpaths", "recaps"})
        )
        for milestone in roadmap.milestones
    ]
    skillpaths = [
        skillpath
        for milestone in roadmap.milestones
        for skillpath in milestone.skillpaths
    ]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _content_generator.invoke(
            {
                "goal_spec": goal,
                "learning_profile": profile,
                "milestones": milestones,
                "skillpaths": skillpaths,
                "content_drafts": [],
            }
        ),
    )
    generated_skillpaths = result.get("generated_skillpaths", [])

    async with get_session() as session:
        await roadmap_service.save_generated_skillpaths(
            user_id=resolved_user_id,
            skillpaths=generated_skillpaths,
            session=session,
        )

    return {
        "roadmap_id": roadmap_id,
        "generated_skillpath_count": len(generated_skillpaths),
    }


async def inject_user_id(
    request: MCPToolCallRequest,
    handler,
):
    """Inject runtime user_id into MCP tool calls that accept a user_id argument."""
    runtime = request.runtime
    context = runtime.context or {}
    state = getattr(runtime, "state", None)
    args = dict(request.args)
    user_id = (
        context.get("user_id")
        or args.get("user_id")
        or _configurable_value(runtime, "user_id")
        or _context_marker_from_state(state, "CURRENT_USER_ID")
    )
    goal_id = (
        context.get("goal_id")
        or args.get("goal_id")
        or _configurable_value(runtime, "goal_id")
        or _context_marker_from_state(state, "CURRENT_GOAL_ID")
    )
    managed_tool_prefixes = (
        "goal_",
        "learning_profile_",
        "roadmap_",
        "learning_memory_",
        "code_correction_",
    )

    if request.name.startswith(managed_tool_prefixes):
        if not user_id:
            raise ValueError(
                "Learning Director MCP tool calls require user_id from runtime "
                "context or explicit tool arguments."
            )
        modified_args = args
        if "user_id" in args or _mcp_tool_accepts_top_level_user_id(request.name):
            modified_args = {**modified_args, "user_id": user_id}
        if goal_id and (request.name == "goal_get_goal" or "goal_id" in args):
            modified_args = {**modified_args, "goal_id": goal_id}
        if "user_id" not in args:
            for nested_key in ("note", "attempt", "query", "request"):
                nested_value = modified_args.get(nested_key)
                if isinstance(nested_value, dict):
                    modified_args = {
                        **modified_args,
                        nested_key: {**nested_value, "user_id": user_id},
                    }
                    break
        modified_request = request.override(args=modified_args)
        return await handler(modified_request)

    return await handler(request)


_SYSTEM_PROMPT = """You are a learning director.

Generate personalized learning roadmaps using the available tools.
Use MCP tools for saved user data and roadmap updates.
Any MCP tool that needs user_id receives it automatically from runtime context.
If the invoking Discovery Agent provides `CURRENT_USER_ID`, pass that value as
`user_id` to `run_planner`, `run_content_generator`, and any MCP tool call that
requires user_id when runtime context is unavailable.
If the invoking Discovery Agent provides `CURRENT_GOAL_ID`, pass that value as
`goal_id` to `goal_get_goal` and `run_planner` when runtime context is unavailable.
After roadmap generation, you may mark skillpaths with optional content-planning guidance such as practice mode, example needs, and article depth when the roadmap context makes those decisions clear.
When the user asks for learning content to be generated, run the content generator after the saved roadmap is ready; it persists generated content to the database.
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
        model=learning_director_model(),
        system_prompt=_SYSTEM_PROMPT,
        context_schema=LearningDirectorContext,
        skills=[SKILLS_DIR],
        tools=[run_planner, run_content_generator, *mcp_tools],
    )


if os.getenv("ANTI_PILOT_BUILD_MODULE_GRAPHS") == "1":
    graph = asyncio.run(create_learning_director())
else:
    graph = None
