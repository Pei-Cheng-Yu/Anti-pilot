## Why

The planner's milestone-level retrieval (inside `skillpath_worker`) injects the *full* retrieved `LearningMemoryContext` into every milestone's skillpath prompt. When the learner's note pool is small, `top_k` returns essentially all notes, so every milestone receives the **same undifferentiated set** — the async milestone, the SQL milestone, and the testing milestone all see identical memory. Vector ranking only differentiates once the pool is large and embeddings are rich; for the common small-pool case there is no per-milestone focus.

A rerank step solves this by purpose-aware *selection*: an LLM (or deterministic fallback) reads the milestone's intent and picks only the notes relevant to *that* milestone, independent of embedding quality.

## What Changes

- Add a new `MemoryRerankPurpose.ROADMAP_PLANNING` value and a planning-specific guidance branch in the rerank advisor prompt
- Inside `skillpath_worker`, after milestone-level retrieval, call the existing Rerank Policy (`arerank_memories`) with `purpose=ROADMAP_PLANNING`, `task_context` = milestone title + objective, and the retrieved notes as candidates
- Inject only the **selected** notes into `SKILLPATH_PROMPT` (instead of all retrieved notes)
- Keep the full retrieved context in `milestone_memory_contexts` for traceability; selection only affects what the prompt sees
- LLM-first with deterministic fallback, reusing the existing `ENABLE_MEMORY_RERANK_ADVISOR` flag and `_fallback_result` (top-N by retrieval order)
- **Scope: milestone-level only.** Goal-level retrieval keeps the full broad context (all 5 types) unchanged

## Capabilities

### New Capabilities

- `planner-milestone-rerank`: Purpose-aware selection of milestone-scoped learner memory inside the planner's skillpath fan-out, so each milestone's skillpath generation sees only the notes relevant to that milestone

### Modified Capabilities

- none

## Impact

- `backend/app/schema/enums.py` — add `MemoryRerankPurpose.ROADMAP_PLANNING`
- `backend/app/advisors/memory_advisors.py` — extend `build_rerank_advisor_prompt` guidance to cover roadmap planning
- `backend/app/langgraph/planner/graphs/generate_roadmap/nodes.py` — in `skillpath_worker`, rerank the retrieved notes and inject only the selected subset
- No DB schema changes, no new advisor function (reuses `rerank_memory_advice` + Rerank Policy), no new MCP tools
- Depends on `add-planner-memory-injection` (the milestone-level retrieval this builds on)
- Reads `learner_memory_notes` only (via the existing retrieval); writes nothing
