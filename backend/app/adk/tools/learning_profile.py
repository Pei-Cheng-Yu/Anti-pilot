from __future__ import annotations

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


def store_learning_profile(
    baseline_level: str | None = None,
    prior_knowledges: list[str] | None = None,
    weak_areas: list[str] | None = None,
    pace_preference: str | None = None,
    confidence_level: str | None = None,
    needs_recap: bool | None = None,
    prefers_examples_first: bool | None = None,
    overload_risk: str | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Store or update the user's learning profile in session state.

    Only provided parameters will overwrite existing values in state.
    Missing parameters will keep the old value if present, otherwise default
    to an empty string, empty list, or None for boolean fields.

    Args:
        baseline_level: The user's current overall level related to the goal, option: ["beginner", "intermediate", "advanced"].
        prior_knowledges: Relevant knowledge or skills the user already has.
        weak_areas: Topics or skills the user struggles with.
        pace_preference: Preferred learning speed or workload intensity, option: ["slow", "balanced", "intensive"].
        confidence_level: Current confidence level for this learning goal, option: ["low", "medium", "high"].
        needs_recap: Whether the user benefits from review and recap.
        prefers_examples_first: Whether the user learns better from examples first.
        overload_risk: Estimated risk of the user feeling overwhelmed, option: ["low", "medium", "high"].
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary containing the updated learning profile.
    """
    current = tool_context.state.get("learning_profile", {})

    updated = {
        "baseline_level": (
            _normalize_optional_str(baseline_level)
            if baseline_level is not None
            else current.get("baseline_level", "")
        ),
        "prior_knowledges": (
            _normalize_optional_str_list(prior_knowledges)
            if prior_knowledges is not None
            else current.get("prior_knowledges", [])
        ),
        "weak_areas": (
            _normalize_optional_str_list(weak_areas)
            if weak_areas is not None
            else current.get("weak_areas", [])
        ),
        "pace_preference": (
            _normalize_optional_str(pace_preference)
            if pace_preference is not None
            else current.get("pace_preference", "")
        ),
        "confidence_level": (
            _normalize_optional_str(confidence_level)
            if confidence_level is not None
            else current.get("confidence_level", "")
        ),
        "needs_recap": (
            needs_recap if needs_recap is not None else current.get("needs_recap", None)
        ),
        "prefers_examples_first": (
            prefers_examples_first
            if prefers_examples_first is not None
            else current.get("prefers_examples_first", None)
        ),
        "overload_risk": (
            _normalize_optional_str(overload_risk)
            if overload_risk is not None
            else current.get("overload_risk", "")
        ),
    }

    tool_context.state["learning_profile"] = updated

    return {
        "status": "success",
        "message": "Learning profile stored successfully.",
        "learning_profile": updated,
    }


def get_learning_profile(tool_context: ToolContext) -> dict:
    """Retrieve the stored learning profile from session state.

    Args:
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary containing the stored learning profile.
    """
    profile = tool_context.state.get("learning_profile", {})

    return {
        "status": "success",
        "learning_profile": {
            "baseline_level": profile.get("baseline_level", ""),
            "prior_knowledges": profile.get("prior_knowledges", []),
            "weak_areas": profile.get("weak_areas", []),
            "pace_preference": profile.get("pace_preference", ""),
            "confidence_level": profile.get("confidence_level", ""),
            "needs_recap": profile.get("needs_recap", None),
            "prefers_examples_first": profile.get("prefers_examples_first", None),
            "overload_risk": profile.get("overload_risk", ""),
        },
    }


def check_learning_profile_missing_values(tool_context: ToolContext) -> dict:
    """Check which LearningProfile fields are still missing from session state.

    A string field is considered missing if it is an empty string.
    A list field is considered missing if it is an empty list.
    A boolean field is considered missing if it is None.

    Args:
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary containing whether the learning profile is complete and
        which fields are still missing.
    """
    profile = tool_context.state.get("learning_profile", {})

    missing_fields: list[str] = []

    if _is_missing_string(profile.get("baseline_level", "")):
        missing_fields.append("baseline_level")
    if _is_missing_list(profile.get("prior_knowledges", [])):
        missing_fields.append("prior_knowledges")
    if _is_missing_list(profile.get("weak_areas", [])):
        missing_fields.append("weak_areas")
    if _is_missing_string(profile.get("pace_preference", "")):
        missing_fields.append("pace_preference")
    if _is_missing_string(profile.get("confidence_level", "")):
        missing_fields.append("confidence_level")
    if profile.get("needs_recap", None) is None:
        missing_fields.append("needs_recap")
    if profile.get("prefers_examples_first", None) is None:
        missing_fields.append("prefers_examples_first")
    if _is_missing_string(profile.get("overload_risk", "")):
        missing_fields.append("overload_risk")

    return {
        "is_complete": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "learning_profile": {
            "baseline_level": profile.get("baseline_level", ""),
            "prior_knowledges": profile.get("prior_knowledges", []),
            "weak_areas": profile.get("weak_areas", []),
            "pace_preference": profile.get("pace_preference", ""),
            "confidence_level": profile.get("confidence_level", ""),
            "needs_recap": profile.get("needs_recap", None),
            "prefers_examples_first": profile.get("prefers_examples_first", None),
            "overload_risk": profile.get("overload_risk", ""),
        },
    }
