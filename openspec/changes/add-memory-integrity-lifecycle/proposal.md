## Why

Learner memory now supports multiple note types and lifecycle states, but duplicate and conflicting memories can still accumulate as the system grows. This change adds a universal memory integrity layer that prevents duplicate/conflicting notes before writes, while also providing controlled merge and conflict-resolution paths for cases that already exist.

## What Changes

- Add a universal memory integrity service that runs before learner memory writes across all memory types.
- Support all current memory types: error patterns, mastery signals, teaching heuristics, background notes, and preference signals.
- Use deterministic candidate discovery and evidence scoring to find likely duplicates or conflicts before creating new notes.
- Add an optional LLM integrity advisor that makes semantic duplicate/conflict recommendations over a controlled candidate set.
- Keep the service as the only authority that validates, clamps, and persists memory changes.
- Add explicit merge and conflict-resolution operations for existing duplicate or contradictory notes.
- Add conservative fallback behavior when the LLM advisor is unavailable or returns invalid output.
- Preserve the existing memory lifecycle behavior for active, watch, and resolved states while adding stronger integrity checks.

## Capabilities

### New Capabilities

- `memory-integrity-lifecycle`: Prevent duplicate/conflicting memory writes, merge related notes, and resolve memory conflicts with deterministic and optional LLM-advised decisions.

### Modified Capabilities

None.

## Impact

- Adds schemas for memory integrity decisions, candidate evidence, merge requests/results, and conflict decisions.
- Adds service logic before `add_memory_note` and consolidation-created note writes.
- Updates learner memory consolidation to use integrity checks before creating or updating notes.
- Adds optional LLM advisor for semantic duplicate/conflict decisions with strict validation and deterministic fallback.
- Adds tests for duplicate prevention across all memory types, merge behavior, conflict handling, advisor fallback, and lifecycle preservation.
