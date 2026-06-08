from app.schema.entities import (
    AddMemoryNoteInput,
    HintRequest,
    MemoryRerankRequest,
    MemoryRerankResult,
    RecordCodingProblemAttemptInput,
    RetrieveLearningMemoryInput,
    UpdateMemoryNoteInput,
)
from app.services import learning_memory, memory_hint, memory_rerank_policy
from sqlalchemy.ext.asyncio import AsyncSession


async def add_memory_note(payload: AddMemoryNoteInput, session: AsyncSession):
    return await learning_memory.add_memory_note(payload, session)


async def update_memory_note(
    payload: UpdateMemoryNoteInput,
    session: AsyncSession,
    *,
    user_id: str | None = None,
):
    return await learning_memory.update_memory_note(payload, session, user_id=user_id)


async def resolve_memory_note(
    memory_id: str,
    session: AsyncSession,
    *,
    user_id: str | None = None,
):
    return await learning_memory.resolve_memory_note(
        memory_id,
        session,
        user_id=user_id,
    )


async def delete_memory_note(
    memory_id: str,
    session: AsyncSession,
    *,
    user_id: str | None = None,
) -> None:
    await learning_memory.delete_memory_note(memory_id, session, user_id=user_id)


async def record_coding_problem_attempt(
    payload: RecordCodingProblemAttemptInput,
    session: AsyncSession,
):
    return await learning_memory.record_coding_problem_attempt(payload, session)


async def record_and_consolidate_attempt(
    payload: RecordCodingProblemAttemptInput,
    session: AsyncSession,
    *,
    judgment_provider=None,
):
    if judgment_provider is None:
        return await learning_memory.record_and_consolidate_attempt(payload, session)

    return await learning_memory.record_and_consolidate_attempt(
        payload,
        session,
        judgment_provider=judgment_provider,
    )


async def get_skill_mastery_state(
    user_id: str,
    skillpath_id: str,
    session: AsyncSession,
):
    return await learning_memory.get_skill_mastery_state(user_id, skillpath_id, session)


async def retrieve_learning_memory(
    payload: RetrieveLearningMemoryInput,
    session: AsyncSession,
):
    return await learning_memory.retrieve_learning_memory(payload, session)


async def rerank_memories(
    payload: MemoryRerankRequest,
    *,
    advisor=None,
) -> MemoryRerankResult:
    return await memory_rerank_policy.arerank_memories(payload, advisor=advisor)


async def generate_memory_aware_hint(
    payload: HintRequest,
    session: AsyncSession,
):
    return await memory_hint.generate_memory_aware_hint(payload, session)
