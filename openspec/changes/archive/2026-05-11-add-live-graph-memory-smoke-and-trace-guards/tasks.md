# Tasks

## 1. Live Graph Smoke

- [x] Add `test_live_learning_content_graph_retrieves_memory_and_invokes_adk` to `tests/test_live_agent_memory_integration.py`.
- [x] Gate it with `RUN_LIVE_AGENT_MEMORY_TESTS=1` and Google/Gemini credentials.
- [x] Seed a real DB user, roadmap, milestone, skillpath, `ERROR_PATTERN`, and `HEURISTIC`.
- [x] Invoke `build_learning_content_graph()` without monkeypatching the content generator or memory retrieval.
- [x] Print diagnostics, memory context, and generated content snippets.

## 2. Assertions

- [x] Assert `learning_memory_retrieval_diagnostics_by_skillpath[target_skillpath_id].status == "retrieved"`.
- [x] Assert `learning_memory_contexts_by_skillpath[target_skillpath_id]` includes the seeded memory note.
- [x] Assert generated content is not the fake placeholder text `"Short article for the skill path."`.
- [x] Assert generated content mentions the seeded memory theme, such as `await`, `async`, or route-handler pitfalls.

## 3. Trace Clarity

- [x] Add comments or docs identifying `_fake_generate_skillpath_content` output as fake deterministic test output.
- [x] Update verification docs to explain that traces containing `"memory database unavailable"` come from the fake failure test.
- [x] Document that direct ADK live tests prove ADK invocation, while the new live graph test proves graph + retrieval + ADK together.

## 4. Verification

- [x] Run default non-live content tests:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py tests/test_content_generator_agent.py -q`
- [x] Run compile verification:
  `PYTHONPATH=. ../venv/bin/python -m compileall -q app tests`
- [x] Optional manual live command:
  `RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s`
