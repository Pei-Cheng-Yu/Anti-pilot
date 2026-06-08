from app.schema.entities import HintResponse, MemoryIntegrityDecision
from app.schema.enums import (
    HintLevel,
    MemoryIntegrityAction,
    MemoryRerankPurpose,
    TeachingAction,
)


def test_memory_advisor_enums_live_in_schema_enums_and_preserve_values():
    assert MemoryIntegrityAction.MERGE.value == "merge"
    assert HintLevel.NUDGE.value == "nudge"
    assert TeachingAction.QUICK_RECAP_THEN_HINT.value == "quick_recap_then_hint"
    assert MemoryRerankPurpose.HINT_GENERATION.value == "hint_generation"

    hint = HintResponse(
        hint="Look at the async call.",
        hint_level=HintLevel.NUDGE,
        teaching_action=TeachingAction.QUICK_RECAP_THEN_HINT,
    )
    decision = MemoryIntegrityDecision(action=MemoryIntegrityAction.CREATE_NEW)

    assert hint.model_dump(mode="json")["hint_level"] == "nudge"
    assert hint.model_dump(mode="json")["teaching_action"] == "quick_recap_then_hint"
    assert decision.model_dump(mode="json")["action"] == "create_new"
