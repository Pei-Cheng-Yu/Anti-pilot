## Context

The backend already routes code-attempt consolidation and direct memory-note writes through `learning_memory.add_memory_note(...)` / `_create_or_reinforce_memory_note_row(...)`. That shared path calls `check_memory_write_integrity(...)`, which can use deterministic signals and an optional LLM advisor to recommend a `MemoryIntegrityAction`.

The gap is execution. The shared write path currently applies `update_existing` and `skip_duplicate` specially, then falls back to creating a new note for other actions. This means `merge`, `keep_both_scoped`, and `flag_conflict` can be valid recommendations but are not applied as first-class lifecycle operations. Manual services already exist for merge and conflict repair, but automatic memory writes do not consistently use them.

The change should strengthen the existing shared service boundary instead of adding feature-specific memory write branches.

## Goals / Non-Goals

**Goals:**
- Make every `MemoryIntegrityAction` executable through one shared memory write path.
- Keep LLM advisor output advisory-only and bounded by deterministic service validation.
- Preserve current callers: code correction, consolidation, and MCP/direct memory writes should continue using the same public service functions.
- Add TDD-first tests that prove each action changes memory state as expected.
- Add Phase 2 support for safe advisor-provided `title` and `summary` updates.

**Non-Goals:**
- Build a periodic memory maintenance scanner in this change.
- Convert `GoalSpec` or `LearningProfile` wholesale into memory notes.
- Let LLMs directly mutate the database or choose unvalidated memory IDs.
- Add new database tables unless implementation discovers an unavoidable need.
- Automatically delete memory notes during conflict handling.

## Decisions

### Decision: Add a deterministic integrity executor

Add an internal function such as `apply_memory_integrity_decision(...)` used by `_create_or_reinforce_memory_note_row(...)` after `check_memory_write_integrity(...)`.

The executor owns all DB writes:
- `CREATE_NEW`: create the incoming note.
- `UPDATE_EXISTING`: reinforce one target note with incoming scope, evidence, tags, concepts, salience, and refreshed indexes.
- `SKIP_DUPLICATE`: return the target note unchanged.
- `KEEP_BOTH_SCOPED`: create the incoming note and leave targets unchanged.
- `MERGE`: if one target is provided, treat the incoming note as `UPDATE_EXISTING`; if multiple existing targets are provided, merge existing targets through `merge_memory_notes(...)` and reinforce the primary with incoming evidence.
- `FLAG_CONFLICT`: create the incoming note, mark target conflicting memories as `watch`, lower their salience conservatively, and leave both notes available for retrieval.

Alternative considered: keep `merge` and `flag_conflict` as manual maintenance actions only. This avoids write-path complexity but leaves the advisor able to recommend actions that the automatic path ignores, which is surprising and harder to test.

### Decision: Keep one shared memory write protocol

Do not add separate MCP, code-correction, profile-agent, or maintenance integrity implementations. All current and future memory creation paths should call the learning-memory service and receive the same integrity behavior.

Alternative considered: implement integrity behavior at each caller. This would make each workflow easier to customize but would duplicate lifecycle rules and increase drift risk.

### Decision: Keep LLM field updates narrow in Phase 2

Advisor `field_updates` may be used only for validated `title` and `summary` updates in Phase 2. The service must reject attempts to update identity, ownership, status, salience, evidence, embeddings, timestamps, or memory type.

Alternative considered: allow LLMs to update tags and concepts too. That may be useful later, but tags/concepts affect retrieval scope and should remain deterministic until title/summary behavior is proven safe.

### Decision: Conflict handling is conservative

Automatic `FLAG_CONFLICT` should not delete or resolve notes. It should preserve both sides and downgrade target conflicts to `watch` with lower salience. Stronger conflict repair can remain in `resolve_memory_conflict(...)` or a future maintenance workflow.

Alternative considered: immediately resolve the older note. That risks hiding useful learner history when the conflict is context-specific or the advisor is overconfident.

## Risks / Trade-offs

- [Risk] `MERGE` with multiple targets could choose the wrong primary if advisor target order is poor. → Mitigation: use deterministic primary selection or validate target order; tests must cover primary/duplicate outcomes.
- [Risk] `FLAG_CONFLICT` may downgrade a still-relevant memory. → Mitigation: lower to `watch`, not `resolved`, and keep both notes retrievable with evidence.
- [Risk] Applying LLM title/summary updates could reduce clarity. → Mitigation: Phase 2 validates length, non-empty content, target action context, and keeps deterministic fields authoritative.
- [Risk] The shared executor may make `_create_or_reinforce_memory_note_row(...)` more complex. → Mitigation: keep executor helper focused and test each action independently.
- [Risk] Live advisor behavior can vary. → Mitigation: deterministic unit tests define the contract; live tests only prove real invocation and bounded outputs.

## Migration Plan

1. Add failing tests for Phase 1 action execution.
2. Implement the executor and route `_create_or_reinforce_memory_note_row(...)` through it.
3. Add failing tests for Phase 2 safe field updates.
4. Implement narrow title/summary field update validation and application.
5. Run existing memory service, memory advisor, content generation, and live smoke tests.

Rollback is straightforward: revert the executor routing and return `_create_or_reinforce_memory_note_row(...)` to its previous update/skip/create behavior.

## Open Questions

- Should `MERGE` primary selection use advisor target order or deterministic salience/evidence ranking? The implementation should pick one and document it in tests.
- Should `FLAG_CONFLICT` lower salience to a fixed ceiling or apply a relative delta? Tests should lock whichever behavior is chosen.
