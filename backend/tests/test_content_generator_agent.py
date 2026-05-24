import json

from app.adk_agents.content_generator.agent import (
    _build_agent,
    _coerce_content_generation_output,
    _supports_adk_output_schema_with_tools,
)
from app.adk_agents.content_generator.schemas import (
    AdkArticleOutput,
    AdkCodingProblemOutput,
    AdkContentGenerationOutput,
)


def _make_output() -> AdkContentGenerationOutput:
    return AdkContentGenerationOutput(
        article=AdkArticleOutput(
            title="Read FastAPI routing",
            description="Learn route handlers.",
            skill_intro="Routes connect URLs to Python functions.",
            reading_content="FastAPI routes are declared with decorators.",
            references=[],
            source_notes=[],
        ),
        coding_problem=AdkCodingProblemOutput(
            title="Write a route",
            description="Practice defining a route.",
            prompt="Create a GET /health route.",
            difficulty="easy",
        ),
    )


def test_coerce_content_generation_output_accepts_model_instance():
    output = _make_output()

    assert (
        _coerce_content_generation_output(output).article.title
        == "Read FastAPI routing"
    )


def test_coerce_content_generation_output_accepts_dict():
    output = _make_output().model_dump(mode="json")

    assert (
        _coerce_content_generation_output(output).coding_problem.title
        == "Write a route"
    )


def test_coerce_content_generation_output_accepts_json_text():
    output = json.dumps(_make_output().model_dump(mode="json"))

    assert (
        _coerce_content_generation_output(output).article.description
        == "Learn route handlers."
    )


def test_build_agent_keeps_search_tools_and_omits_adk_output_schema_by_default():
    agent = _build_agent()

    assert agent.tools
    assert agent.output_schema is None


def test_supports_adk_output_schema_with_tools_uses_adk_compatibility_check(
    monkeypatch,
):
    monkeypatch.setattr(
        "google.adk.utils.output_schema_utils.can_use_output_schema_with_tools",
        lambda model: model == "supported-model",
    )

    assert _supports_adk_output_schema_with_tools("supported-model")
    assert not _supports_adk_output_schema_with_tools("unsupported-model")
