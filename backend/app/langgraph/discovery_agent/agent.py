import os
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from app.db.session import get_session
from app.langgraph.discovery_agent.checkpointing import create_postgres_checkpointer
from app.langgraph.discovery_agent.prompts import DISCOVERY_SYSTEM_PROMPT
from app.langgraph.discovery_agent.schemas import DiscoveryContext, DiscoveryResponse
from app.schema.entities import GoalSpec
from app.services import discovery as discovery_service
from app.services import goal as goal_service
from app.services import learning_profile as learning_profile_service
from deepagents import AsyncSubAgent, create_deep_agent
from dotenv import load_dotenv
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/mcp")
SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")
DISCOVERY_MCP_TOOL_ALLOWLIST = {
    "learning_profile_save_learning_profile",
    "learning_memory_retrieve_learning_memory",
    "learning_memory_get_skill_mastery_state",
    "learning_memory_add_memory_note",
}


def filter_discovery_tools(tools: Iterable[Any]) -> list[Any]:
    """Return only MCP tools the Discovery Agent is allowed to use."""
    return [
        tool
        for tool in tools
        if getattr(tool, "name", None) in DISCOVERY_MCP_TOOL_ALLOWLIST
    ]


def _discovery_user_id(runtime: ToolRuntime[DiscoveryContext]) -> str:
    context = runtime.context or {}
    user_id = context.get("user_id")
    if not user_id:
        raise ValueError("Discovery Agent tools require user_id from runtime context.")
    return user_id


def _discovery_goal_id(runtime: ToolRuntime[DiscoveryContext]) -> str | None:
    context = runtime.context or {}
    return context.get("goal_id")


def _discovery_conversation_id(runtime: ToolRuntime[DiscoveryContext]) -> str | None:
    context = runtime.context or {}
    return context.get("conversation_id")


@tool(parse_docstring=True)
async def discovery_get_goal_status(
    runtime: ToolRuntime[DiscoveryContext],
) -> dict[str, Any]:
    """Check whether the current learner has a saved goal.

    Use this at the start of discovery. Missing goals are normal for new
    discovery conversations and return exists=false instead of failing.
    """
    user_id = _discovery_user_id(runtime)
    async with get_session() as session:
        try:
            goal = await goal_service.get_goal(user_id, session)
        except ValueError as e:
            if "No goal found" in str(e):
                return {"exists": False, "goal": None}
            raise

    return {"exists": True, "goal": goal.model_dump(mode="json")}


@tool(parse_docstring=True)
async def discovery_save_goal(
    goal: GoalSpec,
    runtime: ToolRuntime[DiscoveryContext],
) -> dict[str, Any]:
    """Save the current learner goal and bind the Discovery conversation.

    Use this instead of raw goal MCP tools. It reuses the current goal_id when
    the conversation is already bound, otherwise it generates a new goal_id and
    binds the conversation after saving.

    Args:
        goal: The learner's confirmed learning goal.
    """
    user_id = _discovery_user_id(runtime)
    goal_id = _discovery_goal_id(runtime) or str(uuid4())
    conversation_id = _discovery_conversation_id(runtime)
    async with get_session() as session:
        saved = await goal_service.save_goal(
            user_id,
            goal,
            session,
            goal_id=goal_id,
        )
        if conversation_id is not None and _discovery_goal_id(runtime) is None:
            await discovery_service.bind_discovery_conversation_goal(
                conversation_id,
                user_id,
                goal_id,
                session,
            )

    return {"goal_id": goal_id, "goal": saved.model_dump(mode="json")}


@tool(parse_docstring=True)
async def discovery_get_learning_profile_status(
    runtime: ToolRuntime[DiscoveryContext],
) -> dict[str, Any]:
    """Check whether the current learner has a saved learning profile.

    Use this at the start of discovery. Missing profiles are normal for new
    discovery conversations and return exists=false instead of failing.
    """
    user_id = _discovery_user_id(runtime)
    async with get_session() as session:
        try:
            profile = await learning_profile_service.get_learning_profile(
                user_id, session
            )
        except ValueError as e:
            if "No learning profile found" in str(e):
                return {"exists": False, "learning_profile": None}
            raise

    return {
        "exists": True,
        "learning_profile": profile.model_dump(mode="json"),
    }


async def inject_user_id(
    request: MCPToolCallRequest,
    handler,
):
    """Inject runtime user_id into MCP tool calls that accept a user_id argument."""
    runtime = request.runtime
    user_id = runtime.context["user_id"]
    managed_tool_prefixes = (
        "goal_",
        "learning_profile_",
        "learning_memory_",
    )

    if request.name.startswith(managed_tool_prefixes):
        args = dict(request.args)
        if "user_id" in args:
            modified_args = {**args, "user_id": user_id}
        else:
            modified_args = args
            for nested_key in ("note", "query", "request"):
                nested_value = args.get(nested_key)
                if isinstance(nested_value, dict):
                    modified_args = {
                        **args,
                        nested_key: {**nested_value, "user_id": user_id},
                    }
                    break
        modified_request = request.override(args=modified_args)
        return await handler(modified_request)

    return await handler(request)


async def create_discovery_agent(
    checkpointer=None, *, use_custom_checkpointer: bool = True
):
    """Create the Discovery Agent deep agent."""
    if checkpointer is None and use_custom_checkpointer:
        checkpointer = await create_postgres_checkpointer(setup=False)

    client = MultiServerMCPClient(
        {
            "anti-pilot": {
                "transport": "http",
                "url": MCP_SERVER_URL,
            }
        },
        tool_interceptors=[inject_user_id],
    )
    mcp_tools = filter_discovery_tools(await client.get_tools())
    learning_director: AsyncSubAgent = {
        "name": "learning_director",
        "description": "Generate and persist personalized roadmaps from saved goal and profile entities.",
        "graph_id": "learning_director",
    }

    return create_deep_agent(
        model="google_genai:gemini-3.1-pro-preview",
        tools=[
            discovery_get_goal_status,
            discovery_save_goal,
            discovery_get_learning_profile_status,
            *mcp_tools,
        ],
        system_prompt=DISCOVERY_SYSTEM_PROMPT,
        context_schema=DiscoveryContext,
        response_format=DiscoveryResponse,
        subagents=[learning_director],
        checkpointer=checkpointer,
        skills=[SKILLS_DIR],
    )


async def _build_module_graph():
    return await create_discovery_agent(use_custom_checkpointer=False)


if os.getenv("ANTI_PILOT_BUILD_MODULE_GRAPHS") == "1":
    import asyncio

    graph = asyncio.run(_build_module_graph())
else:
    graph = None
