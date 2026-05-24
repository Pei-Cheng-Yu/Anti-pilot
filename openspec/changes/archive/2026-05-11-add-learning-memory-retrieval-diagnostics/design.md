# Design

## Current State

Content generation now exposes retrieved memory in:

```python
state["learning_memory_contexts_by_skillpath"]
```

This proves memory is visible when it exists. But an empty dict does not explain why memory is absent. In the pasted trace, the graph state has no top-level `user_id`, so `_retrieve_learning_memory_context` returns `None` before querying the database. That makes the observed empty dict expected, but not self-explanatory in LangSmith.

## Target State

Add a second state field:

```python
state["learning_memory_retrieval_diagnostics_by_skillpath"]
```

Each worker returns one diagnostic entry keyed by `skillpath_id`.

Example when `user_id` is missing:

```json
{
  "sp-2": {
    "status": "skipped_no_user_id",
    "skillpath_id": "sp-2",
    "user_id_present": false,
    "active_error_pattern_count": 0,
    "teaching_heuristic_count": 0,
    "recent_attempt_count": 0,
    "relevant_note_count": 0
  }
}
```

Example when memory is retrieved:

```json
{
  "sp-fastapi-routing": {
    "status": "retrieved",
    "skillpath_id": "sp-fastapi-routing",
    "user_id_present": true,
    "active_error_pattern_count": 1,
    "teaching_heuristic_count": 1,
    "recent_attempt_count": 2,
    "relevant_note_count": 3
  }
}
```

## Data Shape

Use a small Pydantic model or typed dict near the content-generation state schema:

```python
class LearningMemoryRetrievalDiagnostic(BaseModel):
    skillpath_id: str
    status: Literal[
        "skipped_no_user_id",
        "retrieved",
        "retrieved_empty",
        "failed",
    ]
    user_id_present: bool
    active_error_pattern_count: int = 0
    teaching_heuristic_count: int = 0
    recent_attempt_count: int = 0
    relevant_note_count: int = 0
    error_summary: str | None = None
```

The state field should use a merge reducer like the memory-context map:

```python
learning_memory_retrieval_diagnostics_by_skillpath: Annotated[
    dict[str, LearningMemoryRetrievalDiagnostic],
    merge_learning_memory_retrieval_diagnostics,
]
```

## Worker Behavior

`content_worker` should produce diagnostics for every generated skillpath:

- If `user_id` is missing: do not call retrieval; return `skipped_no_user_id`.
- If retrieval returns `None`: return `retrieved_empty` or a more precise status if available.
- If retrieval returns a context with any notes or attempts: return `retrieved`.
- If retrieval returns a context with no notes, no attempts, and no mastery state: return `retrieved_empty`.
- If retrieval raises and content generation should continue: return `failed` with a short safe `error_summary`.

The existing memory state field should remain sparse:

- Store a full `LearningMemoryContext` only when retrieval returns a non-`None` context.
- Keep diagnostics separate so empty/skipped states are still observable without storing misleading empty contexts.

## Testing Strategy

Add deterministic graph tests:

- No `user_id`: final state has empty `learning_memory_contexts_by_skillpath`, but diagnostics show `skipped_no_user_id` for each generated skillpath.
- Seeded context: diagnostics show `retrieved` with nonzero counts, and the full context appears in `learning_memory_contexts_by_skillpath`.
- Empty context: diagnostics show `retrieved_empty`.

These tests should use monkeypatching for `_retrieve_learning_memory_context` and `generate_skillpath_content`; no live agent call is needed.

## Documentation

Update verification notes:

- `learning_memory_contexts_by_skillpath` answers: "What memory was retrieved and injected?"
- `learning_memory_retrieval_diagnostics_by_skillpath` answers: "Did retrieval run, and why is memory empty?"

For LangSmith, inspect diagnostics first. If `status="retrieved"`, inspect the full memory context. If `status="skipped_no_user_id"`, fix the graph input state so `user_id` is present.
