## Why

The learning-memory write path already performs an integrity check before creating notes, but only `create_new`, `update_existing`, and `skip_duplicate` are applied clearly. Advisor recommendations such as `merge`, `keep_both_scoped`, and `flag_conflict` can be returned but are not yet executed consistently, which can still allow duplicate or contradictory long-term learner memories to accumulate.

## What Changes

- Add a deterministic memory integrity executor that applies all six `MemoryIntegrityAction` values through the shared learning-memory write path.
- Keep the LLM integrity advisor advisory-only: it may recommend an action, target memory IDs, rationale, and safe field updates, but the service validates and owns all DB mutations.
- Phase 1: implement safe DB behavior for `create_new`, `update_existing`, `skip_duplicate`, `keep_both_scoped`, `merge`, and `flag_conflict`.
- Phase 2: allow bounded advisor-provided `title` and `summary` updates for merge/scoped/conflict cases after service-side validation.
- Add TDD-first unit tests for every action and targeted live smoke tests for real advisor recommendations.
- No breaking API changes are expected; callers should continue using existing memory service and MCP entry points.

## Capabilities

### New Capabilities
- `memory-integrity-execution`: Shared execution contract for applying memory integrity decisions to learner memory writes.

### Modified Capabilities
- None.

## Impact

- Affected services:
  - `backend/app/services/learning_memory.py`
  - `backend/app/services/memory_integrity.py`
  - `backend/app/advisors/memory_advisors.py`
- Affected schemas:
  - `MemoryIntegrityDecision`
  - `MemoryIntegrityAdvisorRecommendation`
  - `MemoryIntegrityAction`
- Affected tests:
  - `backend/tests/test_learning_memory_service.py`
  - `backend/tests/test_memory_advisors.py`
  - `backend/tests/test_live_agent_memory_integration.py`
- Downstream benefits:
  - code-correction memory consolidation
  - MCP memory note writes
  - future profile/preference memory writes through the same shared service
  - future memory maintenance and repair workflows
