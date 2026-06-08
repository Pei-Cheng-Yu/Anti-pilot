from datetime import UTC, datetime

import pytest
from app.advisors import memory_advisors
from app.schema.entities import (
    AddMemoryNoteInput,
    HintRequest,
    LearnerMemoryNote,
    LearningMemoryContext,
    MemoryIntegrityEvidence,
    MemoryRerankRequest,
    MemoryRerankResult,
    SelectedMemoryMetadata,
)
from app.schema.enums import (
    HintLevel,
    MemoryIntegrityAction,
    MemoryRerankPurpose,
    MemoryStatus,
    MemoryType,
    TeachingAction,
)


def _memory(memory_id: str = "memory-1") -> LearnerMemoryNote:
    return LearnerMemoryNote(
        memory_id=memory_id,
        user_id="user-1",
        memory_type=MemoryType.ERROR_PATTERN,
        title="Missing await",
        summary="Learner forgets await in FastAPI route handlers.",
        tags=["await", "fastapi"],
        linked_concepts=["fastapi.async", "missing_await"],
        linked_skillpath_ids=["sp-fastapi-routing"],
        salience_score=0.8,
        status=MemoryStatus.ACTIVE,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


def test_hint_advisor_prompt_contains_low_spoiler_and_bounded_memory_ids():
    prompt = memory_advisors.build_hint_advisor_prompt(
        HintRequest(
            user_id="user-1",
            skillpath_id="sp-fastapi-routing",
            task_prompt="Fix the route handler.",
            submitted_code="product = get_product_from_db(product_id)",
            concept_keys=["fastapi.async"],
            hint_level=HintLevel.NUDGE,
        ),
        LearningMemoryContext(relevant_notes=[_memory()]),
        MemoryRerankResult(
            purpose=MemoryRerankPurpose.HINT_GENERATION,
            selected_memories=[
                SelectedMemoryMetadata(
                    memory_id="memory-1",
                    memory_type=MemoryType.ERROR_PATTERN,
                    title="Missing await",
                    reason="Relevant active memory.",
                )
            ],
            teaching_action=TeachingAction.QUICK_RECAP_THEN_HINT,
        ),
    )

    assert "memory-1" in prompt
    assert "Do not reveal complete corrected code" in prompt
    assert "HintResponse" in prompt


def test_rerank_advisor_prompt_contains_purpose_and_candidate_ids():
    prompt = memory_advisors.build_rerank_advisor_prompt(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.CODE_CORRECTION,
            task_context="Correct the FastAPI route.",
            candidate_memories=[_memory("candidate-1")],
        )
    )

    assert "code_correction" in prompt
    assert "candidate-1" in prompt
    assert "selected memory IDs must come from the candidates" in prompt


def test_integrity_advisor_prompt_preserves_service_owned_write_guardrail():
    prompt = memory_advisors.build_integrity_advisor_prompt(
        AddMemoryNoteInput(
            user_id="user-1",
            memory_type=MemoryType.ERROR_PATTERN,
            title="Missing await",
            summary="Learner forgets await in FastAPI routes.",
            linked_concepts=["fastapi.async"],
        ),
        candidates=[_memory("candidate-1")],
        evidence=[
            MemoryIntegrityEvidence(
                candidate_memory_id="candidate-1",
                candidate_memory_type=MemoryType.ERROR_PATTERN,
                type_compatible=True,
                concept_overlap=1,
                semantic_similarity=0.9,
            )
        ],
        allowed_actions=[MemoryIntegrityAction.MERGE],
    )

    assert "candidate-1" in prompt
    assert "merge" in prompt
    assert "Do not write to the database" in prompt


@pytest.mark.asyncio
async def test_advisor_invocation_parses_structured_response_from_fake_agent():
    class FakeAgent:
        async def ainvoke(self, _payload):
            return {
                "structured_response": {
                    "hint": "Look for the async call that returns an awaitable.",
                    "hint_level": "nudge",
                    "teaching_action": "quick_recap_then_hint",
                    "selected_memory_ids": ["memory-1"],
                    "focused_concepts": ["fastapi.async"],
                    "used_memory": True,
                }
            }

    hint = await memory_advisors.generate_hint_advice(
        HintRequest(
            user_id="user-1",
            skillpath_id="sp-fastapi-routing",
            task_prompt="Fix the route handler.",
            submitted_code="product = get_product_from_db(product_id)",
            concept_keys=["fastapi.async"],
            hint_level=HintLevel.NUDGE,
        ),
        LearningMemoryContext(relevant_notes=[_memory()]),
        MemoryRerankResult(
            purpose=MemoryRerankPurpose.HINT_GENERATION,
            selected_memories=[
                SelectedMemoryMetadata(
                    memory_id="memory-1",
                    memory_type=MemoryType.ERROR_PATTERN,
                    title="Missing await",
                )
            ],
        ),
        agent_factory=lambda **_kwargs: FakeAgent(),
    )

    assert hint.selected_memory_ids == ["memory-1"]
    assert hint.teaching_action == TeachingAction.QUICK_RECAP_THEN_HINT
