# Design

## Current Flow

The content-generation graph currently routes memory like this:

```text
ContentGenerationState.user_id
        ↓
content_worker
        ↓
_retrieve_learning_memory_context(user_id, skillpath)
        ↓
AdkContentGenerationRequest.learning_memory_context
        ↓
build_content_generation_prompt(...)
        ↓
ADK content_generator agent
```

This means memory influences the agent, but it is not stored in a named LangGraph state field. In LangSmith, developers may only see `user_id`, selected skillpath data, content drafts, and generated skillpaths.

## Target Flow

Add state-level observability while keeping the ADK request path unchanged:

```text
ContentGenerationState.user_id
        ↓
content_worker
        ↓
_retrieve_learning_memory_context(user_id, skillpath)
        ↓
learning_memory_contexts_by_skillpath[skillpath_id]
        ↓
AdkContentGenerationRequest.learning_memory_context
        ↓
ADK content_generator agent
```

## State Shape

Add this field to `ContentGenerationState`:

```python
learning_memory_contexts_by_skillpath: Annotated[
    dict[str, LearningMemoryContext],
    merge_learning_memory_contexts,
]
```

Use a merge reducer because multiple `content_worker` nodes can run through LangGraph `Send` fanout. Each worker should return a one-entry dict:

```python
{
    "learning_memory_contexts_by_skillpath": {
        skillpath.skillpath_id: memory_context
    }
}
```

The reducer should merge dicts by key. If the same skillpath appears twice, the later value can replace the earlier value because each worker should own one skillpath generation attempt.

## Worker Behavior

`content_worker` should retrieve memory once and reuse the same object for both:

- `AdkContentGenerationRequest.learning_memory_context`
- `learning_memory_contexts_by_skillpath[skillpath_id]`

This avoids drift where the observable state and the actual prompt input disagree.

If `user_id` is missing, `_retrieve_learning_memory_context` returns `None`. In that case the worker should either omit the state update or store no entry for that skillpath. The state field should still exist safely as an empty dict when initialized.

## LangSmith Inspection

After implementation, inspect:

```python
state["learning_memory_contexts_by_skillpath"]
```

For a specific skillpath:

```python
state["learning_memory_contexts_by_skillpath"][skillpath_id]
```

Important subfields:

- `recent_attempts`
- `active_error_patterns`
- `teaching_heuristics`
- `relevant_notes`
- `mastery_state`

For a FastAPI async missing-await scenario, the main expected signal is:

```python
state["learning_memory_contexts_by_skillpath"]["sp-fastapi-routing"].active_error_patterns
```

## Testing Strategy

Add deterministic graph tests, not live LLM tests:

- Monkeypatch `_retrieve_learning_memory_context` to return a seeded `LearningMemoryContext`.
- Monkeypatch `generate_skillpath_content` to capture `AdkContentGenerationRequest`.
- Invoke the graph with `state["user_id"]`.
- Assert final graph state includes `learning_memory_contexts_by_skillpath`.
- Assert the stored context contains the seeded FastAPI missing-await memory.
- Assert the captured ADK request receives the same context object or equivalent payload.
- Assert no memory state entry is added when `user_id` is absent.

Live ADK smoke tests remain optional and do not need to prove the state reducer.

## Error Handling

- Retrieval failure behavior should remain consistent with the existing code path unless implementation reveals current failures are unhandled.
- If a retrieval call returns `None`, the worker should continue content generation without memory and avoid adding an empty misleading context entry.
- If multiple workers return memory context dictionaries, reducer merge must not drop previously completed worker contexts.

## Privacy and Trace Hygiene

This change intentionally makes learner memory more visible in graph state and tracing. That improves debugging but can expose personal learning history in LangSmith. Keep this field backend-only and avoid forwarding it to client-facing API responses unless explicitly designed later.
