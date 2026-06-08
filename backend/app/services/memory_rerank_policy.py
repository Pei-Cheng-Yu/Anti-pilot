from __future__ import annotations

import inspect
import os
from collections.abc import Callable
from typing import Any

from app.advisors.memory_advisors import rerank_memory_advice
from app.schema.entities import (
    LearnerMemoryNote,
    MemoryRerankRequest,
    MemoryRerankResult,
    SelectedMemoryMetadata,
)
from app.schema.enums import MemoryRerankPurpose, MemoryType, TeachingAction

MemoryRerankAdvisor = Callable[[MemoryRerankRequest], Any]


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _has_llm_credentials() -> bool:
    return any(
        os.getenv(name)
        for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
    )


def _default_rerank_advisor() -> MemoryRerankAdvisor | None:
    if not _env_flag("ENABLE_MEMORY_RERANK_ADVISOR", False):
        return None
    if not _has_llm_credentials():
        return None
    return rerank_memory_advice


def _selected_metadata(note: LearnerMemoryNote, reason: str) -> SelectedMemoryMetadata:
    return SelectedMemoryMetadata(
        memory_id=note.memory_id,
        memory_type=note.memory_type,
        title=note.title,
        reason=reason,
    )


def _fallback_action(selected: list[LearnerMemoryNote]) -> TeachingAction:
    if any(note.memory_type == MemoryType.HEURISTIC for note in selected):
        return TeachingAction.CONTRAST_EXAMPLE
    if any(note.memory_type == MemoryType.ERROR_PATTERN for note in selected):
        return TeachingAction.QUICK_RECAP_THEN_HINT
    return TeachingAction.NORMAL_HINT


def _focused_concepts(selected: list[LearnerMemoryNote]) -> list[str]:
    concepts: set[str] = set()
    for note in selected:
        concepts.update(note.linked_concepts or [])
    return sorted(concepts)


def _fallback_result(request: MemoryRerankRequest) -> MemoryRerankResult:
    selected = request.candidate_memories[: request.max_selected]
    purpose = request.purpose.value.replace("_", " ")
    return MemoryRerankResult(
        purpose=request.purpose,
        selected_memories=[
            _selected_metadata(note, f"Selected by deterministic {purpose} order.")
            for note in selected
        ],
        teaching_action=_fallback_action(selected),
        focused_concepts=_focused_concepts(selected),
        guidance=f"Use the selected learner memories for {purpose}.",
    )


def _validate_result(
    result: MemoryRerankResult | dict[str, Any] | None,
    request: MemoryRerankRequest,
) -> MemoryRerankResult | None:
    try:
        parsed = MemoryRerankResult.model_validate(result)
    except Exception:
        return None
    candidate_ids = {note.memory_id for note in request.candidate_memories}
    selected_ids = {note.memory_id for note in parsed.selected_memories}
    if not selected_ids <= candidate_ids:
        return None
    if parsed.purpose != request.purpose:
        return None
    return parsed


def rerank_memories(
    request: MemoryRerankRequest,
    *,
    advisor: MemoryRerankAdvisor | None = None,
) -> MemoryRerankResult:
    fallback = _fallback_result(request)
    if advisor is None or not request.candidate_memories:
        return fallback
    try:
        maybe_result = advisor(request)
        if inspect.isawaitable(maybe_result):
            return fallback
    except Exception:
        return fallback
    return _validate_result(maybe_result, request) or fallback


async def arerank_memories(
    request: MemoryRerankRequest,
    *,
    advisor: MemoryRerankAdvisor | None = None,
) -> MemoryRerankResult:
    fallback = _fallback_result(request)
    advisor = advisor or _default_rerank_advisor()
    if advisor is None or not request.candidate_memories:
        return fallback
    try:
        maybe_result = advisor(request)
        if inspect.isawaitable(maybe_result):
            maybe_result = await maybe_result
    except Exception:
        return fallback
    return _validate_result(maybe_result, request) or fallback


def build_content_generation_memory_guidance(
    candidate_memories: list[LearnerMemoryNote],
    *,
    task_context: str = "",
    advisor: MemoryRerankAdvisor | None = None,
) -> MemoryRerankResult:
    return rerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.CONTENT_GENERATION,
            task_context=task_context,
            candidate_memories=candidate_memories,
        ),
        advisor=advisor,
    )
