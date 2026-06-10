from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from app.schema.entities import (
    AddMemoryNoteInput,
    CodingProblemAttempt,
    HintRequest,
    HintResponse,
    LearnerMemoryNote,
    LearningMemoryContext,
    MemoryIntegrityAdvisorRecommendation,
    MemoryIntegrityEvidence,
    MemoryRerankRequest,
    MemoryRerankResult,
    SkillMasteryState,
    SkillpathCompletionAdvisorOutput,
    SkillPathItem,
)
from app.schema.enums import MemoryIntegrityAction
from deepagents import create_deep_agent
from pydantic import BaseModel, TypeAdapter

MEMORY_ADVISOR_MODEL = os.getenv(
    "MEMORY_ADVISOR_MODEL", "google_genai:gemini-3.1-flash-lite-preview"
)

_MEMORY_ADVISOR_SYSTEM_PROMPT = """You are a memory advisor for an agentic learning backend.

You make bounded recommendations from the candidate data supplied by the service.
You do not search memory yourself, do not call tools, and do not write to the database.
Return only structured output matching the requested schema.
"""


def _memory_note_payload(note: LearnerMemoryNote) -> dict[str, Any]:
    return {
        "memory_id": note.memory_id,
        "memory_type": note.memory_type.value,
        "title": note.title,
        "summary": note.summary,
        "tags": note.tags,
        "linked_concepts": note.linked_concepts,
        "linked_skillpath_ids": note.linked_skillpath_ids,
        "linked_content_ids": note.linked_content_ids,
        "salience_score": note.salience_score,
        "status": note.status.value,
    }


def _json_payload(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2)
    return json.dumps(value, indent=2, default=str)


def build_hint_advisor_prompt(
    request: HintRequest,
    memory_context: LearningMemoryContext,
    rerank_result: MemoryRerankResult,
) -> str:
    selected_ids = rerank_result.selected_memory_ids
    return (
        "Generate a learner-facing memory-aware hint.\n\n"
        "Rules:\n"
        "- Return a HintResponse.\n"
        "- selected memory IDs must come from the selected rerank memories only.\n"
        "- Do not reveal complete corrected code for nudge or conceptual hints.\n"
        "- Use quick recap or contrast-example metadata when the memory supports it.\n"
        "- Keep the hint concise and focused on the learner's next thinking step.\n\n"
        f"Allowed selected memory IDs: {selected_ids}\n\n"
        f"Hint request:\n{request.model_dump_json(indent=2)}\n\n"
        f"Retrieved memory context:\n{memory_context.model_dump_json(indent=2)}\n\n"
        f"Rerank result:\n{rerank_result.model_dump_json(indent=2)}"
    )


def build_rerank_advisor_prompt(request: MemoryRerankRequest) -> str:
    candidate_ids = [note.memory_id for note in request.candidate_memories]
    return (
        "Rerank learner memories for the requested teaching purpose.\n\n"
        "Rules:\n"
        "- Return a MemoryRerankResult.\n"
        "- selected memory IDs must come from the candidates.\n"
        "- Choose only memories that improve the requested purpose.\n"
        "- Provide guidance suitable for the purpose: hint generation, code correction, content generation, or roadmap planning.\n"
        "- For roadmap_planning: select notes that should shape which skillpaths to include "
        "and how to scope this milestone (e.g. error patterns to remediate, mastery signals to skip/compress, "
        "background or preferences that adjust depth and pacing).\n"
        "- Do not persist or mutate memory.\n\n"
        f"Purpose: {request.purpose.value}\n"
        f"Candidate memory IDs: {candidate_ids}\n\n"
        f"Request:\n{request.model_dump_json(indent=2)}"
    )


def build_integrity_advisor_prompt(
    payload: AddMemoryNoteInput,
    *,
    candidates: list[LearnerMemoryNote],
    evidence: list[MemoryIntegrityEvidence],
    allowed_actions: list[MemoryIntegrityAction],
) -> str:
    return (
        "Recommend a memory integrity action for an incoming learner memory note.\n\n"
        "Rules:\n"
        "- Return a MemoryIntegrityAdvisorRecommendation.\n"
        "- Use only the bounded candidate memories and deterministic evidence below.\n"
        "- Target memory IDs must come from the candidate set.\n"
        "- Do not write to the database. The memory service owns all persistence.\n"
        "- Prefer preventing duplicates and conflicts before creating new memory.\n\n"
        f"Allowed actions: {[action.value for action in allowed_actions]}\n"
        f"Incoming memory:\n{payload.model_dump_json(indent=2)}\n\n"
        f"Candidates:\n{_json_payload([_memory_note_payload(note) for note in candidates])}\n\n"
        f"Evidence:\n{_json_payload([item.model_dump(mode='json') for item in evidence])}"
    )


def build_skillpath_completion_prompt(
    skillpath: SkillPathItem,
    mastery_state: SkillMasteryState | None,
    recent_attempts: list[CodingProblemAttempt],
) -> str:
    attempt_summary = [
        {
            "attempt_id": attempt.attempt_id,
            "correctness": attempt.correctness.value,
            "detected_concepts": attempt.detected_concepts,
            "detected_mistakes": attempt.detected_mistakes,
            "score": attempt.score,
        }
        for attempt in recent_attempts
    ]
    correct_count = sum(
        1 for attempt in recent_attempts if attempt.correctness.value == "correct"
    )
    mastery_payload = (
        mastery_state.model_dump(mode="json") if mastery_state is not None else None
    )
    return (
        "Judge how strong a skillpath completion signal is.\n\n"
        "Rules:\n"
        "- Return a SkillpathCompletionAdvisorOutput.\n"
        "- suggested_mastery_status must be a valid MasteryStatus value.\n"
        "- mastery_signal_salience must be between 0.0 and 1.0.\n"
        "- 'mastered' is ONLY appropriate when the learner has at least one correct\n"
        "  attempt. With no correct attempts, never suggest 'mastered'.\n"
        "- Reading or finishing an activity with no correct coding attempt is a weak\n"
        "  signal: prefer 'practicing' or 'in_progress' with low salience.\n"
        "- Do not write to the database.\n\n"
        f"Correct attempt count: {correct_count}\n"
        f"Skillpath:\n{skillpath.model_dump_json(indent=2)}\n\n"
        f"Current mastery state:\n{_json_payload(mastery_payload)}\n\n"
        f"Recent attempts:\n{_json_payload(attempt_summary)}"
    )


def create_memory_advisor_agent(
    response_format: type[BaseModel],
    *,
    backend: Any | None = None,
    model: str | None = None,
):
    kwargs: dict[str, Any] = {
        "model": model or MEMORY_ADVISOR_MODEL,
        "system_prompt": _MEMORY_ADVISOR_SYSTEM_PROMPT,
        "response_format": response_format,
    }
    if backend is not None:
        kwargs["backend"] = backend
    return create_deep_agent(**kwargs)


def create_hint_advisor_agent(*, backend: Any | None = None, model: str | None = None):
    return create_memory_advisor_agent(HintResponse, backend=backend, model=model)


def create_rerank_advisor_agent(
    *, backend: Any | None = None, model: str | None = None
):
    return create_memory_advisor_agent(MemoryRerankResult, backend=backend, model=model)


def create_integrity_advisor_agent(
    *, backend: Any | None = None, model: str | None = None
):
    return create_memory_advisor_agent(
        MemoryIntegrityAdvisorRecommendation, backend=backend, model=model
    )


def create_skillpath_completion_advisor_agent(
    *, backend: Any | None = None, model: str | None = None
):
    return create_memory_advisor_agent(
        SkillpathCompletionAdvisorOutput, backend=backend, model=model
    )


def _coerce_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
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
    raise ValueError("Memory advisor did not return a JSON object.")


async def _invoke_structured_agent(
    prompt: str,
    response_format: type[BaseModel],
    *,
    agent_factory: Callable[..., Any],
    backend: Any | None = None,
    model: str | None = None,
):
    agent = agent_factory(backend=backend, model=model)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    structured_response = result.get("structured_response")
    if structured_response is not None:
        return response_format.model_validate(structured_response)
    messages = result.get("messages", [])
    if not messages:
        raise ValueError("Memory advisor returned no messages.")
    last_message = messages[-1]
    raw_content = (
        last_message.get("content")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", "")
    )
    raw_text = _coerce_message_text(raw_content)
    return TypeAdapter(response_format).validate_json(_extract_json_payload(raw_text))


async def generate_hint_advice(
    request: HintRequest,
    memory_context: LearningMemoryContext,
    rerank_result: MemoryRerankResult,
    *,
    backend: Any | None = None,
    model: str | None = None,
    agent_factory: Callable[..., Any] = create_hint_advisor_agent,
) -> HintResponse:
    return await _invoke_structured_agent(
        build_hint_advisor_prompt(request, memory_context, rerank_result),
        HintResponse,
        agent_factory=agent_factory,
        backend=backend,
        model=model,
    )


async def rerank_memory_advice(
    request: MemoryRerankRequest,
    *,
    backend: Any | None = None,
    model: str | None = None,
    agent_factory: Callable[..., Any] = create_rerank_advisor_agent,
) -> MemoryRerankResult:
    return await _invoke_structured_agent(
        build_rerank_advisor_prompt(request),
        MemoryRerankResult,
        agent_factory=agent_factory,
        backend=backend,
        model=model,
    )


async def advise_memory_integrity(
    payload: AddMemoryNoteInput,
    candidates: list[LearnerMemoryNote],
    evidence: list[MemoryIntegrityEvidence],
    allowed_actions: list[MemoryIntegrityAction],
    *,
    backend: Any | None = None,
    model: str | None = None,
    agent_factory: Callable[..., Any] = create_integrity_advisor_agent,
) -> MemoryIntegrityAdvisorRecommendation:
    return await _invoke_structured_agent(
        build_integrity_advisor_prompt(
            payload,
            candidates=candidates,
            evidence=evidence,
            allowed_actions=allowed_actions,
        ),
        MemoryIntegrityAdvisorRecommendation,
        agent_factory=agent_factory,
        backend=backend,
        model=model,
    )


async def advise_skillpath_completion(
    skillpath: SkillPathItem,
    mastery_state: SkillMasteryState | None,
    recent_attempts: list[CodingProblemAttempt],
    *,
    backend: Any | None = None,
    model: str | None = None,
    agent_factory: Callable[..., Any] = create_skillpath_completion_advisor_agent,
) -> SkillpathCompletionAdvisorOutput:
    return await _invoke_structured_agent(
        build_skillpath_completion_prompt(skillpath, mastery_state, recent_attempts),
        SkillpathCompletionAdvisorOutput,
        agent_factory=agent_factory,
        backend=backend,
        model=model,
    )
