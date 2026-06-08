## 1. Public Memory Service Boundary

- [x] 1.1 Audit current memory-facing workflows and list each call site as facade caller, internal helper, or deferred/non-memory feature.
- [x] 1.2 Add failing tests for a public memory facade that writes memory through the integrity-protected path.
- [x] 1.3 Add failing tests for facade methods that retrieve memory context, record and consolidate attempts, and generate memory-aware hints.
- [x] 1.4 Implement the public memory facade by delegating to existing lower-level memory services.
- [x] 1.5 Update MCP memory tools to call the public memory facade.
- [x] 1.6 Update current direct public memory write/retrieval workflows to call the facade where applicable.
- [x] 1.7 Add tests proving MCP and current public workflows use the facade rather than direct lower-level write helpers.
- [x] 1.8 Document any lower-level helpers that intentionally remain internal after migration.

## 2. Discovery Agent Memory Contract

- [x] 2.1 Document that discovery agents update goal and learning-profile entities as source of truth.
- [x] 2.2 Document that discovery agents write only durable teaching facts as `preference_signal` or `background` memory notes.
- [x] 2.3 Add tests or schema-level examples showing discovery-style preference/background writes go through the public memory facade.

## 3. Code Correction Rerank Consumer

- [x] 3.1 Add failing unit test that code correction calls rerank with `purpose=code_correction` after retrieving memory.
- [ ] 3.2 Add failing unit test that invalid rerank output falls back without breaking `CodeCorrectionResult`.
- [x] 3.3 Add code-correction result fields or diagnostics for selected memory IDs, teaching action, and rerank guidance.
- [x] 3.4 Implement code correction rerank consumption and selected-memory validation.
- [x] 3.5 Update code-correction tests to verify selected memories shape `suggested_focus` or correction guidance without mutating memory.

## 4. Content Generation Rerank Consumer

- [x] 4.1 Add failing unit test that content generation calls rerank with `purpose=content_generation` after memory retrieval.
- [x] 4.2 Add failing unit test that empty or invalid rerank output still produces valid generation diagnostics.
- [x] 4.3 Add prompt/request context for content-generation selected memories and rerank guidance.
- [x] 4.4 Implement content-generation rerank consumption with deterministic fallback.
- [x] 4.5 Update content-generation graph tests to verify rerank diagnostics appear in graph state.

## 5. Guardrails And Non-Mutation

- [ ] 5.1 Add tests proving rerank consumers do not create, update, resolve, merge, delete, or flag memory notes.
- [ ] 5.2 Add tests proving rerank consumers do not mutate goal, profile, roadmap, milestone, or skillpath state.
- [ ] 5.3 Ensure facade and consumer code keeps advisor output advisory-only and service-owned persistence authoritative.

## 6. Documentation And Verification

- [x] 6.1 Update backend memory docs with the public memory service contract and caller rules.
- [x] 6.2 Update docs with LangSmith observations for code-correction and content-generation rerank consumers.
- [x] 6.3 Run focused non-live tests for memory facade, code correction, content generation, rerank policy, and MCP tools.
- [x] 6.4 Run backend compile check for `app` and relevant tests.
- [ ] 6.5 Run gated live LLM smoke tests for rerank consumers when credentials and flags are available.
