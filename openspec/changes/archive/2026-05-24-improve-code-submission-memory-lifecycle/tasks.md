# Tasks

## 1. Product Submission Boundary

- [x] Add `CodeSubmissionResult` schema containing `validation` and `correction`.
- [x] Add service function `submit_code_attempt(CodeValidationRequest, session, ...)`.
- [x] Invoke `validate_code_submission`.
- [x] Convert with `build_correction_request_from_validation`.
- [x] Call `process_code_correction`.
- [x] Return `CodeSubmissionResult`.
- [x] Add unit test with a fake validator proving one request creates a correction result and persists memory.

## 2. MCP Exposure

- [x] Add MCP tool `code_correction.submit_code_attempt` or `code_correction.validate_and_process_code_submission`.
- [x] Accept `CodeValidationRequest` as the structured input.
- [x] Return `CodeSubmissionResult`.
- [x] Add FastMCP in-memory client test proving the tool accepts nested JSON input.
- [x] Keep existing `code_correction.process_code_correction` for callers that already have validation evidence.

## 3. Success-Side Memory Lifecycle

- [x] Extend `consolidate_attempt_memory` to find related active/watch `ERROR_PATTERN` notes on correct attempts.
- [x] Add bounded salience decrease for related successful attempts.
- [x] Add `ACTIVE -> WATCH` transition for sufficiently improved related evidence.
- [x] Add `WATCH -> RESOLVED` transition after repeated strong related successes.
- [x] Reactivate `WATCH -> ACTIVE` on later related failures.
- [x] Ensure resolved notes remain excluded from default retrieval.
- [x] Add tests for failure -> success -> repeated success lifecycle.

## 4. Mastery Consistency

- [x] Ensure `SkillMasteryState.strong_concepts` and `weak_concepts` stay consistent after successes and failures.
- [x] On successful related attempts, reduce or remove concepts from `weak_concepts` only after enough evidence.
- [x] Create/update `MASTERY_SIGNAL` when success evidence is strong enough.
- [x] Add tests proving mastery state, error patterns, and mastery signals agree after attempt sequences.

## 5. Optional Agent/Reranker Judgment

- [x] Add `MemoryConsolidationJudgment` schema.
- [x] Document validator responsibilities versus consolidation judgment responsibilities.
- [x] Build judgment input from attempt, current mastery, candidate memory notes, recent attempts, and validator-derived fields.
- [x] Add optional provider interface for consolidation judgment.
- [x] Add deterministic fallback when no provider is configured.
- [x] Clamp judgment salience/mastery deltas within strict bounds.
- [x] Ignore out-of-scope memory IDs.
- [x] Treat resolution and merge recommendations as bounded advice requiring deterministic evidence checks.
- [x] Add tests for useful judgment, excessive judgment, invalid judgment, and unavailable judgment.

## 6. Product-Path Verification

- [x] Update product-path live test to call the new `submit_code_attempt` boundary instead of calling correction service directly.
- [x] Add a success-follow-up product-path test that starts with an old error pattern and then submits passing related code.
- [x] Assert old error pattern salience/status changes according to lifecycle rules.
- [x] Assert future content generation sees the updated memory state.
- [x] Document LangSmith fields to inspect for failure and success follow-up cases.

## 7. Documentation and Verification

- [x] Update docs to explain the new flow from VS Code/frontend to validator, correction, memory, and later retrieval.
- [x] Document when to call `submit_code_attempt` vs `process_code_correction` vs low-level `learning_memory_*` MCP tools.
- [x] Run focused non-live suite:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_deepagent_validator.py tests/test_content_generator_agent.py tests/test_code_correction_service.py tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py tests/test_learning_content_generation.py tests/test_mcp_tools.py -q`
- [x] Run compile verification:
  `PYTHONPATH=. ../venv/bin/python -m compileall -q app tests`
- [x] Run gated live memory/agent smoke when credentials are available:
  `RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s`
