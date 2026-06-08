## Context

The backend already records coding attempts, consolidates learner memory, retrieves `LearningMemoryContext`, and injects memory into content generation. Code correction returns compact feedback and persistence results, but there is no dedicated hint service that can generate progressive, memory-aware hints for a learner who is stuck.

The current retriever also performs deterministic reranking over hybrid candidates. That is useful for relevance, but it does not yet answer the pedagogical question: "Which memories should shape this specific hint or generated content, and how?"

## Goals / Non-Goals

**Goals:**

- Add a structured hint service that can produce learner-facing hints from task/code context.
- Use retrieved memory to shape hint focus, hint level, and teaching style.
- Add an optional LLM rerank policy that selects useful memories from a bounded candidate set.
- Support purpose-specific guidance for `hint_generation`, `code_correction`, and `content_generation`.
- Keep output structured and testable with Pydantic schemas.
- Provide deterministic fallback when the LLM reranker is unavailable or invalid.

**Non-Goals:**

- Do not let the reranker create, update, or delete memory.
- Do not modify roadmap structure or skillpath order.
- Do not implement predictive forgetting.
- Do not replace the existing pgvector/full-text/scope candidate retrieval.
- Do not train a learned model in this change.

## Decisions

### Keep Retrieval And Pedagogical Rerank Separate

The existing hybrid retriever remains responsible for finding candidate notes. The new rerank policy receives a small candidate set and decides which memories are pedagogically useful for the caller's purpose.

Alternative considered: ask the LLM to search all learner memory. This was rejected because it is slower, less testable, and bypasses the database retrieval controls.

### Use One Shared Rerank Envelope With Purpose-Specific Guidance

The rerank request will include `purpose`, `task_context`, `learner_context`, `recent_attempts`, and `candidate_memories`. The result will always include selected memories and reasons, plus optional guidance for hints, content, or correction.

Alternative considered: build separate rerank services for hints, content, and correction. This would duplicate memory-selection logic and make behavior harder to compare across callers.

### Make Hints Progressive And Low-Spoiler By Default

Hint generation should support levels such as nudge, conceptual, specific, and near-solution. Default hints should guide the learner without revealing corrected code immediately.

Alternative considered: return one generic feedback paragraph. This would not support gradual help or memory-aware tutoring.

### Keep The LLM Reranker Advisory

The LLM reranker may select memory IDs and suggest teaching actions, but it cannot write memory or change DB state. The caller validates selected IDs against candidate IDs and falls back to deterministic ranking when needed.

Alternative considered: allow the LLM reranker to trigger memory updates. This belongs in memory integrity/lifecycle work, not hint/content guidance.

## Risks / Trade-offs

- LLM reranker selects irrelevant memories -> Validate IDs, constrain schema, and test fixture cases with expected selections.
- Hints reveal too much -> Add hint levels and enforce low-spoiler defaults in schemas and tests.
- Extra LLM call adds latency -> Keep rerank optional and bounded to top candidates.
- Different callers need different output -> Use purpose-specific guidance fields under one shared result schema.
- Non-live tests cannot rely on real LLM behavior -> Provide deterministic fake reranker/advisor fixtures.
