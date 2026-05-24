# Tasks

## 1. Baseline and Discovery

- [x] Run the current memory and correction tests from `backend/`:
  `PYTHONPATH=. python -m pytest tests/test_learning_memory_service.py tests/test_code_correction_service.py -q`
- [x] Record any baseline failures before refactoring.
- [x] Confirm the migration layout used by the repo before adding database migration files.
- [x] Confirm the installed Deep Agents and Google ADK structured-output APIs in the local environment.

## 2. Structured Output for Deep Agent Validator

- [x] Add `backend/tests/test_deepagent_validator.py` covering `structured_response` preference.
- [x] Update `create_code_validator_agent` to pass `response_format=CodeValidationResult`.
- [x] Update validator prompt wording so validation uses submitted code plus caller-supplied compile/runtime/test evidence and does not assume sandbox execution.
- [x] Update `validate_code_submission` to read `structured_response` before JSON-message fallback parsing.
- [x] Run `PYTHONPATH=. python -m pytest tests/test_deepagent_validator.py -q`.

## 3. VS Code Execution Evidence Flow

- [x] Extend `CodeValidationRequest` with optional `compile_error`, `runtime_error`, `stdout`, `stderr`, and `test_results`.
- [x] Ensure `_build_validation_prompt` includes those fields only when supplied.
- [x] Add a correction mapping helper that builds `CodeCorrectionRequest` from `CodeValidationResult`.
- [x] Add tests showing validation evidence reaches the correction request unchanged.
- [x] Run `PYTHONPATH=. python -m pytest tests/test_code_correction_service.py -q`.

## 4. Structured Output for Content Generator

- [x] Add `_coerce_content_generation_output` tests for model instance, dict, and JSON string inputs.
- [x] Add `_coerce_content_generation_output` in `backend/app/adk_agents/content_generator/agent.py`.
- [x] Attempt `output_schema=AdkContentGenerationOutput` in ADK `Agent` construction, then gate it with ADK's own `can_use_output_schema_with_tools` compatibility check after runtime verification and ADK docs showed `output_schema` with tools is model-dependent.
- [x] Replace final JSON-only parse calls with the coercion helper.
- [x] Update prompt wording to require the `AdkContentGenerationOutput` schema while keeping a plain-text JSON fallback line.
- [x] Run `PYTHONPATH=. python -m pytest tests/test_content_generator_agent.py -q`.

## 5. Pgvector Storage and Full-Text Indexing

- [x] Add `pgvector` to `requirements.txt`.
- [x] Update Docker Postgres image or initialization so the `vector` extension is available.
- [x] Change `LearnerMemoryNoteModel.embedding` from `JSONB` to `Vector(3072)` or the confirmed embedding dimension.
- [x] Add `search_text` to `LearnerMemoryNoteModel`.
- [x] Add a helper to build `search_text` from memory-note title, summary, tags, linked concepts, linked skillpaths, linked content ids, and evidence attempt ids.
- [x] Use the helper in memory note create/update/consolidation paths.
- [x] Add a migration enabling `vector`, adding `search_text`, converting or nulling incompatible embeddings, and creating vector/full-text/array indexes.
- [x] Run database model and migration tests, or document the exact local database blocker.

Resolved migration notes:
- The previous local database blocker was plain PostgreSQL without the `vector` extension. After the database image was upgraded to pgvector, `alembic upgrade head` reached this migration.
- The migration also needed to create `coding_problem_attempts`, `skill_mastery_states`, and `learner_memory_notes` because those models existed in SQLAlchemy metadata but not in Alembic history.
- pgvector cannot create an ivfflat index over a 3072-dimensional `vector`; the migration now uses a 3072-dimensional `halfvec` HNSW expression index for cosine search.

## 6. Hybrid Retriever Service

- [x] Create `backend/app/services/learning_memory_retriever.py`.
- [x] Add `_dedupe_note_rows_by_id` and tests for stable first-seen deduplication.
- [x] Implement pgvector top-50 semantic candidate retrieval.
- [x] Implement full-text top-50 keyword candidate retrieval.
- [x] Implement concept/skillpath/content scope candidate retrieval.
- [x] Add `get_memory_note_candidates` to merge and deduplicate all candidate pools.
- [x] Run `PYTHONPATH=. python -m pytest tests/test_learning_memory_retriever.py -q`.

## 7. Wire Retriever Into Learning Memory

- [x] Move query embedding generation before candidate retrieval in `retrieve_learning_memory`.
- [x] Replace all-active-note fetching with `get_memory_note_candidates`.
- [x] Keep `_memory_note_score` as the final Python rerank over the reduced candidate set.
- [x] Preserve memory type filtering and `last_used_at` updates.
- [x] Run `PYTHONPATH=. python -m pytest tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py -q`.

## 8. Use Learning Memory Context in Agent Inputs

- [x] Add optional `learning_memory_context: LearningMemoryContext | None` to `AdkContentGenerationRequest`.
- [x] Retrieve memory in the content generation graph when user id and skillpath/concept context are available.
- [x] Include serialized memory context in the content generation prompt only when present.
- [x] Identify the search/resource recommendation entrypoint and wire the same `LearningMemoryContext` contract there if it exists in the current codebase.
- [x] Add tests proving content generation receives memory context when user context is available.
- [x] Run `PYTHONPATH=. python -m pytest tests/test_learning_content_generation.py -q`.

Search/resource note: no separate search or resource recommendation service exists yet; current search usage is the content generator's Google Search tool, which now receives learner memory through `AdkContentGenerationRequest`.

## 9. Final Verification

- [x] Run the focused backend suite for validator, content generation, correction, and learning memory.
- [x] Run formatting/linting commands used by the repo.
- [x] Verify no code path still requires paid cloud sandbox execution for validation.
- [x] Verify no retrieval path fetches every active user memory note before candidate search.
- [x] Update implementation notes with any deferred optional reranker work.

Verification notes:
- Focused backend suite passed: `tests/test_deepagent_validator.py`, `tests/test_content_generator_agent.py`, `tests/test_code_correction_service.py`, `tests/test_learning_memory_service.py`, `tests/test_learning_memory_retriever.py`, and `tests/test_learning_content_generation.py` (`20 passed`).
- ADK content generator note: ADK docs warn `output_schema` with tools is only supported by specific model/runtime combinations. When `output_schema` was enabled with Google Search and ADK did not consider the runtime natively compatible, ADK injected `set_model_response` and failed to parse nested optional Pydantic fields. The content generator now uses ADK's own compatibility check; otherwise it keeps Google Search enabled and validates final JSON text with Pydantic coercion.
- Real content generation smoke passed via `PYTHONPATH=. ../venv/bin/python tests/test_learning_content_generation.py`.
- `python -m compileall -q app tests` passed.
- `ruff` is not installed in the WSL virtualenv (`venv/bin/ruff: not found`), so lint verification could not be run.
- DB-backed correction/memory tests passed after applying the pgvector migration.
- Optional LLM/reranker remains deferred; the retriever now exposes the merged candidate set where it can be added later.
