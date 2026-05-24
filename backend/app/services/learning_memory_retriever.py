from __future__ import annotations

from app.db.model import LearnerMemoryNoteModel
from app.schema.entities import RetrieveLearningMemoryInput
from app.schema.enums import MemoryStatus
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession


def _dedupe_note_rows_by_id(
    rows: list[LearnerMemoryNoteModel],
) -> list[LearnerMemoryNoteModel]:
    seen: set[str] = set()
    deduped: list[LearnerMemoryNoteModel] = []
    for row in rows:
        if row.memory_id in seen:
            continue
        seen.add(row.memory_id)
        deduped.append(row)
    return deduped


def _apply_memory_type_filter(statement, payload: RetrieveLearningMemoryInput):
    if not payload.memory_types:
        return statement
    return statement.where(
        LearnerMemoryNoteModel.memory_type.in_(
            [memory_type.value for memory_type in payload.memory_types]
        )
    )


async def _get_vector_candidates(
    payload: RetrieveLearningMemoryInput,
    query_embedding: list[float],
    session: AsyncSession,
    limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    statement = (
        select(LearnerMemoryNoteModel)
        .where(LearnerMemoryNoteModel.user_id == payload.user_id)
        .where(LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value)
        .where(LearnerMemoryNoteModel.embedding.is_not(None))
        .order_by(LearnerMemoryNoteModel.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    result = await session.execute(_apply_memory_type_filter(statement, payload))
    return list(result.scalars())


async def _get_keyword_candidates(
    payload: RetrieveLearningMemoryInput,
    session: AsyncSession,
    limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    if not payload.query_text.strip():
        return []
    statement = (
        select(LearnerMemoryNoteModel)
        .where(LearnerMemoryNoteModel.user_id == payload.user_id)
        .where(LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value)
        .where(
            text(
                "to_tsvector('english', search_text) @@ "
                "plainto_tsquery('english', :query)"
            )
        )
        .params(query=payload.query_text)
        .limit(limit)
    )
    result = await session.execute(_apply_memory_type_filter(statement, payload))
    return list(result.scalars())


async def _get_scope_candidates(
    payload: RetrieveLearningMemoryInput,
    session: AsyncSession,
    limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    conditions = []
    if payload.skillpath_id:
        conditions.append(
            LearnerMemoryNoteModel.linked_skillpath_ids.any(payload.skillpath_id)
        )
    if payload.content_id:
        conditions.append(
            LearnerMemoryNoteModel.linked_content_ids.any(payload.content_id)
        )
    for concept in payload.concept_keys:
        conditions.append(LearnerMemoryNoteModel.linked_concepts.any(concept))
    if not conditions:
        return []

    statement = (
        select(LearnerMemoryNoteModel)
        .where(LearnerMemoryNoteModel.user_id == payload.user_id)
        .where(LearnerMemoryNoteModel.status != MemoryStatus.RESOLVED.value)
        .where(or_(*conditions))
        .limit(limit)
    )
    result = await session.execute(_apply_memory_type_filter(statement, payload))
    return list(result.scalars())


async def get_memory_note_candidates(
    payload: RetrieveLearningMemoryInput,
    query_embedding: list[float],
    session: AsyncSession,
    candidate_limit: int = 50,
) -> list[LearnerMemoryNoteModel]:
    vector_rows = await _get_vector_candidates(
        payload, query_embedding, session, candidate_limit
    )
    keyword_rows = await _get_keyword_candidates(payload, session, candidate_limit)
    scope_rows = await _get_scope_candidates(payload, session, candidate_limit)
    return _dedupe_note_rows_by_id([*vector_rows, *keyword_rows, *scope_rows])
