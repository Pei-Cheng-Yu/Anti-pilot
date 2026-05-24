# Add Learning Memory Retrieval Diagnostics

## Summary

Add explicit LangGraph state diagnostics that explain whether learning memory retrieval ran, why it may have been skipped, and how many memory items were retrieved per skillpath.

## Motivation

`learning_memory_contexts_by_skillpath` now makes retrieved memory visible in LangGraph/LangSmith state. However, an empty value is ambiguous:

```json
"learning_memory_contexts_by_skillpath": {}
```

That can mean several different things:

- `user_id` was missing, so retrieval was skipped.
- Retrieval ran but found no relevant notes or attempts.
- Retrieval failed and content generation continued without memory.
- The run was a non-live/fake test state that never seeded memory.

For debugging live traces, developers need to know not only whether memory is present, but also whether the retrieval path executed and what high-level result it produced.

## Goals

- Add an observable state field for memory retrieval diagnostics by skillpath.
- Distinguish `skipped_no_user_id`, `retrieved`, `retrieved_empty`, and `failed` outcomes.
- Include lightweight counts for `recent_attempts`, `active_error_patterns`, `teaching_heuristics`, and `relevant_notes`.
- Keep full memory context available only in `learning_memory_contexts_by_skillpath` when context exists.
- Preserve the current ADK request behavior.
- Update tests so empty memory state is no longer mysterious.

## Non-Goals

- Do not expose full prompts or model responses in diagnostics.
- Do not change retrieval ranking or memory consolidation.
- Do not make ADK call memory retrieval as a tool.
- Do not require live LLM tests for this observability change.

## Success Criteria

- A graph run without `user_id` shows a diagnostic entry for each generated skillpath with `status="skipped_no_user_id"`.
- A graph run with a seeded context shows `status="retrieved"` and counts greater than zero for relevant groups.
- A graph run with an empty retrieved context shows `status="retrieved_empty"`.
- If retrieval raises, the diagnostic records `status="failed"` and a safe error summary while content generation behavior is explicitly defined by implementation.
- Documentation explains how to interpret both `learning_memory_contexts_by_skillpath` and the diagnostics field.
