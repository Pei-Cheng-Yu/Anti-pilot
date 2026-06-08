from __future__ import annotations

import json
import os
import re
from typing import Any

from app.validators.schemas import CodeValidationRequest, CodeValidationResult
from deepagents import create_deep_agent
from pydantic import TypeAdapter

CODE_VALIDATOR_MODEL = os.getenv(
    "CODE_VALIDATOR_MODEL", "google_genai:gemini-3.1-flash-lite-preview"
)

_VALIDATOR_SYSTEM_PROMPT = """You are a code validation agent.

Your job is to validate learner-submitted code for one coding problem.

For this version, do not assume sandbox execution is available. Use the submitted code, coding problem prompt, and any external compile/runtime/test evidence supplied by the caller.

Validation process:
1. Read the coding problem carefully.
2. Inspect the submitted code for obvious blockers:
   - syntax errors
   - missing required function or structure
   - code that clearly cannot run
3. Use provided compile_error, runtime_error, stdout, stderr, and test_results as execution evidence when present.
4. If execution evidence is missing, reason from the code and lower confidence_score.
5. Return a structured CodeValidationResult.

Important rules:
- Prefer provided execution evidence over pure reasoning.
- Do not invent tests that were not provided or run.
- If validation is uncertain, say so in confidence_score.
- feedback_summary should stay concise and learner-facing.
- detected_mistakes should be compact reusable labels like missing_await or wrong_return_shape.
- validation_strategy should be one short label such as external_execution_evidence, reason_only_blocker, or reasoned_static_review.
"""

_RESULT_ADAPTER = TypeAdapter(CodeValidationResult)


def create_code_validator_agent(
    *, backend: Any | None = None, model: str | None = None
):
    """Create a Deep Agent configured to validate learner code."""
    kwargs: dict[str, Any] = {
        "model": model or CODE_VALIDATOR_MODEL,
        "system_prompt": _VALIDATOR_SYSTEM_PROMPT,
        "response_format": CodeValidationResult,
    }
    if backend is not None:
        kwargs["backend"] = backend
    return create_deep_agent(
        **kwargs,
    )


def _build_validation_prompt(request: CodeValidationRequest) -> str:
    return (
        "Validate this learner submission using the submitted code and any external compile/runtime/test evidence supplied below.\n\n"
        f"{request.model_dump_json(indent=2)}\n\n"
        "Return a CodeValidationResult. If structured output is unavailable, return a single JSON object matching that schema."
    )


def _coerce_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        return "\n".join(part for part in text_parts if part)
    return str(content)


def _extract_json_payload(raw_text: str) -> str:
    stripped = raw_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_text, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1)

    first = raw_text.find("{")
    last = raw_text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = raw_text[first : last + 1]
        json.loads(candidate)
        return candidate

    raise ValueError("Validator agent did not return a JSON object.")


async def validate_code_submission(
    request: CodeValidationRequest,
    *,
    backend: Any,
    model: str | None = None,
) -> CodeValidationResult:
    """Run the validator Deep Agent and parse its structured result."""
    agent = create_code_validator_agent(backend=backend, model=model)
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": _build_validation_prompt(request),
                }
            ]
        }
    )

    structured_response = result.get("structured_response")
    if structured_response is not None:
        return CodeValidationResult.model_validate(structured_response)

    messages = result.get("messages", [])
    if not messages:
        raise ValueError("Validator agent returned no messages.")

    last_message = messages[-1]
    raw_content = (
        last_message.get("content")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", "")
    )
    raw_text = _coerce_message_text(raw_content)
    payload = _extract_json_payload(raw_text)
    return _RESULT_ADAPTER.validate_json(payload)
