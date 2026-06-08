## 1. Phase 1 Test-First Coverage

- [x] 1.1 Add failing unit test for `create_new` through the shared memory write path.
- [x] 1.2 Add failing unit test for `update_existing` reinforcing a target note through the shared memory write path.
- [x] 1.3 Add failing unit test for `skip_duplicate` returning a target note without mutation.
- [x] 1.4 Add failing unit test for `keep_both_scoped` creating the incoming note while preserving related targets.
- [x] 1.5 Add failing unit test for `merge` with one target behaving as an update.
- [x] 1.6 Add failing unit test for `merge` with multiple targets resolving duplicates and reinforcing the primary note.
- [x] 1.7 Add failing unit test for `flag_conflict` creating the incoming note and downgrading target notes to `watch`.

## 2. Phase 1 Executor Implementation

- [x] 2.1 Add `apply_memory_integrity_decision(...)` or equivalent internal executor helper.
- [x] 2.2 Route `_create_or_reinforce_memory_note_row(...)` through the executor after `check_memory_write_integrity(...)`.
- [x] 2.3 Implement deterministic execution for `create_new`, `update_existing`, `skip_duplicate`, and `keep_both_scoped`.
- [x] 2.4 Implement deterministic execution for `merge`, including single-target update behavior and multi-target duplicate resolution.
- [x] 2.5 Implement deterministic execution for `flag_conflict`, including conservative target downgrade without deletion.
- [x] 2.6 Ensure all executor paths refresh embeddings/search text when note content changes.
- [x] 2.7 Verify all Phase 1 tests fail before implementation and pass after implementation.

## 3. Phase 2 Test-First Coverage

- [x] 3.1 Add failing unit test for safe advisor `title` and `summary` field updates during merge execution.
- [x] 3.2 Add failing unit test that unsafe advisor field updates are ignored.
- [x] 3.3 Add failing unit test that applied safe field updates refresh retrieval indexes.

## 4. Phase 2 Safe Field Update Implementation

- [x] 4.1 Add safe field-update validation for advisor-provided `title` and `summary`.
- [x] 4.2 Apply validated title/summary updates only to notes selected by the executed integrity action.
- [x] 4.3 Reject advisor updates to identity, ownership, type, status, salience, evidence, embedding, search text, and timestamps.
- [x] 4.4 Keep deterministic service-owned field merging authoritative for tags, concepts, scope, evidence, status, salience, and timestamps.

## 5. Live Advisor Smoke Tests

- [x] 5.1 Add or update live smoke test proving real advisor `update_existing` remains bounded to candidate IDs.
- [x] 5.2 Add live smoke test for real advisor `merge` or `flag_conflict` recommendation with bounded targets and service-owned mutation.
- [x] 5.3 Document expected LangSmith observations for integrity action, advisor usage, target IDs, and DB mutation result.

## 6. Verification

- [x] 6.1 Run focused non-live memory service tests.
- [x] 6.2 Run advisor schema/prompt tests.
- [x] 6.3 Run backend compile check for `app` and relevant tests.
- [x] 6.4 Run gated live LLM memory integration tests when credentials and `RUN_LIVE_AGENT_MEMORY_TESTS=1` are available.
- [x] 6.5 Update memory integrity docs with final action semantics and testing instructions.
