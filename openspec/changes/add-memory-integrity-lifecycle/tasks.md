## 1. Schemas And Contracts

- [x] 1.1 Add schemas for integrity evidence, integrity actions, integrity decisions, and advisor recommendations.
- [x] 1.2 Add schemas for merge requests/results and conflict-resolution requests/results.
- [x] 1.3 Define allowed actions: create new, update existing, merge, skip duplicate, keep both scoped, and flag conflict.
- [x] 1.4 Add validation so advisor target IDs must come from the candidate set.

## 2. Deterministic Integrity Service

- [x] 2.1 Add `memory_integrity` service module for pre-write checks.
- [x] 2.2 Implement candidate discovery across all memory types using user, type compatibility, concepts, tags, scope links, status, salience, and semantic similarity.
- [x] 2.3 Implement deterministic decisions for obvious duplicates across error patterns, heuristics, mastery signals, background notes, and preference signals.
- [x] 2.4 Add tests for duplicate prevention across all five memory types.

## 3. LLM Integrity Advisor

- [x] 3.1 Add optional LLM advisor interface that receives incoming memory, candidate memories, deterministic evidence, and allowed actions.
- [x] 3.2 Validate advisor output before applying decisions.
- [x] 3.3 Add fallback behavior when advisor output is invalid, unavailable, or below confidence threshold.
- [x] 3.4 Add tests for advisor merge recommendation, advisor conflict recommendation, invalid schema fallback, and unknown target ID rejection.

## 4. Merge And Conflict Resolution

- [x] 4.1 Implement explicit `merge_memory_notes` service operation that preserves combined tags, concepts, scope links, evidence IDs, salience, timestamps, search text, and embedding.
- [x] 4.2 Implement conservative conflict resolution for mastery-signal vs error-pattern conflicts.
- [x] 4.3 Implement conservative conflict resolution for preference-signal conflicts.
- [x] 4.4 Add tests for merge preservation, watch/resolved conflict handling, and non-destructive behavior.

## 5. Integrate With Existing Memory Lifecycle

- [x] 5.1 Run pre-write integrity checks inside `add_memory_note`.
- [x] 5.2 Run pre-write integrity checks for consolidation-created error patterns, heuristics, and mastery signals.
- [x] 5.3 Preserve current active/watch/resolved lifecycle semantics.
- [x] 5.4 Ensure resolved notes remain excluded from normal retrieval unless explicitly included.

## 6. Verification And Documentation

- [x] 6.1 Run learning memory service and retriever tests.
- [x] 6.2 Add regression tests for existing repeated-failure and correct-recovery lifecycle cases.
- [x] 6.3 Document prevention-first integrity flow and advisor guardrails in backend memory docs.
- [x] 6.4 Verify no LLM advisor path writes directly to the database.
