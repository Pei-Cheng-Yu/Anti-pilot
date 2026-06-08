## Context

Learner memory now supports error patterns, heuristics, mastery signals, background notes, and preference signals. Current consolidation already prevents some duplicate error patterns by matching scope and concept overlap, but the prevention is narrow and does not apply uniformly across all memory types.

As memory becomes shared across hints, content generation, and future roadmap recommendations, duplicate or conflicting notes become more expensive. The system needs a universal integrity layer that prevents avoidable duplicates before writes and provides controlled repair operations for duplicates or conflicts that already exist.

## Goals / Non-Goals

**Goals:**

- Add universal duplicate/conflict prevention across all memory types.
- Find related candidate notes before creating new memory.
- Use deterministic evidence such as type compatibility, concept overlap, scope overlap, tag overlap, semantic similarity, status, recency, and salience.
- Add an optional LLM integrity advisor for semantic duplicate/conflict decisions over a bounded candidate set.
- Keep the memory service as the final authority for DB writes.
- Add explicit merge and conflict-resolution operations.
- Preserve existing active/watch/resolved lifecycle behavior.

**Non-Goals:**

- Do not let the LLM write directly to the database.
- Do not delete learner memory automatically as the default conflict strategy.
- Do not replace existing retrieval or consolidation behavior wholesale.
- Do not introduce broad roadmap adaptation.
- Do not require a trained reranker/model.

## Decisions

### Add A Memory Integrity Service Before Writes

Memory writes should flow through a `memory_integrity` service before creating new notes. The service returns a structured decision such as create new, update existing, merge with existing, skip duplicate, keep both scoped, or flag conflict.

Alternative considered: rely only on individual call sites to deduplicate. This would repeat logic and leave gaps across memory types.

### Use Deterministic Candidate Discovery First

The service first gathers possible related notes using same user, memory type compatibility, concepts, skillpath/content links, tags, embedding similarity, and status. This keeps the LLM advisor bounded and gives deterministic fallback behavior.

Alternative considered: LLM-only integrity decisions. This was rejected because the LLM should advise on a controlled packet, not inspect arbitrary DB state.

### Add Optional LLM Advisor For Semantic Decisions

Some duplicates and conflicts are semantic rather than exact. The optional advisor can decide that two differently worded preference signals express the same preference, or that an active error pattern conflicts with a strong mastery signal.

The advisor returns structured recommendations only. The memory service validates target IDs, allowed actions, fields, confidence, salience bounds, and status transitions before persisting.

### Implement Conservative Conflict Resolution

Conflicts should usually downgrade, watch, or scope notes rather than delete them. For example, a newer mastery signal may move an older error pattern to watch or resolved when supported by evidence.

Alternative considered: automatically prefer the newest note. This is unsafe because older memory may still apply in a narrower scope.

### Provide Explicit Merge Operations

For duplicates that already exist, the service should support merging duplicate notes into a primary note. Merge combines tags, concepts, linked skillpaths/content, evidence attempt IDs, salience, timestamps, search text, and embedding.

Alternative considered: only preventing future duplicates. This leaves existing duplicate state unresolved and makes tests/debugging harder.

## Risks / Trade-offs

- Over-merging distinct memories -> Require evidence thresholds and allow `keep_both_scoped`.
- Under-merging duplicates -> Add semantic advisor and tests for paraphrased duplicates.
- LLM advisor instability -> Validate outputs and fall back to deterministic decisions.
- Conflict resolution hides useful weakness evidence -> Prefer watch/resolved status changes over deletion.
- Added complexity in memory writes -> Keep integrity decisions structured and service-owned.
