## Context

The branch already has durable learner memory notes, coding attempts, mastery state, hybrid retrieval, memory integrity checks, optional DeepAgent advisors, memory-aware hints, and rerank policy helpers. Those pieces work, but callers still need to know which lower-level service function to call. That is risky before adding a discovery agent because future agents could accidentally bypass integrity checks or duplicate memory-write behavior.

The next step is to define one public memory service boundary that MCP tools, API routes, code correction, content generation, and future agents can call consistently. This change also makes code correction and content generation consume rerank decisions for their own purposes instead of passing broad retrieved context without an explicit selection step.

This is also a migration pass. Any current workflow that calls memory behavior must be audited and either routed through the facade or documented as an internal helper that is not a public caller boundary.

## Goals / Non-Goals

**Goals:**

- Provide one public memory facade for durable memory operations.
- Migrate current public memory-facing workflows to the facade.
- Ensure durable memory writes flow through integrity prevention and service-owned persistence.
- Keep goal and learning-profile entities as their own source of truth while allowing discovery agents to write durable preference/background memory when useful.
- Make code correction use `MemoryRerankPurpose.CODE_CORRECTION`.
- Make content generation use `MemoryRerankPurpose.CONTENT_GENERATION`.
- Keep existing deterministic fallbacks when LLM advisors are disabled or invalid.

**Non-Goals:**

- No scheduled memory decay, aging job, or predictive forgetting.
- No conflict-review queue or human/admin review UI.
- No roadmap mutation or automatic skillpath adaptation.
- No new database tables or Alembic migration unless implementation discovers an unavoidable schema gap.
- No direct discovery-agent implementation in this change.

## Decisions

### Use a public facade over rewriting existing services

Add a public memory facade module that delegates to the existing lower-level services. This avoids a risky rewrite of `learning_memory.py` while still giving callers one clear contract. Existing helpers such as integrity execution, retrieval, rerank, and hint generation can remain internally testable.

Alternative considered: rename and split the whole learning-memory service immediately. That would improve structure long-term but creates too much churn while the branch already contains memory integrity and advisor work.

### Make MCP tools call the facade

The MCP layer should expose durable memory operations, but it should not encode lifecycle rules. Routing MCP memory tools through the facade makes future API routes and agents follow the same behavior.

Alternative considered: leave MCP tools on `learning_memory` directly. That preserves current behavior but does not create a visible architectural boundary for the discovery agent.

### Audit all existing memory workflow call sites

The implementation should inspect current memory-facing paths: MCP tools, code correction, content generation, hint generation, direct memory writes, attempt consolidation, tests, and future API entry points if present. Public callers should route through the facade. Lower-level helpers can remain in place when they are implementation details used by the facade.

Alternative considered: only create the facade and let future code use it. That would not solve the existing split-brain risk, where old workflows keep bypassing the new boundary.

### Treat goal/profile as source of truth and memory as durable teaching context

Discovery should update goal and learning-profile services for structured learner state. It may also create `preference_signal` or `background` memory notes when the fact should influence future teaching prompts. The same fact should not be blindly duplicated into memory just because it exists in the profile.

Alternative considered: mirror all goal/profile fields into memory. That would make retrieval easier but risks contradictions and duplicate maintenance.

### Rerank before feedback and prompt consumption

Code correction and content generation should retrieve a broad `LearningMemoryContext`, then ask the rerank policy which memories matter for the current purpose. This keeps retrieval broad but prompt/feedback guidance narrow.

Alternative considered: pass the full context to all consumers and trust the downstream LLM. That is simpler but weaker for observability and makes noisy memory more likely to shape output.

### Keep rerank advisory and non-mutating

Rerank can choose memories and guidance. It must not write memory, change status, mutate goal/profile, or modify roadmap structure. Persistence remains in memory-write and attempt-consolidation paths.

## Risks / Trade-offs

- Public facade becomes a thin wrapper only -> Keep tests focused on call routing and behavior, not just module existence.
- Existing callers may bypass the facade -> Update MCP, code correction, and content generation first, then document the rule for future agents.
- Rerank advisor may produce invalid memory IDs -> Reuse existing validation and deterministic fallback.
- Content prompts may become too narrow if rerank selects too few memories -> Preserve full diagnostics and allow fallback to deterministic selected context.
- Discovery agent may over-write memory notes -> Document that discovery writes only durable teaching facts/preferences, not every onboarding answer.

## Migration Plan

1. Add the facade while keeping existing services available internally.
2. Audit all current memory-facing workflows and classify each as facade caller, internal helper, or deferred non-memory feature.
3. Update MCP memory tools to call the facade.
4. Update code correction to build and expose code-correction rerank guidance through facade-backed retrieval.
5. Update content generation to build content-generation rerank guidance through facade-backed retrieval and pass it into prompt-facing request data.
6. Add tests before each behavior change.
7. Keep rollback simple: callers can temporarily return to existing lower-level services because no schema migration is planned.

## Open Questions

- Should content-generation rerank guidance be added directly to `AdkContentGenerationRequest`, or placed inside the existing `LearningMemoryContext` diagnostics bundle?
- Should code-correction rerank guidance become part of `CodeCorrectionResult`, or only shape `suggested_focus` and feedback text?
