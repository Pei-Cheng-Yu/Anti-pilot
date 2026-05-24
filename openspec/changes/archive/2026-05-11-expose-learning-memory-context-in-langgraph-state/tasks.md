# Tasks

## 1. State Shape

- [x] Add `LearningMemoryContext` import to `backend/app/langgraph/content_generation/schema/state.py`.
- [x] Add a reducer helper for merging `dict[str, LearningMemoryContext]` values from parallel workers.
- [x] Add `learning_memory_contexts_by_skillpath` to `ContentGenerationState`.

## 2. Content Worker State Update

- [x] Refactor `content_worker` to call `_retrieve_learning_memory_context` once per skillpath.
- [x] Pass the retrieved context into `AdkContentGenerationRequest.learning_memory_context`.
- [x] Return `learning_memory_contexts_by_skillpath={skillpath_id: context}` when context is present.
- [x] Preserve existing behavior when `user_id` is missing or memory retrieval returns `None`.

## 3. Graph-Level Observability Tests

- [x] Add or update a non-live graph test that seeds a `LearningMemoryContext` and invokes the content-generation graph with `user_id`.
- [x] Assert final state includes `learning_memory_contexts_by_skillpath`.
- [x] Assert the generated skillpath ID maps to the seeded memory context.
- [x] Assert the captured `AdkContentGenerationRequest.learning_memory_context` matches the state context.
- [x] Add a no-user test proving no memory context entry is added when `user_id` is absent.
- [x] Run:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py -q`

## 4. Documentation

- [x] Update the memory integration verification notes to describe `state["learning_memory_contexts_by_skillpath"]`.
- [x] Document the most useful fields to inspect: `active_error_patterns`, `teaching_heuristics`, `recent_attempts`, and `relevant_notes`.
- [x] Document that ADK still receives memory through `AdkContentGenerationRequest.learning_memory_context`.

## 5. Final Verification

- [x] Run focused content-generation tests:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_content_generation.py tests/test_content_generator_agent.py -q`
- [x] Run focused memory/agent integration tests:
  `PYTHONPATH=. ../venv/bin/python -m pytest tests/test_learning_memory_service.py tests/test_learning_memory_retriever.py tests/test_code_correction_service.py -q`
- [x] Run compile verification:
  `PYTHONPATH=. ../venv/bin/python -m compileall -q app tests`
