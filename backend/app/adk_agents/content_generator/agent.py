import asyncio
import os
from uuid import uuid4

from app.adk_agents.content_generator.prompts import (
    CONTENT_GENERATOR_INSTRUCTION,
    build_content_generation_prompt,
)
from app.adk_agents.content_generator.schemas import (
    AdkContentGenerationOutput,
    AdkContentGenerationRequest,
)
from google.genai import types

CONTENT_GENERATOR_MODEL = (
    os.getenv("CONTENT_GENERATOR_MODEL") or "gemini-3.1-flash-lite-preview"
)
APP_NAME = "anti_pilot_content_generator"
USER_ID = "content-generator"


def _supports_adk_output_schema_with_tools(model: str) -> bool:
    try:
        from google.adk.utils.output_schema_utils import (
            can_use_output_schema_with_tools,
        )
    except ImportError:
        return False
    return can_use_output_schema_with_tools(model)


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("ADK content generator did not return a JSON object.")
    return stripped[start : end + 1]


def _coerce_content_generation_output(value) -> AdkContentGenerationOutput:
    if isinstance(value, AdkContentGenerationOutput):
        return value
    if isinstance(value, dict):
        return AdkContentGenerationOutput.model_validate(value)
    if isinstance(value, str):
        return AdkContentGenerationOutput.model_validate_json(
            _extract_json_payload(value)
        )
    raise TypeError(f"Unsupported content generation output type: {type(value)!r}")


def _build_agent():
    try:
        try:
            from google.adk.agents import Agent
        except ImportError:  # pragma: no cover - compatibility with older ADK layouts
            from google.adk.agents.llm_agent import Agent

        from google.adk.tools import google_search
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "google-adk is required for grounded content generation. Install the project's updated requirements before running the content-generation graph."
        ) from exc

    agent_kwargs = {
        "name": "content_generator",
        "model": CONTENT_GENERATOR_MODEL,
        "instruction": CONTENT_GENERATOR_INSTRUCTION,
        "tools": [google_search],
    }
    if _supports_adk_output_schema_with_tools(CONTENT_GENERATOR_MODEL):
        agent_kwargs["output_schema"] = AdkContentGenerationOutput
    # For non-Gemini-3 models, ADK output_schema with tools routes through a
    # set_model_response workaround that cannot reliably parse this nested
    # schema. Keep Search available and validate final JSON text with Pydantic.
    return Agent(**agent_kwargs)


async def agenerate_skillpath_content(
    request: AdkContentGenerationRequest,
) -> AdkContentGenerationOutput:
    try:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "google-adk is required for grounded content generation. Install the project's updated requirements before running the content-generation graph."
        ) from exc

    session_service = InMemorySessionService()
    session_id = str(uuid4())
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )
    runner = Runner(
        agent=_build_agent(),
        app_name=APP_NAME,
        session_service=session_service,
    )

    prompt = build_content_generation_prompt(request)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    final_response_text = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response_text = "".join(
                part.text or "" for part in event.content.parts
            )
            break

    if not final_response_text:
        raise ValueError("ADK content generator returned no final response text.")

    return _coerce_content_generation_output(final_response_text)


def generate_skillpath_content(
    request: AdkContentGenerationRequest,
) -> AdkContentGenerationOutput:
    return asyncio.run(agenerate_skillpath_content(request))
