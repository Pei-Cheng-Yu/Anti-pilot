# Design

## Diagnosis

The pasted trace is not a live ADK graph run. It contains two literals from deterministic tests:

- `"Short article for the skill path."` comes from `_fake_generate_skillpath_content` in `tests/test_learning_content_generation.py`.
- `"RuntimeError: memory database unavailable"` comes from the fake failed-retrieval test in the same file.

So the trace proves that diagnostics work, but it does not prove real ADK invocation.

## Target Live Test

Extend `tests/test_live_agent_memory_integration.py` with a third live test:

```text
test_live_learning_content_graph_retrieves_memory_and_invokes_adk
```

The test should:

1. Skip unless `RUN_LIVE_AGENT_MEMORY_TESTS=1` and Google/Gemini credentials exist.
2. Create a test user, roadmap, milestone, and skillpath in the real test database.
3. Seed a FastAPI async/await `ERROR_PATTERN` note and a teaching `HEURISTIC` note for that user and skillpath.
4. Build a LangGraph state with the same `user_id`, milestone, and skillpath.
5. Invoke `build_learning_content_graph()` without monkeypatching `generate_skillpath_content` or `_retrieve_learning_memory_context`.
6. Print:
   - `learning_memory_retrieval_diagnostics_by_skillpath`
   - `learning_memory_contexts_by_skillpath`
   - generated article/problem snippets
7. Assert:
   - diagnostics status for the target skillpath is `retrieved`
   - memory context includes the seeded note
   - generated content validates through normal graph conversion
   - generated content is not the fake placeholder text
   - generated content mentions `await`, `async`, or route-handler pitfalls

## Database Setup

Reuse the same DB setup patterns as the existing DB-backed tests:

- create a unique test user ID
- create minimal roadmap/milestone/skillpath rows
- add memory notes using `learning_memory.add_memory_note`
- clean up rows in `finally`

The live graph test should not rely on hardcoded `user-1` unless that user exists and is intentionally seeded.

## Trace Guards

Non-live tests should remain deterministic, but they should be clearly identifiable:

- Rename fake test helper text or add comments/docstrings making it clear that `"Short article for the skill path."` is a fake generator marker.
- Optionally set or document a LangSmith project/run-name convention for fake tests, such as `unit-fake-content-generation`.
- Keep live tests under `pytest.mark.live_llm` and document that only the live graph test proves real end-to-end graph + retrieval + ADK behavior.

## What LangSmith Should Show

For the live graph smoke, LangSmith should show:

- a graph invocation with top-level `user_id`
- `learning_memory_retrieval_diagnostics_by_skillpath`
- status `retrieved` for the target skillpath
- non-empty `learning_memory_contexts_by_skillpath[target_skillpath_id]`
- a real ADK/model call if ADK tracing is connected

Google Search tool visibility still depends on ADK/LangSmith integration. If Search does not appear as a tool event, the generated content and ADK runtime logs still prove the content agent ran.

## Error Handling

If live graph retrieval returns `retrieved_empty`, the failure message should print the seeded user ID, skillpath ID, and memory note IDs so the DB/retrieval issue can be diagnosed.

If generated content contains the fake placeholder text, fail with a message explaining that the fake graph test path was invoked instead of live ADK.
