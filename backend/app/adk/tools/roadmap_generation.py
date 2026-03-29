from __future__ import annotations

from pathlib import Path

from app.langgraph.planner.graphs.evaluate.graph import build_evaluate_graph
from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.langgraph.planner.schema.entities import GoalSpec, LearningProfile
from dotenv import load_dotenv
from google.adk.tools import ToolContext

# Load .env so tracing / config works when the tool runs
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _get_goal_spec_from_state(tool_context: ToolContext) -> dict:
    goal_spec = tool_context.state.get("goal_spec", {})
    return {
        "title": goal_spec.get("title", ""),
        "description": goal_spec.get("description", ""),
        "target_outcome": goal_spec.get("target_outcome", ""),
        "deadline": goal_spec.get("deadline", ""),
        "criteria": goal_spec.get("criteria", []),
        "constraints": goal_spec.get("constraints", []),
    }


def _get_learning_profile_from_state(tool_context: ToolContext) -> dict:
    profile = tool_context.state.get("learning_profile", {})
    return {
        "baseline_level": profile.get("baseline_level", ""),
        "prior_knowledges": profile.get("prior_knowledges", []),
        "weak_areas": profile.get("weak_areas", []),
        "pace_preference": profile.get("pace_preference", ""),
        "confidence_level": profile.get("confidence_level", ""),
        "needs_recap": profile.get("needs_recap", None),
        "prefers_examples_first": profile.get("prefers_examples_first", None),
        "overload_risk": profile.get("overload_risk", ""),
    }


def _is_missing_string(value) -> bool:
    return not isinstance(value, str) or value.strip() == ""


def _is_missing_list(value) -> bool:
    return not isinstance(value, list) or len(value) == 0


def _check_goal_spec_missing_from_state(tool_context: ToolContext) -> list[str]:
    goal_spec = _get_goal_spec_from_state(tool_context)

    missing_fields: list[str] = []

    if _is_missing_string(goal_spec["title"]):
        missing_fields.append("title")
    if _is_missing_string(goal_spec["description"]):
        missing_fields.append("description")
    if _is_missing_string(goal_spec["target_outcome"]):
        missing_fields.append("target_outcome")
    if _is_missing_string(goal_spec["deadline"]):
        missing_fields.append("deadline")
    if _is_missing_list(goal_spec["criteria"]):
        missing_fields.append("criteria")
    if _is_missing_list(goal_spec["constraints"]):
        missing_fields.append("constraints")

    return missing_fields


def _check_learning_profile_missing_from_state(tool_context: ToolContext) -> list[str]:
    profile = _get_learning_profile_from_state(tool_context)

    missing_fields: list[str] = []

    if _is_missing_string(profile["baseline_level"]):
        missing_fields.append("baseline_level")
    if _is_missing_list(profile["prior_knowledges"]):
        missing_fields.append("prior_knowledges")
    if _is_missing_list(profile["weak_areas"]):
        missing_fields.append("weak_areas")
    if _is_missing_string(profile["pace_preference"]):
        missing_fields.append("pace_preference")
    if _is_missing_string(profile["confidence_level"]):
        missing_fields.append("confidence_level")
    if profile["needs_recap"] is None:
        missing_fields.append("needs_recap")
    if profile["prefers_examples_first"] is None:
        missing_fields.append("prefers_examples_first")
    if _is_missing_string(profile["overload_risk"]):
        missing_fields.append("overload_risk")

    return missing_fields


def run_roadmap_pipeline(tool_context: ToolContext) -> dict:
    """Run the roadmap generation and evaluation pipeline using data stored in session state.

    This tool reads goal_spec and learning_profile from the current ADK session state.
    It first checks whether either object still has missing fields. If anything is missing,
    it returns a structured response describing what must be collected before the pipeline
    can run. If all required fields are present, it validates the state into GoalSpec and
    LearningProfile models, runs the planner graph, then runs the evaluate graph.

    Args:
        tool_context: The ADK tool context containing the current session state.

    Returns:
        A dictionary indicating whether the pipeline ran successfully, whether more
        user information is needed, and the final graph outputs when successful.
    """
    goal_missing = _check_goal_spec_missing_from_state(tool_context)
    profile_missing = _check_learning_profile_missing_from_state(tool_context)

    if goal_missing or profile_missing:
        return {
            "status": "missing_required_state",
            "can_run": False,
            "message": (
                "The roadmap pipeline cannot run yet because required fields are still missing."
            ),
            "missing": {
                "goal_spec": goal_missing,
                "learning_profile": profile_missing,
            },
            "goal_spec": _get_goal_spec_from_state(tool_context),
            "learning_profile": _get_learning_profile_from_state(tool_context),
        }

    try:
        goal_spec = GoalSpec.model_validate(_get_goal_spec_from_state(tool_context))
        learning_profile = LearningProfile.model_validate(
            _get_learning_profile_from_state(tool_context)
        )
    except Exception as exc:
        return {
            "status": "validation_error",
            "can_run": False,
            "message": "Stored state exists but failed schema validation.",
            "error": str(exc),
            "goal_spec": _get_goal_spec_from_state(tool_context),
            "learning_profile": _get_learning_profile_from_state(tool_context),
        }

    initial_state = {
        "goal_spec": goal_spec,
        "learning_profile": learning_profile,
    }

    try:
        planner_graph = build_planner_graph()
        evaluate_graph = build_evaluate_graph()

        planner_result = planner_graph.invoke(initial_state)
        evaluate_result = evaluate_graph.invoke(planner_result)
        planner_result = "first version is done"
        evaluate_result = "evaluate finish"
        # Optional: save outputs back into ADK state for later turns
        tool_context.state["planner_result"] = planner_result
        tool_context.state["evaluate_result"] = evaluate_result

        return {
            "status": "success",
            "can_run": True,
            "message": "Roadmap generation and evaluation completed successfully.",
            "planner_result": planner_result,
            "evaluate_result": evaluate_result,
        }

    except Exception as exc:
        return {
            "status": "execution_error",
            "can_run": False,
            "message": "The roadmap pipeline failed during execution.",
            "error": str(exc),
        }
