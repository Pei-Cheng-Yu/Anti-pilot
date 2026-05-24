# Tasks

## 1. Identify the Product Boundary

- [x] Find the backend route or service the app uses when a learner submits a coding-problem attempt.
- [x] Confirm whether that path invokes validation, correction, attempt persistence, and memory consolidation.
- [x] Confirm current MCP boundary: `code_correction.process_code_correction`.
- [x] Confirm whether a learner-submission HTTP endpoint exists under `backend/app`.
- [x] If no API route covers the full path, document MCP/service as the current product boundary and the missing HTTP/API integration.

## 2. Add Product-Path Bad Attempt Verification

- [x] Create a gated live/integration test or script for the product-shaped flow.
- [x] Prefer invoking MCP `code_correction.process_code_correction`; use an HTTP route only if one exists or is added.
- [x] Seed only the minimum user, roadmap, milestone, skillpath, and coding content needed by the app path.
- [x] Submit a bad FastAPI async route-handler solution with runtime/test evidence showing a missing `await` or coroutine misuse.
- [x] Assert a `CodingProblemAttempt` row is created.
- [x] Assert at least one active `LearnerMemoryNote` is created or updated for the same user.
- [x] Assert the note captures an `ERROR_PATTERN` related to async/await or route-handler mistakes.

## 3. Verify Same-User Content Generation Uses Created Memory

- [x] Run learning-content generation for the same user and related skillpath after the bad attempt.
- [x] Assert `learning_memory_retrieval_diagnostics_by_skillpath[target_skillpath_id].status == "retrieved"`.
- [x] Assert `learning_memory_contexts_by_skillpath[target_skillpath_id]` includes the created memory note.
- [x] Assert generated content is not the fake marker `"Short article for the skill path."`.
- [x] Assert generated content mentions the remembered mistake theme, such as `await`, `async`, coroutine, or FastAPI route handlers.

## 4. LangSmith and Debug Output

- [x] Print redacted attempt, memory, retrieval diagnostic, and generated-content snippets under clear headings.
- [x] Document the exact LangSmith state fields to inspect.
- [x] Document how to distinguish seeded-memory tests from this product-path test.

## 5. Verification Commands

- [x] Run the focused non-live suite:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_deepagent_validator.py tests/test_content_generator_agent.py tests/test_code_correction_service.py tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py tests/test_learning_content_generation.py -q`
- [x] Run compile verification:
  `PYTHONPATH=. ../venv/bin/python -m compileall -q app tests`
- [x] Run the gated product-path/live command:
  `RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s`
- [x] Record live environment requirements and observed LangSmith fields in final notes.
