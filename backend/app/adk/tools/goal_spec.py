from __future__ import annotations

from datetime import date
from typing import Any

from google.adk.tools import ToolContext


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip()


def _normalize_optional_str_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return [v.strip() for v in values if isinstance(v, str) and v.strip()]


def _is_missing_string(value: Any) -> bool:
    return not isinstance(value, str) or value.strip() == ""


def _is_missing_list(value: Any) -> bool:
    return not isinstance(value, list) or len(value) == 0


def store_goal_spec(
    title: str | None = None,
    description: str | None = None,
    target_outcome: str | None = None,
    deadline: date | None = None,
    criteria: list[str] | None = None,
    constraints: list[str] | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Store or update the user's goal specification in session state.

    Only provided parameters will overwrite existing values in state.
    Missing parameters will keep the old value if present, otherwise default
    to an empty string or empty list.

    Args:
        title: Short title of the user's learning goal.
        description: Detailed description of what the user wants to learn.
        target_outcome: Expected outcome or capability after learning.
        deadline: Target deadline in ISO date , such as '2026-06-30'.
        criteria: Conditions used to judge whether the goal is completed successfully.
        constraints: Constraints affecting the learning plan, such as time or background.
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary containing the updated goal specification.
    """
    current = tool_context.state.get("goal_spec", {})

    updated = {
        "title": (
            _normalize_optional_str(title)
            if title is not None
            else current.get("title", "")
        ),
        "description": (
            _normalize_optional_str(description)
            if description is not None
            else current.get("description", "")
        ),
        "target_outcome": (
            _normalize_optional_str(target_outcome)
            if target_outcome is not None
            else current.get("target_outcome", "")
        ),
        "deadline": (
            _normalize_optional_str(deadline)
            if deadline is not None
            else current.get("deadline", "")
        ),
        "criteria": (
            _normalize_optional_str_list(criteria)
            if criteria is not None
            else current.get("criteria", [])
        ),
        "constraints": (
            _normalize_optional_str_list(constraints)
            if constraints is not None
            else current.get("constraints", [])
        ),
    }

    tool_context.state["goal_spec"] = updated

    return {
        "status": "success",
        "message": "Goal specification stored successfully.",
        "goal_spec": updated,
    }


def get_goal_spec(tool_context: ToolContext) -> dict:
    """Retrieve the stored goal specification from session state.

    Args:
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary containing the stored goal specification.
    """
    goal_spec = tool_context.state.get("goal_spec", {})

    return {
        "status": "success",
        "goal_spec": {
            "title": goal_spec.get("title", ""),
            "description": goal_spec.get("description", ""),
            "target_outcome": goal_spec.get("target_outcome", ""),
            "deadline": goal_spec.get("deadline", ""),
            "criteria": goal_spec.get("criteria", []),
            "constraints": goal_spec.get("constraints", []),
        },
    }


def check_goal_spec_missing_values(tool_context: ToolContext) -> dict:
    """Check which GoalSpec fields are still missing from session state.

    A string field is considered missing if it is an empty string.
    A list field is considered missing if it is an empty list.

    Args:
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary containing whether the goal spec is complete and
        which fields are still missing.
    """
    goal_spec = tool_context.state.get("goal_spec", {})

    missing_fields: list[str] = []

    if _is_missing_string(goal_spec.get("title", "")):
        missing_fields.append("title")
    if _is_missing_string(goal_spec.get("description", "")):
        missing_fields.append("description")
    if _is_missing_string(goal_spec.get("target_outcome", "")):
        missing_fields.append("target_outcome")
    if _is_missing_string(goal_spec.get("deadline", "")):
        missing_fields.append("deadline")
    if _is_missing_list(goal_spec.get("criteria", [])):
        missing_fields.append("criteria")
    if _is_missing_list(goal_spec.get("constraints", [])):
        missing_fields.append("constraints")

    return {
        "is_complete": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "goal_spec": {
            "title": goal_spec.get("title", ""),
            "description": goal_spec.get("description", ""),
            "target_outcome": goal_spec.get("target_outcome", ""),
            "deadline": goal_spec.get("deadline", ""),
            "criteria": goal_spec.get("criteria", []),
            "constraints": goal_spec.get("constraints", []),
        },
    }
