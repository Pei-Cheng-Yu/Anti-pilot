from __future__ import annotations

import asyncio
import inspect
import math
import os
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from app.advisors.memory_advisors import advise_skillpath_completion
from app.db.model import (
    CodingProblemAttemptModel,
    LearnerMemoryNoteModel,
    SkillMasteryStateModel,
    UserModel,
)
from app.schema.entities import (
    AddMemoryNoteInput,
    CodingProblemAttempt,
    LearnerMemoryNote,
    LearningMemoryContext,
    MarkSkillpathCompletedResult,
    MemoryConsolidationJudgment,
    MergeMemoryNotesInput,
    MergeMemoryNotesResult,
    RecordCodingProblemAttemptInput,
    ResolveMemoryConflictInput,
    ResolveMemoryConflictResult,
    RetrieveLearningMemoryInput,
    SkillMasteryState,
    SkillpathCompletionAdvisorOutput,
    SkillPathItem,
    TestCaseResult,
    UpdateMemoryNoteInput,
)
from app.schema.enums import (
    AttemptCorrectness,
    MasteryStatus,
    MemoryIntegrityAction,
    MemoryStatus,
    MemoryType,
)
from app.services.learning_memory_retriever import get_memory_note_candidates
from app.services.memory_integrity import check_memory_write_integrity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MEMORY_EMBEDDING_MODEL = os.getenv("MEMORY_EMBEDDING_MODEL") or "gemini-embedding-2"
MemoryConsolidationJudgmentProvider = Callable[
    [
        CodingProblemAttempt,
        SkillMasteryState | None,
        list[LearnerMemoryNote],
        list[CodingProblemAttempt],
    ],
    Any,
]


def _utcnow() -> datetime:
    # DB timestamp columns are currently timezone-naive, so keep service-side
    # timestamps naive as well to avoid asyncpg offset-aware/naive mismatches.
    return datetime.now(UTC).replace(tzinfo=None)


def _to_attempt(row: CodingProblemAttemptModel) -> CodingProblemAttempt:
    return CodingProblemAttempt(
        attempt_id=row.attempt_id,
        user_id=row.user_id,
        skillpath_id=row.skillpath_id,
        content_id=row.content_id,
        submitted_code=row.submitted_code,
        language=row.language,
        correctness=AttemptCorrectness(row.correctness),
        feedback_summary=row.feedback_summary,
        detected_concepts=row.detected_concepts or [],
        detected_mistakes=row.detected_mistakes or [],
        compile_error=row.compile_error,
        runtime_error=row.runtime_error,
        score=row.score,
        test_results=[
            TestCaseResult.model_validate(item) for item in (row.test_results or [])
        ],
        submitted_at=row.submitted_at,
    )


def _to_memory_note(row: LearnerMemoryNoteModel) -> LearnerMemoryNote:
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
        embedding=row.embedding,
        salience_score=row.salience_score,
        status=MemoryStatus(row.status),
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        last_used_at=row.last_used_at,
    )


def _to_mastery_state(row: SkillMasteryStateModel) -> SkillMasteryState:
    return SkillMasteryState(
        user_id=row.user_id,
        skillpath_id=row.skillpath_id,
        status=MasteryStatus(row.status),
        mastery_score=row.mastery_score,
        successful_attempts=row.successful_attempts,
        failed_attempts=row.failed_attempts,
        strong_concepts=row.strong_concepts or [],
        weak_concepts=row.weak_concepts or [],
        last_attempt_at=row.last_attempt_at,
        last_updated_at=row.last_updated_at,
    )


def _normalize_terms(values: list[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        candidate = value.strip().lower()
        if candidate:
            normalized.add(candidate)
    return normalized


def _tokenize_query(query_text: str) -> set[str]:
    return _normalize_terms(query_text.replace("/", " ").replace("_", " ").split())


def _build_note_embedding_text(
    *,
    title: str,
    summary: str,
    tags: list[str],
    linked_concepts: list[str],
) -> str:
    parts = [title.strip(), summary.strip()]
    if tags:
        parts.append("tags: " + ", ".join(tags))
    if linked_concepts:
        parts.append("concepts: " + ", ".join(linked_concepts))
    return "\n".join(part for part in parts if part)


def _build_memory_note_search_text(
    *,
    title: str,
    summary: str,
    tags: list[str],
    linked_concepts: list[str],
    linked_skillpath_ids: list[str],
    linked_content_ids: list[str],
    evidence_attempt_ids: list[str],
) -> str:
    parts = [
        title,
        summary,
        " ".join(tags),
        " ".join(linked_concepts),
        " ".join(linked_skillpath_ids),
        " ".join(linked_content_ids),
        " ".join(evidence_attempt_ids),
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _get_embedding_model():
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "langchain-google-genai is required for learning-memory vector search."
        ) from exc
    return GoogleGenerativeAIEmbeddings(model=MEMORY_EMBEDDING_MODEL)


def _embed_text(text: str) -> list[float]:
    embedding_model = _get_embedding_model()
    return list(embedding_model.embed_query(text))


async def _async_embed_text(text: str) -> list[float]:
    return await asyncio.to_thread(_embed_text, text)


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


def _memory_note_score(
    row: LearnerMemoryNoteModel,
    *,
    skillpath_id: str | None,
    content_id: str | None,
    concept_keys: list[str],
    query_terms: set[str],
    query_embedding: list[float] | None,
) -> float:
    symbolic_score = float(row.salience_score or 0.0)
    if skillpath_id and skillpath_id in (row.linked_skillpath_ids or []):
        symbolic_score += 2.5
    if content_id and content_id in (row.linked_content_ids or []):
        symbolic_score += 2.0

    linked_concepts = _normalize_terms(row.linked_concepts or [])
    tags = _normalize_terms(row.tags or [])
    concept_terms = _normalize_terms(concept_keys)
    concept_overlap = len(concept_terms & linked_concepts)
    symbolic_score += 0.75 * concept_overlap

    haystack_terms = (
        tags
        | linked_concepts
        | _tokenize_query(row.title)
        | _tokenize_query(row.summary)
    )
    keyword_overlap = len(query_terms & haystack_terms)
    symbolic_score += 0.35 * keyword_overlap

    if row.memory_type == MemoryType.ERROR_PATTERN.value:
        symbolic_score += 0.2
    if row.status == MemoryStatus.WATCH.value:
        symbolic_score -= 0.1

    vector_score = _cosine_similarity(query_embedding, row.embedding)
    keyword_score = min(1.0, keyword_overlap / 4.0)
    concept_boost = min(1.0, concept_overlap / 3.0)
    salience_component = min(1.0, float(row.salience_score or 0.0))
    hybrid_score = (
        0.55 * vector_score
        + 0.25 * keyword_score
        + 0.15 * concept_boost
        + 0.05 * salience_component
    )
    return hybrid_score * 10.0 + symbolic_score


def _partition_notes(
    notes: list[LearnerMemoryNote],
) -> tuple[
    list[LearnerMemoryNote],
    list[LearnerMemoryNote],
    list[LearnerMemoryNote],
    list[LearnerMemoryNote],
]:
    active_error_patterns: list[LearnerMemoryNote] = []
    mastery_signals: list[LearnerMemoryNote] = []
    teaching_heuristics: list[LearnerMemoryNote] = []
    background_notes: list[LearnerMemoryNote] = []
    for note in notes:
        if note.memory_type == MemoryType.ERROR_PATTERN:
            active_error_patterns.append(note)
        elif note.memory_type == MemoryType.MASTERY_SIGNAL:
            mastery_signals.append(note)
        elif note.memory_type == MemoryType.HEURISTIC:
            teaching_heuristics.append(note)
        else:
            background_notes.append(note)
    return active_error_patterns, mastery_signals, teaching_heuristics, background_notes


def _should_match_error_pattern(
    row: LearnerMemoryNoteModel,
    *,
    skillpath_id: str,
    content_id: str,
    linked_term_set: set[str],
) -> bool:
    same_scope = skillpath_id in (row.linked_skillpath_ids or []) or content_id in (
        row.linked_content_ids or []
    )
    concept_overlap = len(linked_term_set & _normalize_terms(row.linked_concepts or []))
    return same_scope or concept_overlap >= 2


def _clamp_salience(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp_delta(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _merge_unique(*values: list[str] | None) -> list[str]:
    merged: set[str] = set()
    for items in values:
        merged.update(_normalize_terms(items or []))
    return sorted(merged)


async def _refresh_memory_note_index(row: LearnerMemoryNoteModel) -> None:
    row.embedding = await _async_embed_text(
        _build_note_embedding_text(
            title=row.title,
            summary=row.summary,
            tags=row.tags or [],
            linked_concepts=row.linked_concepts or [],
        )
    )
    row.search_text = _build_memory_note_search_text(
        title=row.title,
        summary=row.summary,
        tags=row.tags or [],
        linked_concepts=row.linked_concepts or [],
        linked_skillpath_ids=row.linked_skillpath_ids or [],
        linked_content_ids=row.linked_content_ids or [],
        evidence_attempt_ids=row.evidence_attempt_ids or [],
    )


async def _count_success_evidence(
    row: LearnerMemoryNoteModel, session: AsyncSession
) -> int:
    evidence_attempt_ids = row.evidence_attempt_ids or []
    if not evidence_attempt_ids:
        return 0
    result = await session.execute(
        select(CodingProblemAttemptModel).where(
            CodingProblemAttemptModel.attempt_id.in_(evidence_attempt_ids),
            CodingProblemAttemptModel.correctness == AttemptCorrectness.CORRECT.value,
        )
    )
    return len(list(result.scalars()))


async def _get_success_evidence_attempt_ids(
    row: LearnerMemoryNoteModel, session: AsyncSession
) -> list[str]:
    evidence_attempt_ids = row.evidence_attempt_ids or []
    if not evidence_attempt_ids:
        return []
    result = await session.execute(
        select(CodingProblemAttemptModel.attempt_id).where(
            CodingProblemAttemptModel.attempt_id.in_(evidence_attempt_ids),
            CodingProblemAttemptModel.correctness == AttemptCorrectness.CORRECT.value,
        )
    )
    return sorted(set(result.scalars()))


async def _create_memory_note_row(
    payload: AddMemoryNoteInput,
    session: AsyncSession,
    *,
    embedding: list[float] | None = None,
) -> LearnerMemoryNoteModel:
    user = await session.get(UserModel, payload.user_id)
    if not user:
        session.add(UserModel(user_id=payload.user_id))

    if embedding is None:
        embedding = await _async_embed_text(
            _build_note_embedding_text(
                title=payload.title,
                summary=payload.summary,
                tags=payload.tags,
                linked_concepts=payload.linked_concepts,
            )
        )
    row = LearnerMemoryNoteModel(
        memory_id=str(uuid4()),
        user_id=payload.user_id,
        memory_type=payload.memory_type.value,
        title=payload.title,
        summary=payload.summary,
        tags=payload.tags,
        linked_concepts=payload.linked_concepts,
        linked_skillpath_ids=payload.linked_skillpath_ids,
        linked_content_ids=payload.linked_content_ids,
        evidence_attempt_ids=payload.evidence_attempt_ids,
        embedding=embedding,
        search_text=_build_memory_note_search_text(
            title=payload.title,
            summary=payload.summary,
            tags=payload.tags,
            linked_concepts=payload.linked_concepts,
            linked_skillpath_ids=payload.linked_skillpath_ids,
            linked_content_ids=payload.linked_content_ids,
            evidence_attempt_ids=payload.evidence_attempt_ids,
        ),
        salience_score=payload.salience_score,
        status=payload.status.value,
        last_seen_at=_utcnow(),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def _reinforce_memory_note_row(
    row: LearnerMemoryNoteModel, payload: AddMemoryNoteInput
) -> LearnerMemoryNoteModel:
    row.tags = _merge_unique(row.tags, payload.tags)
    row.linked_concepts = _merge_unique(row.linked_concepts, payload.linked_concepts)
    row.linked_skillpath_ids = _merge_unique(
        row.linked_skillpath_ids, payload.linked_skillpath_ids
    )
    row.linked_content_ids = _merge_unique(
        row.linked_content_ids, payload.linked_content_ids
    )
    row.evidence_attempt_ids = _merge_unique(
        row.evidence_attempt_ids, payload.evidence_attempt_ids
    )
    row.salience_score = _clamp_salience(
        max(float(row.salience_score or 0.0), payload.salience_score)
    )
    if row.status == MemoryStatus.WATCH.value and payload.status == MemoryStatus.ACTIVE:
        row.status = MemoryStatus.ACTIVE.value
    row.last_seen_at = _utcnow()
    await _refresh_memory_note_index(row)
    return row


def _safe_memory_integrity_text_update(value: Any, *, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length:
        return None
    return cleaned


async def _apply_safe_memory_integrity_field_updates(
    row: LearnerMemoryNoteModel,
    field_updates: dict[str, Any] | None,
) -> LearnerMemoryNoteModel:
    if not field_updates:
        return row

    changed = False
    title = _safe_memory_integrity_text_update(
        field_updates.get("title"),
        max_length=180,
    )
    if title is not None:
        row.title = title
        changed = True

    summary = _safe_memory_integrity_text_update(
        field_updates.get("summary"),
        max_length=1200,
    )
    if summary is not None:
        row.summary = summary
        changed = True

    if changed:
        await _refresh_memory_note_index(row)
    return row


async def apply_memory_integrity_decision(
    payload: AddMemoryNoteInput,
    decision,
    session: AsyncSession,
    *,
    embedding: list[float] | None = None,
) -> LearnerMemoryNoteModel:
    action = decision.action
    target_memory_ids = decision.target_memory_ids

    if (
        action in {MemoryIntegrityAction.UPDATE_EXISTING, MemoryIntegrityAction.MERGE}
        and len(target_memory_ids) == 1
    ):
        row = await _get_owned_memory_note_row(
            target_memory_ids[0],
            payload.user_id,
            session,
        )
        row = await _reinforce_memory_note_row(row, payload)
        return await _apply_safe_memory_integrity_field_updates(
            row,
            decision.field_updates,
        )

    if action == MemoryIntegrityAction.SKIP_DUPLICATE and target_memory_ids:
        return await _get_owned_memory_note_row(
            target_memory_ids[0],
            payload.user_id,
            session,
        )

    if action == MemoryIntegrityAction.MERGE and len(target_memory_ids) > 1:
        primary_id = target_memory_ids[0]
        duplicate_ids = target_memory_ids[1:]
        await merge_memory_notes(
            MergeMemoryNotesInput(
                user_id=payload.user_id,
                primary_memory_id=primary_id,
                duplicate_memory_ids=duplicate_ids,
                rationale=decision.rationale,
            ),
            session,
        )
        primary = await _get_owned_memory_note_row(primary_id, payload.user_id, session)
        primary = await _reinforce_memory_note_row(primary, payload)
        return await _apply_safe_memory_integrity_field_updates(
            primary,
            decision.field_updates,
        )

    if action == MemoryIntegrityAction.FLAG_CONFLICT and target_memory_ids:
        row = await _create_memory_note_row(payload, session, embedding=embedding)
        row = await _apply_safe_memory_integrity_field_updates(
            row,
            decision.field_updates,
        )
        now = _utcnow()
        for memory_id in target_memory_ids:
            target = await _get_owned_memory_note_row(
                memory_id,
                payload.user_id,
                session,
            )
            target.status = MemoryStatus.WATCH.value
            target.salience_score = _clamp_salience(
                min(float(target.salience_score or 0.0), 0.45)
            )
            target.last_seen_at = now
        return row

    row = await _create_memory_note_row(payload, session, embedding=embedding)
    return await _apply_safe_memory_integrity_field_updates(
        row,
        decision.field_updates,
    )


async def _create_or_reinforce_memory_note_row(
    payload: AddMemoryNoteInput, session: AsyncSession
) -> LearnerMemoryNoteModel:
    embedding = await _async_embed_text(
        _build_note_embedding_text(
            title=payload.title,
            summary=payload.summary,
            tags=payload.tags,
            linked_concepts=payload.linked_concepts,
        )
    )
    decision = await check_memory_write_integrity(
        payload,
        session,
        incoming_embedding=embedding,
    )
    return await apply_memory_integrity_decision(
        payload,
        decision,
        session,
        embedding=embedding,
    )


async def add_memory_note(
    payload: AddMemoryNoteInput, session: AsyncSession
) -> LearnerMemoryNote:
    row = await _create_or_reinforce_memory_note_row(payload, session)
    await session.commit()
    await session.refresh(row)
    return _to_memory_note(row)


async def _get_owned_memory_note_row(
    memory_id: str, user_id: str, session: AsyncSession
) -> LearnerMemoryNoteModel:
    row = await session.get(LearnerMemoryNoteModel, memory_id)
    if not row:
        raise ValueError(f"Memory note {memory_id} not found")
    if row.user_id != user_id:
        raise ValueError(f"Memory note {memory_id} does not belong to user {user_id}")
    return row


async def update_memory_note(
    payload: UpdateMemoryNoteInput,
    session: AsyncSession,
    *,
    user_id: str | None = None,
) -> LearnerMemoryNote:
    if user_id is not None:
        row = await _get_owned_memory_note_row(payload.memory_id, user_id, session)
    else:
        row = await session.get(LearnerMemoryNoteModel, payload.memory_id)
        if not row:
            raise ValueError(f"Memory note {payload.memory_id} not found")

    updates = payload.model_dump(exclude={"memory_id"}, exclude_unset=True)
    for key, value in updates.items():
        if key in {"status", "memory_type"} and value is not None:
            setattr(row, key, value.value)
        else:
            setattr(row, key, value)
    row.embedding = await _async_embed_text(
        _build_note_embedding_text(
            title=row.title,
            summary=row.summary,
            tags=row.tags or [],
            linked_concepts=row.linked_concepts or [],
        )
    )
    row.search_text = _build_memory_note_search_text(
        title=row.title,
        summary=row.summary,
        tags=row.tags or [],
        linked_concepts=row.linked_concepts or [],
        linked_skillpath_ids=row.linked_skillpath_ids or [],
        linked_content_ids=row.linked_content_ids or [],
        evidence_attempt_ids=row.evidence_attempt_ids or [],
    )
    row.last_seen_at = _utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_memory_note(row)


async def resolve_memory_note(
    memory_id: str, session: AsyncSession, *, user_id: str | None = None
) -> LearnerMemoryNote:
    return await update_memory_note(
        UpdateMemoryNoteInput(memory_id=memory_id, status=MemoryStatus.RESOLVED),
        session,
        user_id=user_id,
    )


async def delete_memory_note(
    memory_id: str, session: AsyncSession, *, user_id: str | None = None
) -> None:
    if user_id is not None:
        row = await _get_owned_memory_note_row(memory_id, user_id, session)
    else:
        row = await session.get(LearnerMemoryNoteModel, memory_id)
        if not row:
            raise ValueError(f"Memory note {memory_id} not found")
    await session.delete(row)
    await session.commit()


async def merge_memory_notes(
    payload: MergeMemoryNotesInput, session: AsyncSession
) -> MergeMemoryNotesResult:
    if not payload.duplicate_memory_ids:
        raise ValueError("At least one duplicate memory ID is required")
    primary = await _get_owned_memory_note_row(
        payload.primary_memory_id, payload.user_id, session
    )
    duplicate_rows = [
        await _get_owned_memory_note_row(memory_id, payload.user_id, session)
        for memory_id in payload.duplicate_memory_ids
    ]
    for duplicate in duplicate_rows:
        if duplicate.memory_type != primary.memory_type:
            raise ValueError("Only notes of the same memory type can be merged")
        primary.tags = _merge_unique(primary.tags, duplicate.tags)
        primary.linked_concepts = _merge_unique(
            primary.linked_concepts, duplicate.linked_concepts
        )
        primary.linked_skillpath_ids = _merge_unique(
            primary.linked_skillpath_ids, duplicate.linked_skillpath_ids
        )
        primary.linked_content_ids = _merge_unique(
            primary.linked_content_ids, duplicate.linked_content_ids
        )
        primary.evidence_attempt_ids = _merge_unique(
            primary.evidence_attempt_ids, duplicate.evidence_attempt_ids
        )
        primary.salience_score = _clamp_salience(
            max(
                float(primary.salience_score or 0.0),
                float(duplicate.salience_score or 0.0),
            )
        )
        duplicate.status = MemoryStatus.RESOLVED.value
        duplicate.last_seen_at = _utcnow()

    primary.last_seen_at = _utcnow()
    await _refresh_memory_note_index(primary)
    await session.commit()
    await session.refresh(primary)
    for duplicate in duplicate_rows:
        await session.refresh(duplicate)
    return MergeMemoryNotesResult(
        primary_note=_to_memory_note(primary),
        merged_memory_ids=[
            primary.memory_id,
            *[row.memory_id for row in duplicate_rows],
        ],
        resolved_memory_ids=[row.memory_id for row in duplicate_rows],
    )


async def resolve_memory_conflict(
    payload: ResolveMemoryConflictInput, session: AsyncSession
) -> ResolveMemoryConflictResult:
    primary = await _get_owned_memory_note_row(
        payload.primary_memory_id, payload.user_id, session
    )
    conflicting = await _get_owned_memory_note_row(
        payload.conflicting_memory_id, payload.user_id, session
    )
    action = MemoryIntegrityAction.KEEP_BOTH_SCOPED
    primary_type = MemoryType(primary.memory_type)
    conflicting_type = MemoryType(conflicting.memory_type)
    now = _utcnow()

    if {
        primary_type,
        conflicting_type,
    } == {MemoryType.MASTERY_SIGNAL, MemoryType.ERROR_PATTERN}:
        error_row = primary if primary_type == MemoryType.ERROR_PATTERN else conflicting
        error_row.status = MemoryStatus.WATCH.value
        error_row.salience_score = _clamp_salience(
            min(float(error_row.salience_score or 0.0), 0.45)
        )
        error_row.last_seen_at = now
        action = MemoryIntegrityAction.FLAG_CONFLICT
    elif primary_type == conflicting_type == MemoryType.PREFERENCE_SIGNAL:
        conflicting.status = MemoryStatus.WATCH.value
        conflicting.salience_score = _clamp_salience(
            min(float(conflicting.salience_score or 0.0), 0.35)
        )
        conflicting.last_seen_at = now
        action = MemoryIntegrityAction.FLAG_CONFLICT

    primary.last_seen_at = now
    await session.commit()
    await session.refresh(primary)
    await session.refresh(conflicting)
    return ResolveMemoryConflictResult(
        primary_note=_to_memory_note(primary),
        conflicting_note=_to_memory_note(conflicting),
        action=action,
        rationale=payload.rationale,
    )


async def record_coding_problem_attempt(
    payload: RecordCodingProblemAttemptInput, session: AsyncSession
) -> CodingProblemAttempt:
    user = await session.get(UserModel, payload.user_id)
    if not user:
        session.add(UserModel(user_id=payload.user_id))

    submitted_at = _utcnow()
    row = CodingProblemAttemptModel(
        attempt_id=str(uuid4()),
        user_id=payload.user_id,
        skillpath_id=payload.skillpath_id,
        content_id=payload.content_id,
        submitted_code=payload.submitted_code,
        language=payload.language,
        correctness=payload.correctness.value,
        feedback_summary=payload.feedback_summary,
        detected_concepts=payload.detected_concepts,
        detected_mistakes=payload.detected_mistakes,
        compile_error=payload.compile_error,
        runtime_error=payload.runtime_error,
        score=payload.score,
        test_results=[item.model_dump(mode="json") for item in payload.test_results],
        submitted_at=submitted_at,
    )
    session.add(row)

    mastery_result = await session.execute(
        select(SkillMasteryStateModel).where(
            SkillMasteryStateModel.user_id == payload.user_id,
            SkillMasteryStateModel.skillpath_id == payload.skillpath_id,
        )
    )
    mastery_row = mastery_result.scalar_one_or_none()
    if not mastery_row:
        mastery_row = SkillMasteryStateModel(
            user_id=payload.user_id,
            skillpath_id=payload.skillpath_id,
            status=MasteryStatus.IN_PROGRESS.value,
            mastery_score=0.0,
            successful_attempts=0,
            failed_attempts=0,
            strong_concepts=[],
            weak_concepts=[],
            last_attempt_at=None,
            last_updated_at=submitted_at,
        )
        session.add(mastery_row)

    mastery_row.successful_attempts = mastery_row.successful_attempts or 0
    mastery_row.failed_attempts = mastery_row.failed_attempts or 0
    mastery_row.strong_concepts = mastery_row.strong_concepts or []
    mastery_row.weak_concepts = mastery_row.weak_concepts or []

    is_success = payload.correctness == AttemptCorrectness.CORRECT
    if is_success:
        mastery_row.successful_attempts += 1
        mastery_row.status = MasteryStatus.PRACTICING.value
        mastery_row.mastery_score = min(1.0, mastery_row.mastery_score + 0.15)
        merged_strong = _normalize_terms(
            (mastery_row.strong_concepts or []) + payload.detected_concepts
        )
        mastery_row.strong_concepts = sorted(merged_strong)
    else:
        mastery_row.failed_attempts += 1
        mastery_row.status = MasteryStatus.PRACTICING.value
        mastery_row.mastery_score = max(0.0, mastery_row.mastery_score - 0.05)
        merged_weak = _normalize_terms(
            (mastery_row.weak_concepts or [])
            + payload.detected_concepts
            + payload.detected_mistakes
        )
        mastery_row.weak_concepts = sorted(merged_weak)
    mastery_row.last_attempt_at = submitted_at
    mastery_row.last_updated_at = submitted_at

    await session.commit()
    await session.refresh(row)
    return _to_attempt(row)


async def _maybe_get_consolidation_judgment(
    *,
    judgment_provider: MemoryConsolidationJudgmentProvider | None,
    attempt: CodingProblemAttempt,
    mastery_state: SkillMasteryState | None,
    candidate_notes: list[LearnerMemoryNote],
    recent_attempts: list[CodingProblemAttempt],
) -> MemoryConsolidationJudgment | None:
    if judgment_provider is None:
        return None
    maybe_judgment = judgment_provider(
        attempt, mastery_state, candidate_notes, recent_attempts
    )
    if inspect.isawaitable(maybe_judgment):
        maybe_judgment = await maybe_judgment
    if maybe_judgment is None:
        return None
    try:
        return MemoryConsolidationJudgment.model_validate(maybe_judgment)
    except Exception:
        return None


async def _apply_consolidation_judgment(
    *,
    judgment: MemoryConsolidationJudgment | None,
    candidate_rows_by_id: dict[str, LearnerMemoryNoteModel],
    user_id: str,
    skillpath_id: str,
    session: AsyncSession,
    now: datetime,
    updated_notes: list[LearnerMemoryNote],
) -> None:
    if judgment is None:
        return

    for adjustment in judgment.salience_adjustments:
        row = candidate_rows_by_id.get(adjustment.memory_id)
        if row is None:
            continue
        bounded_delta = _clamp_delta(adjustment.delta, minimum=-0.15, maximum=0.15)
        row.salience_score = _clamp_salience(
            float(row.salience_score or 0.5) + bounded_delta
        )
        row.last_seen_at = now
        await _refresh_memory_note_index(row)
        updated_notes.append(_to_memory_note(row))

    bounded_mastery_delta = _clamp_delta(
        judgment.mastery_delta, minimum=-0.1, maximum=0.2
    )
    if bounded_mastery_delta == 0.0:
        return
    mastery_result = await session.execute(
        select(SkillMasteryStateModel).where(
            SkillMasteryStateModel.user_id == user_id,
            SkillMasteryStateModel.skillpath_id == skillpath_id,
        )
    )
    mastery_row = mastery_result.scalar_one_or_none()
    if mastery_row:
        mastery_row.mastery_score = _clamp_salience(
            float(mastery_row.mastery_score or 0.0) + bounded_mastery_delta
        )
        mastery_row.last_updated_at = now


async def consolidate_attempt_memory(
    user_id: str,
    attempt_id: str,
    session: AsyncSession,
    *,
    judgment_provider: MemoryConsolidationJudgmentProvider | None = None,
) -> list[LearnerMemoryNote]:
    attempt_row = await session.get(CodingProblemAttemptModel, attempt_id)
    if not attempt_row or attempt_row.user_id != user_id:
        raise ValueError(f"Attempt {attempt_id} not found for user {user_id}")

    mastery_state = await get_skill_mastery_state(
        user_id, attempt_row.skillpath_id, session
    )
    now = _utcnow()
    updated_notes: list[LearnerMemoryNote] = []

    linked_terms = sorted(
        _normalize_terms(
            (attempt_row.detected_mistakes or [])
            + (attempt_row.detected_concepts or [])
        )
    )
    max_related_success_count = 0
    success_overcame_error_pattern = False
    related_success_attempt_ids: set[str] = set()
    if (
        attempt_row.correctness
        in {
            AttemptCorrectness.INCORRECT.value,
            AttemptCorrectness.PARTIALLY_CORRECT.value,
            AttemptCorrectness.RUNTIME_ERROR.value,
        }
        and linked_terms
    ):
        notes_result = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == user_id,
                LearnerMemoryNoteModel.memory_type == MemoryType.ERROR_PATTERN.value,
                LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value,
            )
        )
        candidate_rows = list(notes_result.scalars())
        linked_term_set = set(linked_terms)
        matching_row = next(
            (
                row
                for row in candidate_rows
                if _should_match_error_pattern(
                    row,
                    skillpath_id=attempt_row.skillpath_id,
                    content_id=attempt_row.content_id,
                    linked_term_set=linked_term_set,
                )
            ),
            None,
        )

        summary = (
            f"Learner repeatedly struggles with {', '.join(linked_terms[:3])}. "
            f"Latest feedback: {attempt_row.feedback_summary}"
        )
        tags = sorted(
            _normalize_terms((matching_row.tags if matching_row else []) + linked_terms)
        )
        evidence_attempt_ids = sorted(
            set(
                (matching_row.evidence_attempt_ids if matching_row else [])
                + [attempt_id]
            )
        )

        if matching_row:
            matching_row.title = (
                matching_row.title or f"Repeated issue in {attempt_row.language}"
            )
            matching_row.summary = summary
            matching_row.tags = tags
            matching_row.linked_concepts = sorted(
                _normalize_terms((matching_row.linked_concepts or []) + linked_terms)
            )
            matching_row.linked_skillpath_ids = sorted(
                set(
                    (matching_row.linked_skillpath_ids or [])
                    + [attempt_row.skillpath_id]
                )
            )
            matching_row.linked_content_ids = sorted(
                set((matching_row.linked_content_ids or []) + [attempt_row.content_id])
            )
            matching_row.evidence_attempt_ids = evidence_attempt_ids
            matching_row.salience_score = min(
                1.0, float(matching_row.salience_score or 0.5) + 0.1
            )
            matching_row.status = MemoryStatus.ACTIVE.value
            matching_row.last_seen_at = now
            await _refresh_memory_note_index(matching_row)
            updated_notes.append(_to_memory_note(matching_row))
        else:
            created_row = await _create_or_reinforce_memory_note_row(
                AddMemoryNoteInput(
                    user_id=user_id,
                    memory_type=MemoryType.ERROR_PATTERN,
                    title=f"Repeated issue in {attempt_row.language}",
                    summary=summary,
                    tags=linked_terms,
                    linked_concepts=linked_terms,
                    linked_skillpath_ids=[attempt_row.skillpath_id],
                    linked_content_ids=[attempt_row.content_id],
                    evidence_attempt_ids=[attempt_id],
                    salience_score=0.6,
                    status=MemoryStatus.ACTIVE,
                ),
                session,
            )
            updated_notes.append(_to_memory_note(created_row))

        target_row = matching_row if matching_row else created_row
        if (
            target_row.salience_score >= 0.8
            or len(target_row.evidence_attempt_ids or []) >= 2
        ):
            heuristic_summary = (
                f"Before related exercises, recap {', '.join(linked_terms[:3])} "
                "and provide a small contrast example."
            )
            heuristic_result = await session.execute(
                select(LearnerMemoryNoteModel).where(
                    LearnerMemoryNoteModel.user_id == user_id,
                    LearnerMemoryNoteModel.memory_type == MemoryType.HEURISTIC.value,
                    LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value,
                )
            )
            heuristic_rows = list(heuristic_result.scalars())
            heuristic_row = next(
                (
                    row
                    for row in heuristic_rows
                    if _should_match_error_pattern(
                        row,
                        skillpath_id=attempt_row.skillpath_id,
                        content_id=attempt_row.content_id,
                        linked_term_set=linked_term_set,
                    )
                ),
                None,
            )
            if heuristic_row:
                heuristic_row.summary = heuristic_summary
                heuristic_row.tags = sorted(
                    _normalize_terms((heuristic_row.tags or []) + linked_terms)
                )
                heuristic_row.linked_concepts = sorted(
                    _normalize_terms(
                        (heuristic_row.linked_concepts or []) + linked_terms
                    )
                )
                heuristic_row.linked_skillpath_ids = sorted(
                    set(
                        (heuristic_row.linked_skillpath_ids or [])
                        + [attempt_row.skillpath_id]
                    )
                )
                heuristic_row.linked_content_ids = sorted(
                    set(
                        (heuristic_row.linked_content_ids or [])
                        + [attempt_row.content_id]
                    )
                )
                heuristic_row.evidence_attempt_ids = sorted(
                    set((heuristic_row.evidence_attempt_ids or []) + [attempt_id])
                )
                heuristic_row.salience_score = min(
                    1.0, float(heuristic_row.salience_score or 0.5) + 0.05
                )
                heuristic_row.last_seen_at = now
                heuristic_row.embedding = await _async_embed_text(
                    _build_note_embedding_text(
                        title=heuristic_row.title,
                        summary=heuristic_row.summary,
                        tags=heuristic_row.tags or [],
                        linked_concepts=heuristic_row.linked_concepts or [],
                    )
                )
                heuristic_row.search_text = _build_memory_note_search_text(
                    title=heuristic_row.title,
                    summary=heuristic_row.summary,
                    tags=heuristic_row.tags or [],
                    linked_concepts=heuristic_row.linked_concepts or [],
                    linked_skillpath_ids=heuristic_row.linked_skillpath_ids or [],
                    linked_content_ids=heuristic_row.linked_content_ids or [],
                    evidence_attempt_ids=heuristic_row.evidence_attempt_ids or [],
                )
                updated_notes.append(_to_memory_note(heuristic_row))
            else:
                heuristic_created = await _create_or_reinforce_memory_note_row(
                    AddMemoryNoteInput(
                        user_id=user_id,
                        memory_type=MemoryType.HEURISTIC,
                        title=f"Teaching support for {attempt_row.skillpath_id}",
                        summary=heuristic_summary,
                        tags=linked_terms,
                        linked_concepts=linked_terms,
                        linked_skillpath_ids=[attempt_row.skillpath_id],
                        linked_content_ids=[attempt_row.content_id],
                        evidence_attempt_ids=[attempt_id],
                        salience_score=0.5,
                        status=MemoryStatus.ACTIVE,
                    ),
                    session,
                )
                updated_notes.append(_to_memory_note(heuristic_created))

    if attempt_row.correctness == AttemptCorrectness.CORRECT.value and linked_terms:
        notes_result = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == user_id,
                LearnerMemoryNoteModel.memory_type == MemoryType.ERROR_PATTERN.value,
                LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value,
            )
        )
        linked_term_set = set(linked_terms)
        related_error_rows = [
            row
            for row in notes_result.scalars()
            if _should_match_error_pattern(
                row,
                skillpath_id=attempt_row.skillpath_id,
                content_id=attempt_row.content_id,
                linked_term_set=linked_term_set,
            )
        ]
        for row in related_error_rows:
            row.linked_concepts = sorted(
                _normalize_terms((row.linked_concepts or []) + linked_terms)
            )
            row.linked_skillpath_ids = sorted(
                set((row.linked_skillpath_ids or []) + [attempt_row.skillpath_id])
            )
            row.linked_content_ids = sorted(
                set((row.linked_content_ids or []) + [attempt_row.content_id])
            )
            row.evidence_attempt_ids = sorted(
                set((row.evidence_attempt_ids or []) + [attempt_id])
            )
            row.salience_score = _clamp_salience(float(row.salience_score or 0.5) - 0.1)
            row.summary = (
                f"Learner showed improvement on {', '.join(linked_terms[:3])}. "
                f"Latest feedback: {attempt_row.feedback_summary}"
            )
            success_evidence_attempt_ids = await _get_success_evidence_attempt_ids(
                row, session
            )
            related_success_attempt_ids.update(success_evidence_attempt_ids)
            success_count = len(success_evidence_attempt_ids)
            max_related_success_count = max(max_related_success_count, success_count)
            if success_count >= 2:
                row.status = MemoryStatus.RESOLVED.value
                success_overcame_error_pattern = True
            else:
                row.status = MemoryStatus.WATCH.value
            row.last_seen_at = now
            await _refresh_memory_note_index(row)
            updated_notes.append(_to_memory_note(row))

        if max_related_success_count >= 2 or success_overcame_error_pattern:
            mastery_result = await session.execute(
                select(SkillMasteryStateModel).where(
                    SkillMasteryStateModel.user_id == user_id,
                    SkillMasteryStateModel.skillpath_id == attempt_row.skillpath_id,
                )
            )
            mastery_row = mastery_result.scalar_one_or_none()
            if mastery_row:
                resolved_terms = set(linked_terms)
                mastery_row.weak_concepts = sorted(
                    _normalize_terms(mastery_row.weak_concepts or []) - resolved_terms
                )
                mastery_row.strong_concepts = sorted(
                    _normalize_terms((mastery_row.strong_concepts or []) + linked_terms)
                )
                mastery_row.last_updated_at = now

    if (
        attempt_row.correctness == AttemptCorrectness.CORRECT.value
        and mastery_state is not None
        and (
            mastery_state.mastery_score >= 0.7
            or max_related_success_count >= 2
            or success_overcame_error_pattern
        )
    ):
        mastery_concepts = sorted(
            _normalize_terms(
                mastery_state.strong_concepts + attempt_row.detected_concepts
            )
        )
        notes_result = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == user_id,
                LearnerMemoryNoteModel.memory_type == MemoryType.MASTERY_SIGNAL.value,
                LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value,
            )
        )
        candidate_rows = list(notes_result.scalars())
        matching_row = next(
            (
                row
                for row in candidate_rows
                if attempt_row.skillpath_id in (row.linked_skillpath_ids or [])
            ),
            None,
        )
        summary = (
            f"Learner is showing strong progress on {attempt_row.skillpath_id} "
            f"with correct work and mastery score {mastery_state.mastery_score:.2f}."
        )
        if matching_row:
            matching_row.summary = summary
            matching_row.tags = sorted(
                _normalize_terms((matching_row.tags or []) + mastery_concepts)
            )
            matching_row.linked_concepts = sorted(
                _normalize_terms(
                    (matching_row.linked_concepts or []) + mastery_concepts
                )
            )
            matching_row.linked_content_ids = sorted(
                set((matching_row.linked_content_ids or []) + [attempt_row.content_id])
            )
            matching_row.evidence_attempt_ids = sorted(
                set((matching_row.evidence_attempt_ids or []) + [attempt_id])
                | related_success_attempt_ids
            )
            matching_row.salience_score = min(
                1.0, float(matching_row.salience_score or 0.5) + 0.05
            )
            matching_row.last_seen_at = now
            matching_row.embedding = await _async_embed_text(
                _build_note_embedding_text(
                    title=matching_row.title,
                    summary=matching_row.summary,
                    tags=matching_row.tags or [],
                    linked_concepts=matching_row.linked_concepts or [],
                )
            )
            matching_row.search_text = _build_memory_note_search_text(
                title=matching_row.title,
                summary=matching_row.summary,
                tags=matching_row.tags or [],
                linked_concepts=matching_row.linked_concepts or [],
                linked_skillpath_ids=matching_row.linked_skillpath_ids or [],
                linked_content_ids=matching_row.linked_content_ids or [],
                evidence_attempt_ids=matching_row.evidence_attempt_ids or [],
            )
            updated_notes.append(_to_memory_note(matching_row))
        else:
            created_row = await _create_or_reinforce_memory_note_row(
                AddMemoryNoteInput(
                    user_id=user_id,
                    memory_type=MemoryType.MASTERY_SIGNAL,
                    title=f"Progress in {attempt_row.skillpath_id}",
                    summary=summary,
                    tags=mastery_concepts,
                    linked_concepts=mastery_concepts,
                    linked_skillpath_ids=[attempt_row.skillpath_id],
                    linked_content_ids=[attempt_row.content_id],
                    evidence_attempt_ids=sorted(
                        related_success_attempt_ids | {attempt_id}
                    ),
                    salience_score=0.55,
                    status=MemoryStatus.ACTIVE,
                ),
                session,
            )
            updated_notes.append(_to_memory_note(created_row))

    if judgment_provider is not None:
        candidate_result = await session.execute(
            select(LearnerMemoryNoteModel).where(
                LearnerMemoryNoteModel.user_id == user_id,
                LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value,
            )
        )
        candidate_rows = list(candidate_result.scalars())
        recent_attempts_result = await session.execute(
            select(CodingProblemAttemptModel)
            .where(
                CodingProblemAttemptModel.user_id == user_id,
                CodingProblemAttemptModel.skillpath_id == attempt_row.skillpath_id,
            )
            .order_by(CodingProblemAttemptModel.submitted_at.desc())
            .limit(5)
        )
        current_mastery_state = await get_skill_mastery_state(
            user_id, attempt_row.skillpath_id, session
        )
        judgment = await _maybe_get_consolidation_judgment(
            judgment_provider=judgment_provider,
            attempt=_to_attempt(attempt_row),
            mastery_state=current_mastery_state,
            candidate_notes=[_to_memory_note(row) for row in candidate_rows],
            recent_attempts=[
                _to_attempt(row) for row in recent_attempts_result.scalars()
            ],
        )
        await _apply_consolidation_judgment(
            judgment=judgment,
            candidate_rows_by_id={row.memory_id: row for row in candidate_rows},
            user_id=user_id,
            skillpath_id=attempt_row.skillpath_id,
            session=session,
            now=now,
            updated_notes=updated_notes,
        )

    await session.commit()
    return updated_notes


async def record_and_consolidate_attempt(
    payload: RecordCodingProblemAttemptInput,
    session: AsyncSession,
    *,
    judgment_provider: MemoryConsolidationJudgmentProvider | None = None,
) -> tuple[CodingProblemAttempt, list[LearnerMemoryNote]]:
    attempt = await record_coding_problem_attempt(payload, session)
    updated_notes = await consolidate_attempt_memory(
        payload.user_id,
        attempt.attempt_id,
        session,
        judgment_provider=judgment_provider,
    )
    return attempt, updated_notes


async def get_skill_mastery_state(
    user_id: str, skillpath_id: str, session: AsyncSession
) -> SkillMasteryState | None:
    result = await session.execute(
        select(SkillMasteryStateModel).where(
            SkillMasteryStateModel.user_id == user_id,
            SkillMasteryStateModel.skillpath_id == skillpath_id,
        )
    )
    row = result.scalar_one_or_none()
    return _to_mastery_state(row) if row else None


SkillpathCompletionAdvisorProvider = Callable[
    [SkillPathItem, "SkillMasteryState | None", list[CodingProblemAttempt]],
    Any,
]

_DETERMINISTIC_COMPLETION_ADVICE = SkillpathCompletionAdvisorOutput(
    suggested_mastery_status=MasteryStatus.PRACTICING,
    mastery_signal_salience=0.5,
    signal_strength="weak",
    reasoning="Deterministic fallback: completion recorded without strong evidence.",
)


def _completion_env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _completion_has_llm_credentials() -> bool:
    return any(
        os.getenv(name)
        for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY")
    )


def _default_completion_advisor() -> SkillpathCompletionAdvisorProvider | None:
    """LLM-first advisor when enabled and credentialed; None triggers fallback."""
    if not _completion_env_flag("ENABLE_SKILLPATH_COMPLETION_ADVISOR", False):
        return None
    if not _completion_has_llm_credentials():
        return None

    async def _advisor(
        skillpath: SkillPathItem,
        mastery_state: SkillMasteryState | None,
        recent_attempts: list[CodingProblemAttempt],
    ) -> SkillpathCompletionAdvisorOutput:
        return await advise_skillpath_completion(
            skillpath, mastery_state, recent_attempts
        )

    return _advisor


async def mark_skillpath_completed(
    user_id: str,
    skillpath_id: str,
    session: AsyncSession,
    *,
    completion_advisor: SkillpathCompletionAdvisorProvider | None = None,
) -> MarkSkillpathCompletedResult:
    """Orchestrate the effects of a learner marking a skillpath done.

    1. Set skillpaths.status = "completed" (unconditional).
    2. Load mastery state + recent attempts.
    3. Judge signal strength with the completion advisor (LLM-first, deterministic
       fallback when disabled / uncredentialed / invalid output).
    4. Hard guard: "mastered" requires at least one correct attempt.
    5. Upsert skill_mastery_states with the judged status.
    6. Write a mastery_signal note through the Memory Integrity lifecycle.
    """
    from app.services import roadmap as roadmap_service

    # Step 1: always mark the skillpath record completed.
    skillpath = await roadmap_service.update_skillpath(
        user_id, skillpath_id, session, status="completed"
    )

    # Step 2: gather evidence.
    mastery_state = await get_skill_mastery_state(user_id, skillpath_id, session)
    attempts_result = await session.execute(
        select(CodingProblemAttemptModel)
        .where(
            CodingProblemAttemptModel.user_id == user_id,
            CodingProblemAttemptModel.skillpath_id == skillpath_id,
        )
        .order_by(CodingProblemAttemptModel.submitted_at.desc())
        .limit(5)
    )
    recent_attempts = [_to_attempt(row) for row in attempts_result.scalars()]

    # Step 3: advisor judgment, LLM-first with deterministic fallback.
    advisor = (
        completion_advisor
        if completion_advisor is not None
        else _default_completion_advisor()
    )
    advisor_used = advisor is not None
    advice = _DETERMINISTIC_COMPLETION_ADVICE
    if advisor is not None:
        try:
            raw = await advisor(skillpath, mastery_state, recent_attempts)
            advice = SkillpathCompletionAdvisorOutput.model_validate(raw)
        except Exception:
            advice = _DETERMINISTIC_COMPLETION_ADVICE
            advisor_used = False

    # Step 4: hard guard — "mastered" only with correct-attempt evidence.
    correct_attempts = [
        a for a in recent_attempts if a.correctness == AttemptCorrectness.CORRECT
    ]
    suggested = advice.suggested_mastery_status
    if suggested == MasteryStatus.MASTERED and not recent_attempts:
        suggested = MasteryStatus.PRACTICING
    elif suggested == MasteryStatus.MASTERED and not correct_attempts:
        suggested = MasteryStatus.IN_PROGRESS

    # Step 5: upsert mastery state directly (aggregate tracker, not a memory note).
    now = _utcnow()
    mastery_row = (
        await session.execute(
            select(SkillMasteryStateModel).where(
                SkillMasteryStateModel.user_id == user_id,
                SkillMasteryStateModel.skillpath_id == skillpath_id,
            )
        )
    ).scalar_one_or_none()
    if not mastery_row:
        mastery_row = SkillMasteryStateModel(
            user_id=user_id,
            skillpath_id=skillpath_id,
            status=suggested.value,
            mastery_score=0.0,
            successful_attempts=0,
            failed_attempts=0,
            strong_concepts=[],
            weak_concepts=[],
            last_attempt_at=None,
            last_updated_at=now,
        )
        session.add(mastery_row)
    mastery_row.status = suggested.value
    mastery_row.last_updated_at = now
    await session.commit()
    await session.refresh(mastery_row)
    mastery_state_out = _to_mastery_state(mastery_row)

    # Step 6: write mastery_signal through the integrity lifecycle. The Integrity
    # Service finds overlapping active error_pattern notes and may flag_conflict,
    # moving them to watch — no explicit downgrade step needed here.
    note_payload = AddMemoryNoteInput(
        user_id=user_id,
        memory_type=MemoryType.MASTERY_SIGNAL,
        title=f"Completed skillpath: {skillpath.title}",
        summary=(
            f"Learner marked skillpath '{skillpath.title}' complete. "
            f"Suggested mastery: {suggested.value}. {advice.reasoning}"
        ),
        linked_skillpath_ids=[skillpath_id],
        linked_concepts=list(skillpath.learning_objectives or []),
        evidence_attempt_ids=[a.attempt_id for a in recent_attempts],
        salience_score=advice.mastery_signal_salience,
    )
    mastery_signal = await add_memory_note(note_payload, session)

    return MarkSkillpathCompletedResult(
        skillpath=skillpath,
        mastery_state=mastery_state_out,
        mastery_signal=mastery_signal,
        advisor_used=advisor_used,
    )


def _collect_linked_skillpath_ids(context: LearningMemoryContext) -> set[str]:
    """Collect every unique linked_skillpath_id across all note buckets."""
    ids: set[str] = set()
    buckets = (
        context.active_error_patterns,
        context.mastery_signals,
        context.teaching_heuristics,
        context.background_notes,
        context.relevant_notes,
    )
    for bucket in buckets:
        for note in bucket:
            for sid in note.linked_skillpath_ids or []:
                ids.add(sid)
    return ids


async def load_mastery_states_for_skillpaths(
    user_id: str,
    skillpath_ids: set[str] | list[str],
    session: AsyncSession,
) -> dict[str, SkillMasteryState]:
    """Batch-load mastery states for a set of skillpaths, keyed by skillpath_id.

    Returns an empty dict (no query issued) when ``skillpath_ids`` is empty.
    """
    ids = list(skillpath_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(SkillMasteryStateModel).where(
            SkillMasteryStateModel.user_id == user_id,
            SkillMasteryStateModel.skillpath_id.in_(ids),
        )
    )
    return {row.skillpath_id: _to_mastery_state(row) for row in result.scalars()}


async def retrieve_learning_memory(
    payload: RetrieveLearningMemoryInput, session: AsyncSession
) -> LearningMemoryContext:
    mastery_state = None
    if payload.skillpath_id:
        mastery_state = await get_skill_mastery_state(
            payload.user_id, payload.skillpath_id, session
        )

    attempts_query = (
        select(CodingProblemAttemptModel)
        .where(CodingProblemAttemptModel.user_id == payload.user_id)
        .order_by(CodingProblemAttemptModel.submitted_at.desc())
    )
    if payload.skillpath_id:
        attempts_query = attempts_query.where(
            CodingProblemAttemptModel.skillpath_id == payload.skillpath_id
        )
    if payload.content_id:
        attempts_query = attempts_query.where(
            CodingProblemAttemptModel.content_id == payload.content_id
        )
    attempts_result = await session.execute(
        attempts_query.limit(payload.top_k_attempts)
    )
    recent_attempts = [_to_attempt(row) for row in attempts_result.scalars()]

    query_terms = _tokenize_query(payload.query_text)
    query_embedding = await _async_embed_text(payload.query_text)
    note_rows = await get_memory_note_candidates(
        payload,
        query_embedding,
        session,
        candidate_limit=max(50, payload.top_k_notes * 10),
    )
    # Candidate retrieval happens in Postgres; Python keeps the final hybrid rerank
    # small and explainable. A future LLM/reranker can use this same candidate set.
    scored_notes = sorted(
        note_rows,
        key=lambda row: _memory_note_score(
            row,
            skillpath_id=payload.skillpath_id,
            content_id=payload.content_id,
            concept_keys=payload.concept_keys,
            query_terms=query_terms,
            query_embedding=query_embedding,
        ),
        reverse=True,
    )[: payload.top_k_notes]

    now = _utcnow()
    for row in scored_notes:
        row.last_used_at = now
    await session.commit()

    relevant_notes = [_to_memory_note(row) for row in scored_notes]
    (
        active_error_patterns,
        mastery_signals,
        teaching_heuristics,
        background_notes,
    ) = _partition_notes(relevant_notes)

    context = LearningMemoryContext(
        mastery_state=mastery_state,
        recent_attempts=recent_attempts,
        active_error_patterns=active_error_patterns,
        mastery_signals=mastery_signals,
        teaching_heuristics=teaching_heuristics,
        background_notes=background_notes,
        relevant_notes=relevant_notes,
    )

    # Bridge: when no skillpath_id was supplied, mastery_state is null. Surface
    # mastery data for the skillpaths the retrieved notes are scoped to.
    linked_ids = _collect_linked_skillpath_ids(context)
    if payload.skillpath_id:
        linked_ids.discard(payload.skillpath_id)
    context.linked_mastery_states = await load_mastery_states_for_skillpaths(
        payload.user_id, linked_ids, session
    )

    return context
