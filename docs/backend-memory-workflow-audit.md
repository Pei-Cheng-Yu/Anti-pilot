# Backend Memory Workflow Audit

This audit supports OpenSpec change
`add-unified-memory-service-and-rerank-consumers`.

## Public Facade Callers

These workflows should call the public memory service facade:

- MCP memory tools in `backend/app/mcp/tools/learning_memory.py`
  - add/update/resolve/delete memory notes
  - record attempts and consolidate memory
  - retrieve memory context
  - generate memory-aware hints
- Code correction in `backend/app/services/code_correction.py`
  - retrieve memory context before persistence
  - record and consolidate the submitted attempt
  - rerank retrieved memories for `code_correction`
- Content generation in
  `backend/app/langgraph/content_generation/graphs/generate_learning_content/nodes.py`
  - retrieve memory context per skillpath
  - rerank retrieved memories for `content_generation`
- Future API routes and discovery agents
  - write durable `preference_signal` or `background` notes
  - retrieve memory context for learner-aware orchestration

## Public Memory Service Contract

`backend/app/services/memory_service.py` is the intended public boundary for
memory-facing product flows. MCP tools, API routes, code-correction workflows,
content-generation workflows, and future discovery agents should call this
facade instead of importing lower-level helpers directly.

The facade owns these public operations:

- durable note writes: `add_memory_note`, `update_memory_note`,
  `resolve_memory_note`, and `delete_memory_note`
- attempt lifecycle writes: `record_coding_problem_attempt` and
  `record_and_consolidate_attempt`
- memory reads: `get_skill_mastery_state` and `retrieve_learning_memory`
- advisory memory actions: `rerank_memories` and `generate_memory_aware_hint`

Lower-level modules may still exist, but they should be treated as internal
implementation details. This keeps integrity checks, rerank validation, and
future memory lifecycle policy behind one stable service boundary.

## Discovery Agent Memory Contract

Discovery agents should keep goal and learning-profile entities as the source
of truth for structured learner setup data:

- goals: title, target outcome, deadline, criteria, constraints
- learning profile: baseline level, weak areas, pace, confidence, recap needs,
  examples-first preference, overload risk

Discovery agents should write memory notes only when the extracted information
is durable teaching context that benefits future generation or feedback. Use:

- `preference_signal` for stable teaching preferences, such as "examples before
  abstract explanation" or "prefers hands-on practice"
- `background` for durable learner context not already owned by the goal/profile
  schema, such as prior project experience or concept history

Do not duplicate the full goal or learning profile into memory. A discovery
agent may write a compact memory note when the fact is useful across sessions,
but it should still update the goal/profile services through their own tools.

## Internal Helpers

These modules remain lower-level implementation details owned by the facade or
specialized services:

- `backend/app/services/learning_memory.py`
  - persistence, consolidation, integrity execution, retrieval implementation
- `backend/app/services/learning_memory_retriever.py`
  - hybrid candidate collection
- `backend/app/services/memory_integrity.py`
  - integrity candidate evidence, advisor validation, deterministic fallback
- `backend/app/services/memory_rerank_policy.py`
  - bounded purpose-specific memory selection
- `backend/app/services/memory_hint.py`
  - hint retrieval, rerank, advisor validation, fallback hint construction
- `backend/app/advisors/memory_advisors.py`
  - structured DeepAgent advisor prompts and response parsing

These helpers are intentionally kept internal after the facade migration because
they represent implementation policy, not product entrypoints. Direct callers
would make it easier to bypass integrity validation, rerank result validation,
or future lifecycle rules.

## LangSmith Observability

For code correction, inspect `CodeCorrectionResult.memory_rerank`:

- `purpose` should be `code_correction`
- `selected_memories` should contain only retrieved candidate memory IDs
- `teaching_action`, `focused_concepts`, and `guidance` explain how the memory
  should shape feedback

For content generation, inspect graph state:

- `learning_memory_retrieval_diagnostics_by_skillpath`
- `learning_memory_contexts_by_skillpath`
- `learning_memory_rerank_results_by_skillpath`
- `learning_memory_rerank_diagnostics_by_skillpath`

Useful rerank diagnostics:

- `status`: `reranked`, `skipped_no_memory`, or `failed`
- `candidate_memory_count`
- `selected_memory_ids`
- `teaching_action`
- `focused_concepts`
- `guidance_present`

## Deferred Or Non-Memory Workflows

These are intentionally not migrated by this change:

- Goal and learning-profile services remain their own source of truth.
- Roadmap, milestone, and skillpath status updates remain roadmap-owned.
- Scheduled decay, predictive forgetting, conflict review queues, and roadmap
  adaptation are future lifecycle work.
