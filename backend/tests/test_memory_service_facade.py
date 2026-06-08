from unittest.mock import AsyncMock

import pytest
from app.schema.entities import (
    AddMemoryNoteInput,
    HintRequest,
    RecordCodingProblemAttemptInput,
    RetrieveLearningMemoryInput,
    UpdateMemoryNoteInput,
)
from app.schema.enums import AttemptCorrectness, HintLevel, MemoryType
from app.services import memory_service


@pytest.mark.asyncio
async def test_memory_facade_delegates_durable_note_writes(monkeypatch):
    session = object()
    payload = AddMemoryNoteInput(
        user_id="user-1",
        memory_type=MemoryType.PREFERENCE_SIGNAL,
        title="Examples first",
        summary="Learner prefers examples before abstract explanations.",
    )
    expected = object()
    add_memory_note = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        memory_service.learning_memory,
        "add_memory_note",
        add_memory_note,
    )

    result = await memory_service.add_memory_note(payload, session)

    assert result is expected
    add_memory_note.assert_awaited_once_with(payload, session)


@pytest.mark.asyncio
async def test_memory_facade_delegates_context_attempt_and_hint_workflows(monkeypatch):
    session = object()
    retrieve_input = RetrieveLearningMemoryInput(
        user_id="user-1",
        query_text="fastapi async await",
    )
    attempt_input = RecordCodingProblemAttemptInput(
        user_id="user-1",
        skillpath_id="sp-1",
        content_id="cp-1",
        submitted_code="result = fetch_user()",
        language="python",
        correctness=AttemptCorrectness.RUNTIME_ERROR,
        feedback_summary="coroutine was never awaited",
    )
    hint_input = HintRequest(
        user_id="user-1",
        task_prompt="Fix the async route.",
        submitted_code="result = fetch_user()",
        concept_keys=["fastapi.async"],
        hint_level=HintLevel.NUDGE,
    )
    expected_context = object()
    expected_attempt_result = (object(), [object()])
    expected_hint = object()
    retrieve_learning_memory = AsyncMock(return_value=expected_context)
    record_and_consolidate_attempt = AsyncMock(return_value=expected_attempt_result)
    generate_memory_aware_hint = AsyncMock(return_value=expected_hint)
    monkeypatch.setattr(
        memory_service.learning_memory,
        "retrieve_learning_memory",
        retrieve_learning_memory,
    )
    monkeypatch.setattr(
        memory_service.learning_memory,
        "record_and_consolidate_attempt",
        record_and_consolidate_attempt,
    )
    monkeypatch.setattr(
        memory_service.memory_hint,
        "generate_memory_aware_hint",
        generate_memory_aware_hint,
    )

    context = await memory_service.retrieve_learning_memory(retrieve_input, session)
    attempt_result = await memory_service.record_and_consolidate_attempt(
        attempt_input,
        session,
    )
    hint = await memory_service.generate_memory_aware_hint(hint_input, session)

    assert context is expected_context
    assert attempt_result == expected_attempt_result
    assert hint is expected_hint
    retrieve_learning_memory.assert_awaited_once_with(retrieve_input, session)
    record_and_consolidate_attempt.assert_awaited_once_with(attempt_input, session)
    generate_memory_aware_hint.assert_awaited_once_with(hint_input, session)


@pytest.mark.asyncio
async def test_memory_facade_exposes_lifecycle_mutations(monkeypatch):
    session = object()
    update = UpdateMemoryNoteInput(memory_id="mem-1", title="Updated")
    update_memory_note = AsyncMock(return_value="updated")
    resolve_memory_note = AsyncMock(return_value="resolved")
    delete_memory_note = AsyncMock(return_value=None)
    monkeypatch.setattr(
        memory_service.learning_memory,
        "update_memory_note",
        update_memory_note,
    )
    monkeypatch.setattr(
        memory_service.learning_memory,
        "resolve_memory_note",
        resolve_memory_note,
    )
    monkeypatch.setattr(
        memory_service.learning_memory,
        "delete_memory_note",
        delete_memory_note,
    )

    assert (
        await memory_service.update_memory_note(
            update,
            session,
            user_id="user-1",
        )
        == "updated"
    )
    assert (
        await memory_service.resolve_memory_note(
            "mem-1",
            session,
            user_id="user-1",
        )
        == "resolved"
    )
    await memory_service.delete_memory_note("mem-1", session, user_id="user-1")

    update_memory_note.assert_awaited_once_with(update, session, user_id="user-1")
    resolve_memory_note.assert_awaited_once_with(
        "mem-1",
        session,
        user_id="user-1",
    )
    delete_memory_note.assert_awaited_once_with(
        "mem-1",
        session,
        user_id="user-1",
    )
