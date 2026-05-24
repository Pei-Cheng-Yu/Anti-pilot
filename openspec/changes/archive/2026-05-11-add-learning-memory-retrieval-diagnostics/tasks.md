# Tasks

## 1. Diagnostic State Shape

- [x] Add a `LearningMemoryRetrievalDiagnostic` model or typed state shape.
- [x] Add a merge reducer for `dict[str, LearningMemoryRetrievalDiagnostic]`.
- [x] Add `learning_memory_retrieval_diagnostics_by_skillpath` to `ContentGenerationState`.

## 2. Diagnostic Builder

- [x] Add a helper that builds diagnostics from `user_id`, `skillpath_id`, and optional `LearningMemoryContext`.
- [x] Return `skipped_no_user_id` when `user_id` is absent.
- [x] Return `retrieved` when context includes memory notes, attempts, or mastery state.
- [x] Return `retrieved_empty` when retrieval returns an empty context.
- [x] Add safe `failed` support if retrieval errors are caught.

## 3. Content Worker Integration

- [x] Return one diagnostic entry for every content worker invocation.
- [x] Keep `learning_memory_contexts_by_skillpath` only for actual retrieved contexts.
- [x] Keep `AdkContentGenerationRequest.learning_memory_context` behavior unchanged.

## 4. Tests

- [x] Add a no-user graph test asserting diagnostics show `skipped_no_user_id`.
- [x] Add a seeded-memory graph test asserting diagnostics show `retrieved` and nonzero counts.
- [x] Add an empty-memory graph test asserting diagnostics show `retrieved_empty`.
- [x] Run:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py -q`

## 5. Documentation

- [x] Update verification notes to explain `learning_memory_retrieval_diagnostics_by_skillpath`.
- [x] Document how to interpret empty `learning_memory_contexts_by_skillpath`.
- [x] Include the likely cause from the observed trace: missing top-level `user_id`.

## 6. Final Verification

- [x] Run focused content-generation tests:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py tests/test_content_generator_agent.py -q`
- [x] Run compile verification:
  `PYTHONPATH=. ../venv/bin/python -m compileall -q app tests`
