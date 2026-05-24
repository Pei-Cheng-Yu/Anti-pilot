# Add Live Graph Memory Smoke and Trace Guards

## Summary

Add a real live LangGraph content-generation smoke test that uses actual memory retrieval plus the real ADK content generator, and prevent deterministic fake graph tests from being confused with live ADK traces in LangSmith.

## Motivation

Current live coverage has two separate pieces:

- `test_live_agent_memory_integration.py` invokes the real ADK content generator directly with a seeded `LearningMemoryContext`.
- `test_learning_content_generation.py` invokes the real LangGraph content-generation graph but monkeypatches the content generator and memory retrieval for deterministic tests.

This makes debugging confusing in LangSmith. A trace can show:

```json
"reading_content": "Core explanation with a small worked example."
"error_summary": "RuntimeError: memory database unavailable"
```

Those are fake-test literals, not live ADK behavior. Even when `RUN_LIVE_AGENT_MEMORY_TESTS=1` and `GOOGLE_API_KEY` are set, a trace from `test_learning_content_generation.py` does not prove real ADK invocation.

We need a smoke path that proves the full route:

```text
LangGraph state with user_id
        ↓
real DB-backed retrieve_learning_memory
        ↓
learning_memory_contexts_by_skillpath
        ↓
AdkContentGenerationRequest.learning_memory_context
        ↓
real ADK content generator
```

## Goals

- Add a gated live LangGraph smoke test that invokes `build_learning_content_graph()` without monkeypatching `generate_skillpath_content`.
- Seed or ensure real learner memory exists in the database before graph invocation.
- Use a real `user_id`, skillpath ID, and memory note that retrieval should match.
- Assert diagnostics show `retrieved`, not `failed` or `retrieved_empty`.
- Assert `learning_memory_contexts_by_skillpath` includes the seeded memory note for the relevant skillpath.
- Assert generated content is not the deterministic fake placeholder text.
- Make non-live fake graph tests easy to distinguish from live traces.

## Non-Goals

- Do not make live LLM calls part of default unit test runs.
- Do not remove deterministic fake tests.
- Do not change retrieval ranking or memory schema.
- Do not require LangSmith for the test to pass; LangSmith is an inspection aid.

## Success Criteria

- Running
  `RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s`
  includes a live graph test.
- The live graph test produces real ADK-generated content instead of `"Short article for the skill path."`.
- The final graph state includes `learning_memory_retrieval_diagnostics_by_skillpath[skillpath_id].status == "retrieved"`.
- The final graph state includes `learning_memory_contexts_by_skillpath[skillpath_id]` with the seeded FastAPI async/await memory note.
- Documentation explains how to tell fake deterministic traces from live ADK traces.
