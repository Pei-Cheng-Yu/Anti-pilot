## 1. Enum Contract Refactor

- [ ] 1.1 Move `MemoryIntegrityAction`, `HintLevel`, `TeachingAction`, and `MemoryRerankPurpose` into `backend/app/schema/enums.py`.
- [ ] 1.2 Update `entities.py`, services, tests, MCP tools, and agent modules to import moved enums from `app.schema.enums`.
- [ ] 1.3 Add or update focused tests/compile checks that fail on stale enum imports.
- [ ] 1.4 Verify serialized enum values remain unchanged in model dumps.

## 2. Advisor Schemas And Prompts

- [ ] 2.1 Add structured request/response schemas for hint advisor input and output if existing `HintRequest`/`HintResponse` are not sufficient.
- [ ] 2.2 Add structured request/response schemas for rerank advisor input and output if existing rerank schemas need agent-specific metadata.
- [ ] 2.3 Add structured request/response schemas for integrity advisor input and output if existing integrity schemas need agent-specific metadata.
- [ ] 2.4 Add prompt builders that describe low-spoiler hint rules, bounded candidate IDs, allowed teaching actions, and service-owned write guardrails.

## 3. DeepAgent Advisor Modules

- [ ] 3.1 Add a hint advisor module following existing validator/content-generator structured-output patterns.
- [ ] 3.2 Add a rerank advisor module following existing validator/content-generator structured-output patterns.
- [ ] 3.3 Add an integrity advisor module following existing validator/content-generator structured-output patterns.
- [ ] 3.4 Ensure every advisor returns Pydantic-validated structured output and never performs database writes.

## 4. Service Wiring

- [ ] 4.1 Wire `generate_memory_aware_hint` to invoke the hint advisor by default when advisor execution is enabled.
- [ ] 4.2 Wire `memory_rerank_policy.rerank_memories` to invoke the rerank advisor by default when advisor execution is enabled.
- [ ] 4.3 Wire `memory_integrity.check_memory_write_integrity` to invoke the integrity advisor for ambiguous duplicate/conflict candidate sets when advisor execution is enabled.
- [ ] 4.4 Add configuration flags for advisor execution and deterministic fallback behavior.
- [ ] 4.5 Validate selected or target memory IDs against the bounded candidate set before returning or applying advisor output.
- [ ] 4.6 Validate low-level hint outputs so nudge/conceptual hints do not reveal complete corrected code.

## 5. Tests

- [ ] 5.1 Add non-live fake-advisor tests for hint advisor success, invalid schema fallback, invalid memory IDs, and low-spoiler fallback.
- [ ] 5.2 Add non-live fake-advisor tests for rerank advisor success, invalid schema fallback, invalid memory IDs, and purpose-specific guidance.
- [ ] 5.3 Add non-live fake-advisor tests for integrity advisor merge recommendation, conflict recommendation, invalid target IDs, and service-owned persistence.
- [ ] 5.4 Add regression tests proving deterministic fallback still works when advisors are disabled or unavailable.
- [ ] 5.5 Add tests proving advisor/rerank paths do not directly mutate memory rows.

## 6. Live Smoke And Observability

- [ ] 6.1 Add a gated live smoke test that seeds missing-await memory and invokes the real hint advisor path.
- [ ] 6.2 Add assertions that the live hint selects the seeded memory ID and does not return placeholder or unrelated SQL guidance.
- [ ] 6.3 Add LangSmith observation notes listing trace fields to inspect for advisor request, selected memory IDs, teaching action, and fallback status.
- [ ] 6.4 Keep live smoke gated by `RUN_LIVE_AGENT_MEMORY_TESTS` and Google/Gemini credentials.

## 7. Documentation And Verification

- [ ] 7.1 Update backend memory docs to explain advisor-first behavior and deterministic fallback.
- [ ] 7.2 Document environment/configuration flags for enabling hint, rerank, and integrity advisors.
- [ ] 7.3 Run focused non-live tests for memory service, retriever, hint/rerank behavior, content generation, and code correction.
- [ ] 7.4 Run backend compile verification.
- [ ] 7.5 Run the gated live smoke test when credentials are available.
