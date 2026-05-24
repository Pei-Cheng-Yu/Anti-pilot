# Memory Retrieval Agent Integration Verification

Run these commands from WSL so the backend uses the project virtualenv:

```bash
cd /mnt/c/Users/seans/anti-pilot/Anti-pilot/backend
PYTHONPATH=. ../venv/bin/alembic current
PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py -q
PYTHONPATH=. ../venv/bin/python -m pytest tests/test_code_correction_service.py -q
PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py tests/test_content_generator_agent.py -q
PYTHONPATH=. ../venv/bin/python -m pytest tests/test_deepagent_validator.py tests/test_content_generator_agent.py tests/test_code_correction_service.py tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py tests/test_learning_content_generation.py -q
PYTHONPATH=. ../venv/bin/python -m compileall -q app tests
```

LangGraph/LangSmith memory inspection:

```python
state["learning_memory_retrieval_diagnostics_by_skillpath"]
state["learning_memory_contexts_by_skillpath"]
state["learning_memory_contexts_by_skillpath"][skillpath_id]
```

Use `learning_memory_retrieval_diagnostics_by_skillpath` first. It answers
whether retrieval ran and why memory may be empty:

- `skipped_no_user_id`: the graph input had no top-level `user_id`, so retrieval
  did not query memory.
- `retrieved_empty`: retrieval ran, but returned no notes, attempts, or mastery
  state for that skillpath.
- `retrieved`: retrieval found context. Inspect
  `learning_memory_contexts_by_skillpath[skillpath_id]` next.
- `failed`: retrieval raised an error and content generation continued without
  memory; inspect `error_summary`.

The most useful fields inside each `LearningMemoryContext` are
`active_error_patterns`, `teaching_heuristics`, `recent_attempts`, and
`relevant_notes`. For the FastAPI async/await scenario, check that the generated
skillpath has an `active_error_patterns` note for the missing-await mistake.

The ADK content generator still receives memory through
`AdkContentGenerationRequest.learning_memory_context`; the state field is the
observable copy used for graph tracing and debugging.

Trace sanity checks:

- If generated content contains `Short article for the skill path.`,
  `Core explanation with a small worked example.`, or options named only
  `Option A` / `Option B` / `Option C`, that trace came from the deterministic
  fake graph tests, not live ADK.
- If diagnostics contain `RuntimeError: memory database unavailable`, that trace
  came from the fake retrieval-failure test.
- The direct live ADK test proves ADK invocation with a seeded request. The live
  graph smoke proves the full route: LangGraph state, DB-backed memory
  retrieval, state visibility, and real ADK generation.

Optional live smoke tests:

```bash
cd /mnt/c/Users/seans/anti-pilot/Anti-pilot/backend
RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s
```

Live tests require Google/Gemini credentials in the environment, such as
`GOOGLE_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_GENAI_API_KEY`. The live content
test prints the seeded `LearningMemoryContext` before invoking ADK, then checks
that generated content validates and mentions the seeded FastAPI async/await
theme. The live validator test checks that runtime/test evidence survives into
the structured validation result.
