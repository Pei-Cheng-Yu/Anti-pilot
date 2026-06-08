## Context

The current memory branch has deterministic services for memory integrity, memory rerank policy, and memory-aware hints. Those services establish safe schemas and fallback behavior, but the learner-facing quality still depends on real agent judgment. The existing backend already has patterns for structured agent output in the validator and content generator, and live memory integration tests can be observed in LangSmith.

The next step is to keep the safe service contracts while making DeepAgent/LLM advisors the normal product path for hint generation, memory reranking, and ambiguous memory integrity decisions. Shared enum vocabulary also needs to move into `schema/enums.py` so agents, schemas, MCP tools, and services import the same constants.

## Goals / Non-Goals

**Goals:**

- Move shared enum definitions out of `entities.py` and into `schema/enums.py`.
- Add structured DeepAgent/LLM advisors for hint generation, memory reranking, and memory integrity.
- Make advisor invocation the normal path when enabled/configured.
- Keep deterministic behavior as fallback and validation, not as the main intelligence.
- Keep all database writes service-owned and validated.
- Add LangSmith-observable live smoke coverage for the real advisor path.
- Reuse existing agent and graph patterns where practical.

**Non-Goals:**

- Do not let advisors search arbitrary learner memory.
- Do not let advisors directly create, update, merge, resolve, or delete memory rows.
- Do not replace pgvector/full-text/scope retrieval.
- Do not implement roadmap adaptation or predictive forgetting.
- Do not require every unit test to call a live LLM.

## Decisions

### Centralize Enums In `schema/enums.py`

Shared enums such as `MemoryIntegrityAction`, `HintLevel`, `TeachingAction`, and `MemoryRerankPurpose` should live beside existing enums like `MemoryType` and `MemoryStatus`.

Alternative considered: create a new enum package. This is unnecessary now because the repo already uses a single `schema/enums.py` module, and the new enums are part of the same schema vocabulary layer.

### Add Separate Advisor Modules

Use separate advisor modules for distinct jobs:

- hint advisor: generates structured learner-facing `HintResponse`
- rerank advisor: selects candidate memory IDs and returns teaching guidance
- integrity advisor: recommends duplicate/conflict action over bounded candidates

Alternative considered: one universal memory advisor. This would blur prompts and schemas. Separate modules keep each prompt focused and make tests easier to reason about.

### LLM Is Normal Path, Deterministic Is Guardrail

For product calls, services should attempt the LLM advisor first when enabled and credentials are available. If the advisor fails, returns invalid schema, selects invalid IDs, or violates spoiler rules, the service falls back to deterministic behavior.

Alternative considered: deterministic-first with optional manual advisor injection. That is safe but makes the feature feel like a scaffold rather than an agentic learning system.

### Retrieval Bounds Advisor Context

Advisors receive only bounded candidates from the existing retrieval/integrity candidate-discovery layer. They do not query the database themselves.

Alternative considered: let the LLM retrieve or inspect all memory. This increases latency and makes privacy, correctness, and observability harder.

### Service Owns Persistence

The integrity advisor can recommend actions such as `update_existing`, `merge`, or `flag_conflict`, but the service validates IDs, action type, confidence, salience/status changes, and then performs writes. Advisor code returns structured recommendations only.

Alternative considered: agent tool calls that write directly to memory. This was rejected because memory lifecycle requires deterministic guardrails and auditability.

### Live Smoke Should Be LangSmith-Observable

Add at least one gated live smoke that seeds memory, invokes the real advisor path, and asserts selected memory IDs and generated hint/advice are memory-specific. Use existing `.env` tracing variables and live marker conventions.

## Risks / Trade-offs

- LLM latency and cost -> keep candidate sets bounded and retain deterministic fallback.
- Advisor returns invalid IDs -> validate every selected/target memory ID against candidates.
- Hint reveals too much -> validate low-level hint output against submitted code and expected spoiler rules.
- Integrity advisor over-merges -> only use advisor over bounded candidates and require service validation before writes.
- Live tests are slower/flakier -> keep live tests gated by environment variables and maintain non-live fake-advisor tests.
- Enum move breaks imports -> update all imports and add focused compile/tests to catch stale references.

## Migration Plan

1. Move enums to `schema/enums.py` and update imports.
2. Add structured advisor schemas/prompts/modules without changing DB schema.
3. Wire hint/rerank services to call advisors by default when enabled/configured.
4. Wire integrity service to call advisor for ambiguous decisions after deterministic candidate discovery.
5. Add non-live fake-advisor tests.
6. Add gated live smoke test and LangSmith observation notes.
7. Keep deterministic fallback available for local development and unavailable credentials.

Rollback strategy: disable advisor invocation through configuration and fall back to deterministic service behavior.

## Open Questions

- Should advisor enabling use one global flag or separate flags for hint, rerank, and integrity?
- Should the hint advisor be implemented with the same DeepAgent wrapper as validation, or a lighter ADK structured-output agent?
- Should integrity advisor be enabled by default immediately, or only after more live evidence because it can affect writes?
