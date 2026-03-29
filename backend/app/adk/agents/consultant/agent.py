import os
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adk.tools.goal_spec import (
    check_goal_spec_missing_values,
    get_goal_spec,
    store_goal_spec,
)
from app.adk.tools.learning_profile import (
    check_learning_profile_missing_values,
    get_learning_profile,
    store_learning_profile,
)
from app.adk.tools.roadmap_generation import run_roadmap_pipeline
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.skills import load_skill_from_dir
from google.adk.tools import google_search, skill_toolset
from google.adk.tools.agent_tool import AgentTool


def get_current_time_for_planning() -> datetime:
    return datetime.now(ZoneInfo("Asia/Taipei"))


load_dotenv()
search_agent = Agent(
    model="gemini-2.5-flash",
    name="SearchAgent",
    instruction="""
    You're a specialist in Google Search, used for searching unfamiliar field
    """,
    tools=[google_search],
)
coding_agent = Agent(
    model="gemini-2.5-flash",
    name="CodeAgent",
    instruction="""
    You're a specialist in Code Execution
    """,
    code_executor=BuiltInCodeExecutor(),
)

roadmap_intake_skill = load_skill_from_dir(
    pathlib.Path(__file__).parent / "skills" / "roadmap-intake"
)

roadmap_skill_toolset = skill_toolset.SkillToolset(skills=[roadmap_intake_skill])

root_agent = Agent(
    name="RootAgent",
    model=os.getenv("ADK_AGENT_MODEL", "gemini-2.5-flash"),
    tools=[
        get_goal_spec,
        check_goal_spec_missing_values,
        store_goal_spec,
        get_learning_profile,
        check_learning_profile_missing_values,
        store_learning_profile,
        run_roadmap_pipeline,
        roadmap_skill_toolset,
        get_current_time_for_planning,
        AgentTool(agent=search_agent),
    ],
    instruction="""
    You are a learning roadmap intake and planning assistant.

    Follow the roadmap-intake skill as your primary policy for all user interaction —
    how to interpret messages, normalize input, ask follow-up questions, and avoid
    exposing schema friction.

    ## Operating Procedure

    **Step 1 — Collect and store**
    As the user provides information, call store_goal_spec or store_learning_profile
    immediately with whatever fields are now known. Do not wait for a complete profile.

    **Step 2 — Check readiness**
    After each storage call, check whether required fields are still missing.
    Never assume completeness — always verify through tools.

    **Step 3 — Ask for what's missing**
    If required fields remain, ask for the most important missing item using the
    intake skill's question style. One question at a time.

    **Step 4 — Generate**
    Once all required fields are confirmed complete, call the roadmap generation tool.
    If it reports missing state, return to Step 1.

    ## Required Fields

    goal_spec: title, description, target_outcome, deadline, criteria, constraints
    learning_profile: baseline_level, prior_knowledges, weak_areas, pace_preference,
    confidence_level, needs_recap, prefers_examples_first, overload_risk

    ## Hard Rules
    - Empty string, empty list, and None all count as missing.
    - Never invent user preferences, deadlines, or constraints.
    - Never overwrite previously stored fields unless the user explicitly updates them.
    - Never run generation while required fields are missing.
    - Prefer tool-based state over conversational memory alone.
    """,
)
