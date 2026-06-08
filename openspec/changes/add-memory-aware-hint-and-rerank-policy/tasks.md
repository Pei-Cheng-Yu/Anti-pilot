## 1. Schemas And Contracts

- [x] 1.1 Add Pydantic schemas for `HintRequest`, `HintResponse`, hint levels, teaching actions, and selected memory metadata.
- [x] 1.2 Add Pydantic schemas for `MemoryRerankRequest`, `MemoryRerankResult`, selected memory decisions, and purpose-specific guidance.
- [x] 1.3 Add validation rules so rerank results cannot reference memory IDs outside the candidate set.

## 2. Rerank Policy Service

- [x] 2.1 Add a memory rerank policy service that accepts deterministic candidates and returns selected memories plus guidance.
- [x] 2.2 Add deterministic fallback behavior that uses existing ranked memory order when the LLM advisor is unavailable or invalid.
- [x] 2.3 Add an optional LLM advisor interface for structured rerank output without DB writes.
- [x] 2.4 Add tests for valid advisor output, invalid memory IDs, invalid schema fallback, and purpose-specific guidance.

## 3. Hint Service

- [x] 3.1 Add a hint service that builds a memory retrieval query from learner/task/code context.
- [x] 3.2 Connect the hint service to `learning_memory.retrieve_learning_memory`.
- [x] 3.3 Apply rerank policy output to choose hint focus, hint level, quick recap, or contrast-example guidance.
- [x] 3.4 Ensure default hints do not reveal complete corrected code.
- [x] 3.5 Add tests for hints with relevant memory, hints without memory, progressive hint levels, and low-spoiler behavior.

## 4. Integration

- [x] 4.1 Wire rerank policy into content generation or provide an opt-in helper that content generation can call.
- [x] 4.2 Wire rerank policy into hint generation as the first production consumer.
- [x] 4.3 Expose selected memory IDs and teaching action metadata in returned hint results.
- [x] 4.4 Add MCP or service entrypoint coverage if agent callers need direct hint access.

## 5. Verification

- [x] 5.1 Run non-live tests for learning memory, content generation, and new hint/rerank behavior.
- [x] 5.2 Add a fixture that proves a missing-await memory is selected over unrelated SQL memory for an async FastAPI hint.
- [x] 5.3 Verify the reranker does not persist or mutate learner memory.
- [x] 5.4 Document the hint/rerank flow in backend service documentation.
