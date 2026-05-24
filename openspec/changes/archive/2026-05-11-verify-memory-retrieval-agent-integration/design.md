# Design

## Current State

The backend now has:

- `CodingProblemAttemptModel`, `LearnerMemoryNoteModel`, and `SkillMasteryStateModel`.
- Consolidation that creates `ERROR_PATTERN`, `MASTERY_SIGNAL`, and `HEURISTIC` notes.
- `learning_memory_retriever.py` for vector, keyword, and scope candidate retrieval.
- `retrieve_learning_memory` returning grouped `LearningMemoryContext`.
- Correction service that retrieves memory, records attempts, and consolidates notes.
- Content-generation graph that passes `LearningMemoryContext` into `AdkContentGenerationRequest`.
- ADK content generation that keeps Google Search enabled and validates final JSON text unless ADK confirms native `output_schema + tools` support.

The missing piece is repeatable evidence that these pieces work together under realistic conditions.

## Test Layers

### 1. Retrieval Quality Test

Add a DB-backed test that seeds several memory notes for one user:

- Strong related note: FastAPI async route missing `await`.
- Nearby but weaker note: general FastAPI route background.
- Unrelated note: Python basics or frontend concept.
- Resolved note: related but `resolved`, which must be excluded.

The test calls `retrieve_learning_memory` with:

```text
query_text="fastapi async await route"
skillpath_id="sp-fastapi-routing"
concept_keys=["fastapi.async", "fastapi.routing", "missing await"]
```

Assertions:

- The first `relevant_notes` item is the async error note.
- `active_error_patterns` includes the async note.
- unrelated notes rank below related notes or are absent.
- resolved notes are absent.

This test should run in the normal DB-backed suite because it uses fake embeddings and a deterministic local database.

### 2. Consolidation and Retrieval Integration

Extend the existing memory/correction integration coverage to make the learner-memory lifecycle explicit:

```text
RecordCodingProblemAttemptInput x 2
-> record_and_consolidate_attempt
-> retrieve_learning_memory
-> LearningMemoryContext
```

Assertions:

- An `ERROR_PATTERN` note exists after the first or second failed attempt.
- A `HEURISTIC` note exists after repeated evidence crosses the salience/frequency rule.
- `recent_attempts` includes the latest attempts.
- `teaching_heuristics` contains the generated support note.

### 3. Correction Flow Smoke

Add a script or marked test that simulates what VS Code sends:

- submitted code
- runtime error or test results
- detected concepts and mistakes

It should call `process_code_correction`, then print or assert:

- persisted attempt id
- inferred correctness
- updated memory notes
- retrieved `LearningMemoryContext`

This can be a normal DB-backed test if no live LLM is involved.

### 4. Content Generator Memory Smoke

Add a live smoke script or `pytest.mark.live_llm` test that:

1. Seeds memory for a test user, such as repeated missing `await` in FastAPI routes.
2. Runs content generation for a FastAPI route-handler skillpath with `user_id`.
3. Captures the `AdkContentGenerationRequest` or generated prompt for inspection.
4. Runs the real ADK generator only when credentials are present and the live flag is set.

Assertions for the non-live part:

- `learning_memory_context` is present on the request.
- Prompt text contains the memory section.
- Memory notes contain the expected error pattern and heuristic.

Assertions for the live part:

- Generation completes.
- Article or coding problem includes a useful adaptation related to the seeded memory, such as a reminder about `await`, async I/O, or route-handler pitfalls.

### 5. Validator Live Smoke

Add a live smoke path for `validate_code_submission` with a fake or state backend and external execution evidence. It should be skipped unless required model credentials are present.

Assertions:

- Live result validates into `CodeValidationResult`.
- `validation_strategy` reflects external evidence or static review.
- Runtime/compile evidence is not dropped.

## Developer Commands

Document these commands in test module docstrings or a smoke README:

```bash
cd /mnt/c/Users/seans/anti-pilot/Anti-pilot/backend
PYTHONPATH=. ../venv/bin/alembic current
PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_memory_service.py tests/test_code_correction_service.py tests/test_learning_memory_retriever.py -q
PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q
```

## Error Handling

- Live tests should skip with a clear reason when credentials or explicit live flags are missing.
- Smoke scripts should print the `LearningMemoryContext` summary before running live agents so failures still show whether retrieval worked.
- If ADK structured output with tools is unavailable, live content generation should continue through JSON text plus Pydantic validation.

## Scope Boundary

This change is about verification and observability, not changing the memory architecture again. Any ranking formula changes should only happen if a new deterministic test exposes a real miss.
