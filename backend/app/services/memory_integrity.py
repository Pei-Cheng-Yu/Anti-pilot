from __future__ import annotations

import inspect
import math
import os
from collections.abc import Callable
from typing import Any

from app.advisors.memory_advisors import advise_memory_integrity
from app.db.model import LearnerMemoryNoteModel
from app.schema.entities import (
    AddMemoryNoteInput,
    LearnerMemoryNote,
    MemoryIntegrityAdvisorRecommendation,
    MemoryIntegrityDecision,
    MemoryIntegrityEvidence,
)
from app.schema.enums import MemoryIntegrityAction, MemoryStatus, MemoryType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MemoryIntegrityAdvisor = Callable[
    [
        AddMemoryNoteInput,
        list[LearnerMemoryNoteModel],
        list[MemoryIntegrityEvidence],
        list[MemoryIntegrityAction],
    ],
    Any,
]

ALLOWED_MEMORY_INTEGRITY_ACTIONS = [
    MemoryIntegrityAction.CREATE_NEW,
    MemoryIntegrityAction.UPDATE_EXISTING,
    MemoryIntegrityAction.MERGE,
    MemoryIntegrityAction.SKIP_DUPLICATE,
    MemoryIntegrityAction.KEEP_BOTH_SCOPED,
    MemoryIntegrityAction.FLAG_CONFLICT,
]


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


def _row_to_memory_note(row: LearnerMemoryNoteModel) -> LearnerMemoryNote:
    return LearnerMemoryNote(
        memory_id=row.memory_id,
        user_id=row.user_id,
        memory_type=MemoryType(row.memory_type),
        title=row.title,
        summary=row.summary,
        tags=row.tags or [],
        linked_concepts=row.linked_concepts or [],
        linked_skillpath_ids=row.linked_skillpath_ids or [],
        linked_content_ids=row.linked_content_ids or [],
        evidence_attempt_ids=row.evidence_attempt_ids or [],
        salience_score=float(row.salience_score or 0.0),
        status=MemoryStatus(row.status),
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        last_used_at=row.last_used_at,
    )


def _default_integrity_advisor() -> MemoryIntegrityAdvisor | None:
    if not _env_flag("ENABLE_MEMORY_INTEGRITY_ADVISOR", False):
        return None
    if not _has_llm_credentials():
        return None

    async def _advisor(
        payload: AddMemoryNoteInput,
        candidates: list[LearnerMemoryNoteModel],
        evidence: list[MemoryIntegrityEvidence],
        allowed_actions: list[MemoryIntegrityAction],
    ) -> MemoryIntegrityAdvisorRecommendation:
        return await advise_memory_integrity(
            payload,
            [_row_to_memory_note(row) for row in candidates],
            evidence,
            allowed_actions,
        )

    return _advisor


def _normalize_terms(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        candidate = value.strip().lower()
        if candidate:
            normalized.add(candidate)
    return normalized


def _cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if a is None or b is None or len(a) == 0 or len(b) == 0 or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    cosine = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def _memory_type_from_row(row: LearnerMemoryNoteModel) -> MemoryType:
    return MemoryType(row.memory_type)


def _memory_status_from_row(row: LearnerMemoryNoteModel) -> MemoryStatus:
    return MemoryStatus(row.status)


def _is_type_compatible(incoming_type: MemoryType, candidate_type: MemoryType) -> bool:
    if incoming_type == candidate_type:
        return True
    conflict_pair = {MemoryType.ERROR_PATTERN, MemoryType.MASTERY_SIGNAL}
    return {incoming_type, candidate_type} == conflict_pair


def build_integrity_evidence(
    payload: AddMemoryNoteInput,
    candidate: LearnerMemoryNoteModel,
    *,
    incoming_embedding: list[float] | None = None,
) -> MemoryIntegrityEvidence:
    candidate_type = _memory_type_from_row(candidate)
    candidate_status = _memory_status_from_row(candidate)
    incoming_concepts = _normalize_terms(payload.linked_concepts)
    candidate_concepts = _normalize_terms(candidate.linked_concepts or [])
    incoming_tags = _normalize_terms(payload.tags)
    candidate_tags = _normalize_terms(candidate.tags or [])
    incoming_scope = set(payload.linked_skillpath_ids + payload.linked_content_ids)
    candidate_scope = set(
        (candidate.linked_skillpath_ids or []) + (candidate.linked_content_ids or [])
    )

    concept_overlap = len(incoming_concepts & candidate_concepts)
    tag_overlap = len(incoming_tags & candidate_tags)
    scope_overlap = len(incoming_scope & candidate_scope)
    semantic_similarity = _cosine_similarity(incoming_embedding, candidate.embedding)
    type_compatible = _is_type_compatible(payload.memory_type, candidate_type)
    reasons: list[str] = []
    if type_compatible:
        reasons.append("type compatible")
    if concept_overlap:
        reasons.append(f"{concept_overlap} concept overlap")
    if tag_overlap:
        reasons.append(f"{tag_overlap} tag overlap")
    if scope_overlap:
        reasons.append(f"{scope_overlap} scope overlap")
    if semantic_similarity >= 0.85:
        reasons.append("high semantic similarity")

    return MemoryIntegrityEvidence(
        candidate_memory_id=candidate.memory_id,
        candidate_memory_type=candidate_type,
        type_compatible=type_compatible,
        concept_overlap=concept_overlap,
        tag_overlap=tag_overlap,
        scope_overlap=scope_overlap,
        semantic_similarity=semantic_similarity,
        salience_score=float(candidate.salience_score or 0.0),
        status=candidate_status,
        reasons=reasons,
    )


async def find_memory_integrity_candidates(
    payload: AddMemoryNoteInput,
    session: AsyncSession,
    *,
    incoming_embedding: list[float] | None = None,
    include_resolved: bool = False,
    candidate_limit: int = 25,
) -> tuple[list[LearnerMemoryNoteModel], list[MemoryIntegrityEvidence]]:
    query = select(LearnerMemoryNoteModel).where(
        LearnerMemoryNoteModel.user_id == payload.user_id
    )
    if not include_resolved:
        query = query.where(
            LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value
        )
    result = await session.execute(query)
    rows = list(result.scalars())
    evidence_by_id = {
        row.memory_id: build_integrity_evidence(
            payload,
            row,
            incoming_embedding=incoming_embedding,
        )
        for row in rows
    }
    candidates = [
        row
        for row in rows
        if evidence_by_id[row.memory_id].type_compatible
        and (
            evidence_by_id[row.memory_id].concept_overlap > 0
            or evidence_by_id[row.memory_id].tag_overlap > 0
            or evidence_by_id[row.memory_id].scope_overlap > 0
            or evidence_by_id[row.memory_id].semantic_similarity >= 0.8
        )
    ]
    candidates.sort(
        key=lambda row: (
            evidence_by_id[row.memory_id].scope_overlap,
            evidence_by_id[row.memory_id].concept_overlap,
            evidence_by_id[row.memory_id].tag_overlap,
            evidence_by_id[row.memory_id].semantic_similarity,
            evidence_by_id[row.memory_id].salience_score,
        ),
        reverse=True,
    )
    candidates = candidates[:candidate_limit]
    return candidates, [evidence_by_id[row.memory_id] for row in candidates]


def deterministic_integrity_decision(
    payload: AddMemoryNoteInput,
    candidates: list[LearnerMemoryNoteModel],
    evidence: list[MemoryIntegrityEvidence],
) -> MemoryIntegrityDecision:
    has_incoming_evidence = bool(payload.evidence_attempt_ids)
    for item in evidence:
        if item.candidate_memory_type != payload.memory_type:
            continue
        if has_incoming_evidence and (
            item.scope_overlap > 0
            or item.concept_overlap >= 2
            or item.tag_overlap >= 2
            or item.semantic_similarity >= 0.92
        ):
            return MemoryIntegrityDecision(
                action=MemoryIntegrityAction.UPDATE_EXISTING,
                target_memory_ids=[item.candidate_memory_id],
                confidence=0.8,
                rationale="Existing memory matches by scope, concepts, tags, or semantics.",
                evidence=evidence,
            )

    for item in evidence:
        if (
            not item.type_compatible
            or item.candidate_memory_type == payload.memory_type
        ):
            continue
        if item.concept_overlap >= 1 or item.scope_overlap > 0:
            return MemoryIntegrityDecision(
                action=MemoryIntegrityAction.FLAG_CONFLICT,
                target_memory_ids=[item.candidate_memory_id],
                confidence=0.65,
                rationale="Incoming memory may conflict with an existing related note.",
                evidence=evidence,
            )

    return MemoryIntegrityDecision(
        action=MemoryIntegrityAction.CREATE_NEW,
        confidence=0.5,
        rationale="No sufficiently similar active memory was found.",
        evidence=evidence,
    )


def validate_advisor_recommendation(
    recommendation: MemoryIntegrityAdvisorRecommendation | dict[str, Any] | None,
    *,
    candidate_memory_ids: set[str],
    allowed_actions: list[MemoryIntegrityAction] | None = None,
    min_confidence: float = 0.6,
    fallback: MemoryIntegrityDecision | None = None,
) -> MemoryIntegrityDecision:
    fallback_decision = fallback or MemoryIntegrityDecision(
        action=MemoryIntegrityAction.CREATE_NEW,
        confidence=0.0,
        rationale="Falling back to deterministic memory integrity behavior.",
    )
    allowed = set(allowed_actions or ALLOWED_MEMORY_INTEGRITY_ACTIONS)
    try:
        parsed = MemoryIntegrityAdvisorRecommendation.model_validate(recommendation)
    except Exception:
        fallback_decision.rationale = "Advisor returned invalid schema."
        fallback_decision.advisor_used = False
        return fallback_decision

    if parsed.action not in allowed:
        fallback_decision.rationale = "Advisor returned unsupported action."
        fallback_decision.advisor_used = False
        return fallback_decision
    unknown_ids = set(parsed.target_memory_ids) - candidate_memory_ids
    if unknown_ids:
        fallback_decision.rationale = (
            "Advisor referenced unknown target memory IDs: "
            + ", ".join(sorted(unknown_ids))
        )
        fallback_decision.advisor_used = False
        return fallback_decision
    if parsed.confidence < min_confidence:
        fallback_decision.rationale = "Advisor confidence was below threshold."
        fallback_decision.advisor_used = False
        return fallback_decision

    return MemoryIntegrityDecision(
        action=parsed.action,
        target_memory_ids=parsed.target_memory_ids,
        confidence=parsed.confidence,
        rationale=parsed.rationale,
        advisor_used=True,
        field_updates=parsed.field_updates,
    )


async def check_memory_write_integrity(
    payload: AddMemoryNoteInput,
    session: AsyncSession,
    *,
    incoming_embedding: list[float] | None = None,
    advisor: MemoryIntegrityAdvisor | None = None,
    min_advisor_confidence: float = 0.6,
) -> MemoryIntegrityDecision:
    candidates, evidence = await find_memory_integrity_candidates(
        payload,
        session,
        incoming_embedding=incoming_embedding,
    )
    deterministic = deterministic_integrity_decision(payload, candidates, evidence)
    advisor = advisor or _default_integrity_advisor()
    if advisor is None or not candidates:
        return deterministic

    maybe_recommendation = advisor(
        payload,
        candidates,
        evidence,
        ALLOWED_MEMORY_INTEGRITY_ACTIONS,
    )
    if inspect.isawaitable(maybe_recommendation):
        maybe_recommendation = await maybe_recommendation
    advisor_decision = validate_advisor_recommendation(
        maybe_recommendation,
        candidate_memory_ids={row.memory_id for row in candidates},
        min_confidence=min_advisor_confidence,
        fallback=deterministic,
    )
    advisor_decision.evidence = evidence
    return advisor_decision
