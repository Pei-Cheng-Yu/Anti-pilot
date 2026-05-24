# Product-Path Memory Verification

## Current Product Boundary

There is no learner-submission FastAPI route visible under `backend/app`.

The current product-facing boundary is MCP/service:

- `backend/app/mcp/server.py` mounts `code_correction_mcp`
- `backend/app/mcp/tools/code_correction.py` exposes `code_correction.submit_code_attempt`
- that MCP tool delegates to `app.services.code_correction.submit_code_attempt`
- `submit_code_attempt` invokes the validator, converts validation evidence to `CodeCorrectionRequest`, then delegates to `process_code_correction`
- the correction service calls `learning_memory.record_and_consolidate_attempt`

So memory generation is wired when callers use the submission MCP/service path.

Use `process_code_correction` only when a caller already has trusted validation/evaluation evidence and wants to skip validator invocation.

Use low-level `learning_memory_*` tools for explicit memory edits, background/preference notes, or debugging. Routine learner-code evolution should go through `submit_code_attempt`.

## Verified Flow

The live product-path test starts without seeded memory for the test user:

```text
bad FastAPI async route attempt
        |
submit_code_attempt
        |
validate_code_submission
        |
process_code_correction
        |
CodingProblemAttempt
        |
LearnerMemoryNote(ERROR_PATTERN)
        |
build_learning_content_graph
        |
learning_memory_retrieval_diagnostics_by_skillpath.status == "retrieved"
        |
learning_memory_contexts_by_skillpath contains the created note
        |
real ADK content generation adapts to the missing-await mistake
```

The live product-path test also submits a passing related follow-up:

```text
passing FastAPI async route attempt
        |
submit_code_attempt
        |
validate_code_submission
        |
process_code_correction
        |
same ERROR_PATTERN gets another evidence attempt
        |
salience decreases and status moves active -> watch
        |
content graph retrieval still sees the watched note
```

## LangSmith Fields To Inspect

For the content-generation graph trace, inspect:

- `learning_memory_retrieval_diagnostics_by_skillpath`
- `learning_memory_contexts_by_skillpath`
- `generated_skillpaths`

Expected diagnostic shape:

```json
{
  "status": "retrieved",
  "active_error_pattern_count": 1,
  "recent_attempt_count": 2,
  "relevant_note_count": 1
}
```

Expected memory context evidence:

- `mastery_state.failed_attempts == 1`
- `mastery_state.successful_attempts == 1`
- `recent_attempts` contains the bad attempt and the passing follow-up
- `active_error_patterns[0].status == "watch"` after the follow-up
- `active_error_patterns[0].evidence_attempt_ids` contains both attempt IDs
- `active_error_patterns[0].summary` mentions improvement on async/await or route handling

Expected generated content evidence:

- not the fake marker `Short article for the skill path.`
- mentions `await`, `async`, coroutine, or FastAPI route handlers

## Seeded-Memory Difference

Seeded-memory tests insert `LearnerMemoryNote` rows before generation. This product-path test does not.

Instead, it proves the memory note is created by the bad attempt itself through correction persistence and consolidation.

## Commands

Run the product-path live test from WSL:

```bash
cd /mnt/c/Users/seans/anti-pilot/Anti-pilot/backend
RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py::test_live_product_path_bad_attempt_creates_memory_then_content_graph_uses_it -q -s
```

Run the full live memory/agent smoke:

```bash
cd /mnt/c/Users/seans/anti-pilot/Anti-pilot/backend
RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s
```
