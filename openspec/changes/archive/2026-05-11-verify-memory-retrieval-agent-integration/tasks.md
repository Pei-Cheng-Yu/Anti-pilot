# Tasks

## 1. Retrieval Quality Coverage

- [x] Add a DB-backed test that seeds related, nearby, unrelated, and resolved learner memory notes.
- [x] Query `"fastapi async await route"` with FastAPI async concept keys.
- [x] Assert the FastAPI async error note ranks first in `relevant_notes`.
- [x] Assert resolved notes are excluded.
- [x] Assert grouped context includes `active_error_patterns`.
- [x] Run:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py -q`

## 2. Consolidation Lifecycle Coverage

- [x] Add or strengthen a test for two repeated failed coding attempts.
- [x] Assert consolidation creates or updates an `ERROR_PATTERN`.
- [x] Assert repeated evidence creates a `HEURISTIC`.
- [x] Assert `retrieve_learning_memory` returns `recent_attempts`, `active_error_patterns`, `teaching_heuristics`, and `relevant_notes`.
- [x] Run:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_memory_service.py -q`

## 3. Correction Flow Integration Smoke

- [x] Add a correction smoke test or helper that simulates VS Code supplied runtime/test evidence.
- [x] Call `process_code_correction`.
- [x] Assert a `coding_problem_attempts` row is persisted.
- [x] Assert `learner_memory_notes` gets or updates an `ERROR_PATTERN`.
- [x] Assert a later `retrieve_learning_memory` call returns that note.
- [x] Run:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_code_correction_service.py -q`

## 4. Content Generator Memory Inspection

- [x] Add a non-live test that seeds learner memory and captures the `AdkContentGenerationRequest`.
- [x] Assert `learning_memory_context` is present and contains the seeded memory.
- [x] Assert `build_content_generation_prompt` includes a `Learner memory context` section.
- [x] Run:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py tests/test_content_generator_agent.py -q`

## 5. Live Content Generation Smoke

- [x] Add a live smoke script or `pytest.mark.live_llm` test for real ADK content generation after seeded memory exists.
- [x] Skip unless credentials and an explicit live flag are present.
- [x] Print the seeded `LearningMemoryContext` before invoking ADK.
- [x] Assert generation completes and output validates as `AdkContentGenerationOutput`.
- [x] Add a weak behavioral assertion that generated article/problem mentions the seeded memory theme, such as `await`, `async`, or route-handler pitfalls.
- [x] Manual command:
  `PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q`

## 6. Live Validator Smoke

- [x] Add a live smoke test for `validate_code_submission` with external runtime evidence.
- [x] Skip unless model credentials and an explicit live flag are present.
- [x] Assert result validates as `CodeValidationResult`.
- [x] Assert external execution evidence influences `validation_strategy`, `runtime_error`, or `feedback_summary`.

## 7. Documentation and Final Verification

- [x] Document WSL commands for migration, DB-backed tests, and live tests.
- [x] Run focused non-live suite:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_deepagent_validator.py tests/test_content_generator_agent.py tests/test_code_correction_service.py tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py tests/test_learning_content_generation.py -q`
- [x] Run compile verification:
  `PYTHONPATH=. ../venv/bin/python -m compileall -q app tests`
- [x] Record any live-test environment requirements in the final notes.
