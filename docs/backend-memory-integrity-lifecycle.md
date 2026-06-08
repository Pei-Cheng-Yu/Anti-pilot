# Backend Memory Integrity Lifecycle

Learner memory writes use a prevention-first integrity flow. Before creating a
new `LearnerMemoryNote`, the memory service asks the integrity layer to compare
the incoming note with existing active or watched notes for the same user.

## What The Integrity Layer Checks

The integrity service builds deterministic evidence for each candidate note:

- memory type compatibility
- linked concept overlap
- tag overlap
- skillpath and content scope overlap
- embedding cosine similarity
- candidate status and salience

For evidence-backed writes, obvious duplicates are reinforced instead of
creating a new row. Reinforcement preserves the existing memory ID, unions tags,
concepts, skillpath IDs, content IDs, and evidence attempt IDs, keeps the higher
salience score, and refreshes search text and embedding data.

All writes flow through a shared executor after the integrity decision is made:

- `create_new` creates a new memory note.
- `update_existing` reinforces the selected target note.
- `skip_duplicate` returns the selected target note without mutation.
- `keep_both_scoped` creates the incoming note and leaves related targets
  unchanged.
- `merge` with one target behaves like an update; `merge` with multiple targets
  merges duplicate existing notes into the first target, marks duplicate targets
  `resolved`, and reinforces the primary with incoming evidence.
- `flag_conflict` creates the incoming note, marks target notes `watch`, lowers
  target salience conservatively, and keeps both sides available for retrieval.

Resolved notes remain excluded from normal duplicate checks and retrieval unless
a caller explicitly asks to include them.

## Advisor-First Guardrails

When `ENABLE_MEMORY_INTEGRITY_ADVISOR` is enabled and model credentials are
present, ambiguous duplicate or conflict candidate sets can invoke the real
DeepAgent-backed integrity advisor. The advisor is advisory only. It receives the
incoming memory, bounded candidate memories, deterministic evidence, and allowed
actions:

- `create_new`
- `update_existing`
- `merge`
- `skip_duplicate`
- `keep_both_scoped`
- `flag_conflict`

The advisor never writes to the database. The service validates its output before
using it. Invalid schemas, unknown target IDs, unsupported actions, unavailable
credentials, disabled advisor flags, or low confidence recommendations fall back
to deterministic behavior.

Advisor `field_updates` are bounded. The executor may apply validated non-empty
`title` and `summary` strings, then refresh retrieval indexes. Identity,
ownership, memory type, status, salience, evidence IDs, embeddings, search text,
and timestamps remain service-owned and are ignored if an advisor suggests them.

## Configuration

Advisor execution is controlled by environment flags:

- `ENABLE_MEMORY_INTEGRITY_ADVISOR=1` enables the integrity advisor.
- `MEMORY_ADVISOR_MODEL` defaults to `google_genai:gemini-3.1-flash-lite-preview`.

The service still requires at least one model credential environment variable:
`GOOGLE_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_GENAI_API_KEY`. Without this flag
and credentials, deterministic integrity behavior remains the local development
and non-live test path.

## Merge And Conflict Repair

Existing duplicate notes can be repaired with `merge_memory_notes`. The primary
note keeps combined tags, concepts, scope links, evidence IDs, the highest
salience score, and refreshed search metadata. Duplicate notes are preserved but
moved to `resolved`.

Conflicts are handled conservatively. A mastery signal can downgrade an older
error pattern to `watch`, and a stronger preference signal can downgrade a
conflicting preference signal to `watch`. The service avoids destructive deletion
as the default repair strategy.

The shared write path now also applies merge and conflict decisions when they are
returned by the integrity layer. Manual repair helpers remain useful for future
maintenance scans or operator-driven cleanup.

## Testing And LangSmith Checks

Focused non-live tests cover each action through the shared memory write path:

- create
- update
- skip duplicate
- keep both scoped
- merge one target
- merge multiple targets
- flag conflict
- safe title/summary field updates
- unsafe field-update rejection

Live smoke tests should be run only with `RUN_LIVE_AGENT_MEMORY_TESTS=1`,
credentials, and the relevant advisor flag enabled. In LangSmith or pytest
output, check:

- `advisor_used=true`
- the returned `action`
- `target_memory_ids` are limited to service-provided candidates
- unsafe `field_updates` do not override service-owned fields
- DB state matches the executor action, such as duplicate rows moving to
  `resolved` or conflicting targets moving to `watch`
