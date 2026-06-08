from __future__ import annotations

import inspect
import os
from collections.abc import Callable
from typing import Any

from app.advisors.memory_advisors import generate_hint_advice
from app.schema.entities import (
    HintRequest,
    HintResponse,
    MemoryRerankRequest,
    RetrieveLearningMemoryInput,
)
from app.schema.enums import HintLevel, MemoryRerankPurpose, TeachingAction
from app.services import learning_memory
from app.services.memory_rerank_policy import MemoryRerankAdvisor, arerank_memories
from sqlalchemy.ext.asyncio import AsyncSession

MemoryHintAdvisor = Callable[[HintRequest, Any, Any], Any]


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


def _default_hint_advisor() -> MemoryHintAdvisor | None:
    if not _env_flag("ENABLE_MEMORY_HINT_ADVISOR", False):
        return None
    if not _has_llm_credentials():
        return None
    return generate_hint_advice


def _build_query_text(request: HintRequest) -> str:
    parts = [
        request.task_prompt,
        request.submitted_code,
        request.validation_feedback or "",
        " ".join(request.concept_keys),
    ]
    return " ".join(part for part in parts if part)


def _base_hint(request: HintRequest, action: TeachingAction) -> str:
    concept = request.concept_keys[0] if request.concept_keys else "the target concept"
    if request.hint_level == HintLevel.NUDGE:
        if action == TeachingAction.QUICK_RECAP_THEN_HINT:
            return (
                f"Quick recap: before changing the code, identify which call is "
                f"asynchronous and whether {concept} requires `await` at that call."
            )
        return f"Look for the part of your code connected to {concept} before editing."
    if request.hint_level == HintLevel.CONCEPTUAL:
        return (
            f"Think about the rule behind {concept}: the route should return the "
            "actual result of the operation, not a pending operation."
        )
    if request.hint_level == HintLevel.SPECIFIC:
        return (
            "Find the database or helper call in your handler and make sure the "
            "async operation is completed before you return the response."
        )
    return (
        "You are very close: apply the async/await rule at the call site, then "
        "return the resolved value."
    )


def _quick_recap(action: TeachingAction, concepts: list[str]) -> str | None:
    if action not in {TeachingAction.QUICK_RECAP, TeachingAction.QUICK_RECAP_THEN_HINT}:
        return None
    if not concepts:
        return "Recap the prerequisite concept before trying the next edit."
    return "Recap: " + ", ".join(concepts[:3])


def _contrast_example(action: TeachingAction) -> str | None:
    if action != TeachingAction.CONTRAST_EXAMPLE:
        return None
    return "Contrast the version that starts an async operation with the version that waits for its result."


def _filter_hint_candidates(request: HintRequest, memory_context) -> list:
    if not request.concept_keys:
        return memory_context.relevant_notes
    requested = {concept.strip().lower() for concept in request.concept_keys if concept}
    filtered = [
        note
        for note in memory_context.relevant_notes
        if requested & {concept.strip().lower() for concept in note.linked_concepts}
    ]
    return filtered


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().split())


def _low_level_hint_reveals_solution(request: HintRequest, hint: str) -> bool:
    if request.hint_level not in {HintLevel.NUDGE, HintLevel.CONCEPTUAL}:
        return False
    normalized_hint = _normalized_text(hint)
    for line in request.submitted_code.splitlines():
        if "=" not in line:
            continue
        _, rhs = line.split("=", 1)
        call_expression = rhs.strip()
        if not call_expression:
            continue
        if _normalized_text(f"await {call_expression}") in normalized_hint:
            return True
    return False


def _validate_hint_advisor_response(
    response: HintResponse | dict[str, Any] | None,
    *,
    request: HintRequest,
    allowed_memory_ids: set[str],
) -> HintResponse | None:
    try:
        parsed = HintResponse.model_validate(response)
    except Exception:
        return None

    if not set(parsed.selected_memory_ids) <= allowed_memory_ids:
        return None
    selected_metadata_ids = {memory.memory_id for memory in parsed.selected_memories}
    if not selected_metadata_ids <= allowed_memory_ids:
        return None
    if _low_level_hint_reveals_solution(request, parsed.hint):
        return None
    return parsed


async def generate_memory_aware_hint(
    request: HintRequest,
    session: AsyncSession,
    *,
    rerank_advisor: MemoryRerankAdvisor | None = None,
    hint_advisor: MemoryHintAdvisor | None = None,
) -> HintResponse:
    memory_context = await learning_memory.retrieve_learning_memory(
        RetrieveLearningMemoryInput(
            user_id=request.user_id,
            query_text=_build_query_text(request),
            skillpath_id=request.skillpath_id,
            content_id=request.content_id,
            concept_keys=request.concept_keys,
            top_k_notes=5,
        ),
        session,
    )
    rerank_result = await arerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.HINT_GENERATION,
            task_context=request.task_prompt,
            learner_context=request.validation_feedback or "",
            recent_attempts=memory_context.recent_attempts,
            candidate_memories=_filter_hint_candidates(request, memory_context),
            max_selected=3,
        ),
        advisor=rerank_advisor,
    )
    hint_advisor = hint_advisor or _default_hint_advisor()
    if hint_advisor is not None:
        try:
            maybe_hint = hint_advisor(request, memory_context, rerank_result)
            if inspect.isawaitable(maybe_hint):
                maybe_hint = await maybe_hint
        except Exception:
            maybe_hint = None
        advisor_hint = _validate_hint_advisor_response(
            maybe_hint,
            request=request,
            allowed_memory_ids=set(rerank_result.selected_memory_ids),
        )
        if advisor_hint is not None:
            return advisor_hint

    hint = _base_hint(request, rerank_result.teaching_action)
    return HintResponse(
        hint=hint,
        hint_level=request.hint_level,
        teaching_action=rerank_result.teaching_action,
        selected_memory_ids=rerank_result.selected_memory_ids,
        selected_memories=rerank_result.selected_memories,
        focused_concepts=rerank_result.focused_concepts,
        quick_recap=_quick_recap(
            rerank_result.teaching_action, rerank_result.focused_concepts
        ),
        contrast_example=_contrast_example(rerank_result.teaching_action),
        used_memory=bool(rerank_result.selected_memory_ids),
    )
