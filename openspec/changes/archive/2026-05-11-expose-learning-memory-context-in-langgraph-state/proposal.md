# Expose Learning Memory Context in LangGraph State

## Summary

Make retrieved learner memory visible in the content-generation LangGraph state so LangSmith and graph-state inspection can show which memory contexts were retrieved and passed to the ADK content generator.

## Motivation

The current content-generation flow retrieves learner memory inside `content_worker` and injects it directly into `AdkContentGenerationRequest.learning_memory_context`. That is behaviorally useful, but it is hard to observe:

- LangGraph state only shows inputs such as `user_id`, skillpaths, and generated content.
- LangSmith may show the content worker and model call, but not the actual `LearningMemoryContext`.
- Debugging whether memory was retrieved requires inspecting the ADK request or final prompt.
- Live agent runs can look suspiciously fast or opaque because memory retrieval is not a visible state transition.

We need first-class state-level observability for the memory payload used by each generated skillpath.

## Goals

- Add a state field keyed by `skillpath_id`, such as `learning_memory_contexts_by_skillpath`.
- Store each retrieved `LearningMemoryContext` in that field during content generation.
- Keep `AdkContentGenerationRequest.learning_memory_context` as the actual agent input.
- Make LangGraph/LangSmith inspection show memory context IDs, grouped notes, and recent attempts without needing to inspect ADK internals.
- Add tests proving the state contains the same memory context that is injected into the ADK request.
- Preserve current behavior when `user_id` is absent or no memory is retrieved.

## Non-Goals

- Do not move retrieval into the ADK agent as a tool call.
- Do not change retrieval ranking, pgvector query behavior, or memory consolidation.
- Do not require live LLM calls in normal tests.
- Do not expose private learner memory outside backend traces/state used by developers.

## Success Criteria

- `ContentGenerationState` includes `learning_memory_contexts_by_skillpath`.
- `content_worker` returns both `content_drafts` and a state update for the retrieved memory context.
- The ADK request still receives `learning_memory_context`.
- A graph-level test can inspect the final state and find memory under the generated skillpath ID.
- A request-capture test proves the state context and ADK request context match.
- Documentation explains which state field to inspect in LangSmith/LangGraph.
