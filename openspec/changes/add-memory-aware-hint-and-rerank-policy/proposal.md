## Why

Learner memory is already recorded, retrieved, and injected into content generation, but the product still lacks a dedicated memory-aware hint path and a policy layer that decides how retrieved memory should shape learner-facing guidance. This change adds a controlled hint and rerank policy so memory can improve the immediate learner experience without changing roadmap structure yet.

## What Changes

- Add a memory-aware hint generation capability that accepts learner/task/code context and returns structured hints without revealing full solutions by default.
- Add an optional LLM memory reranker/advisor over the existing hybrid-retrieved candidate memory set.
- Keep the current deterministic retriever as the candidate source; the LLM reranker only selects and explains pedagogically useful memories from candidates.
- Add structured teaching actions such as normal hint, quick recap, contrast example, and quick recap then practice.
- Allow content generation and hint generation to consume rerank decisions, selected memory IDs, and teaching guidance.
- Do not let the reranker write learner memory or modify roadmaps.
- Do not implement broad roadmap adaptation in this change.

## Capabilities

### New Capabilities

- `memory-aware-hints`: Generate structured learner hints from task/code context and `LearningMemoryContext`.
- `memory-rerank-policy`: Select pedagogically useful memories from hybrid-retrieved candidates and return purpose-specific guidance.

### Modified Capabilities

None.

## Impact

- Adds schemas for hint requests/responses and memory rerank requests/results.
- Adds service logic for memory-aware hint generation.
- Adds optional LLM-backed rerank advisor with deterministic fallback.
- Updates content-generation and/or hint flows to consume selected memories and teaching actions.
- Adds tests for hint behavior, rerank selection, invalid rerank fallback, and memory-specific quick recap/contrast guidance.
