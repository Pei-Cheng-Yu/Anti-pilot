## Context

`add-planner-memory-injection` added milestone-level retrieval inside `skillpath_worker`: each per-milestone worker calls `retrieve_learning_memory()` and injects the resulting `LearningMemoryContext` into `SKILLPATH_PROMPT`. Observed behaviour: with a small note pool, `top_k_notes` (default 5) returns ~all notes, and the hybrid score's discriminating term (`0.55×vector`) is weak unless embeddings are rich — so all milestones receive the same notes.

The codebase already has a complete, purpose-driven rerank stack:
- `MemoryRerankRequest{purpose, task_context, learner_context, recent_attempts, candidate_memories, max_selected}`
- `MemoryRerankResult{purpose, selected_memories, teaching_action, focused_concepts, guidance}`
- `memory_rerank_policy.arerank_memories(request, advisor=None)` — LLM-first, deterministic `_fallback_result` (first `max_selected` candidates) when the advisor is unavailable or returns invalid output
- `_default_rerank_advisor()` gated by `ENABLE_MEMORY_RERANK_ADVISOR` + credentials → `rerank_memory_advice`
- `build_rerank_advisor_prompt` branches guidance by purpose

Content generation already uses this with `purpose=CONTENT_GENERATION`. The planner can reuse the same machinery with a new purpose.

## Goals / Non-Goals

**Goals:**
- Per-milestone selection of the retrieved notes, so each milestone's skillpath prompt sees only relevant notes
- Reuse the existing rerank advisor + policy + deterministic fallback (no new advisor function)
- Differentiate milestones even with a small pool / weak embeddings (LLM reads milestone intent)

**Non-Goals:**
- No goal-level rerank — goal generation keeps the full broad context
- No new advisor function, no new DB schema, no new MCP tool
- No change to retrieval itself (still returns the full `LearningMemoryContext`); selection is a post-retrieval filter for the prompt only

## Decisions

### Decision 1: New `MemoryRerankPurpose.ROADMAP_PLANNING`

Reusing `CONTENT_GENERATION` would feed content-oriented selection guidance. A dedicated purpose lets the prompt say "select notes that should shape *which skillpaths to include and how to scope this milestone*." Only the enum value + a guidance branch are new; the request/result schemas and policy are unchanged.

### Decision 2 (REVISED): Retrieve + rerank in a pre-fan-out node, not inside the worker

**Original plan** was to rerank inside `skillpath_worker` via `asyncio.run`. This **deadlocked**: the rerank runs a Google LLM call via `asyncio.run` inside the parallel fan-out worker thread, which leaves the process-global Google `aiohttp` client bound to that temporary (now-closed) event loop; the worker's subsequent **sync** `get_gemini().invoke()` then reuses that loop-bound client and hangs. (Content-gen doesn't hit this because it generates via ADK, not `get_gemini().invoke()`, after its rerank.)

**Revised design:** a single pre-fan-out node `retrieve_and_rerank_milestones` runs after `milestone_quick_review` (on proceed) and does **all** milestones' retrieval + rerank concurrently in **one event loop** (`asyncio.gather`, one `asyncio.run` on the main invoke thread, isolated NullPool engine). It stores per-milestone full context (`milestone_memory_contexts`) and selected note ids (`milestone_selected_ids`) in state. `route_to_skillpath_workers` then fans out, putting each milestone's **rerank-filtered** context into the Send payload as `milestone_prompt_context`. `skillpath_worker` becomes **pure-sync** — it only reads its payload context and calls `get_gemini().invoke()`. No event loop ever runs inside a fan-out worker thread, so the Google client is never loop-poisoned. Per-milestone retrieval/rerank failures are caught inside the gather and that milestone degrades out (no crash).

This also removes the need for the `milestone_memory_contexts` dict reducer (a single node writes the whole map), though the reducer is kept harmlessly.

#### (superseded) Decision 2: Rerank inside skillpath_worker, fold into the existing async wrapper

`skillpath_worker` already retrieves milestone memory via a sync `asyncio.run()` wrapper with an isolated NullPool engine. The rerank advisor is a DeepAgent LLM call with **no DB access**, so it runs inside the *same* async wrapper — one `asyncio.run()` does retrieve-then-rerank, avoiding extra event-loop churn:

```python
async def _run():
    async with isolated_session() as session:
        context = await retrieve_learning_memory(..., session)
    rerank = await arerank_memories(
        MemoryRerankRequest(
            purpose=MemoryRerankPurpose.ROADMAP_PLANNING,
            task_context=f"{milestone.title}\n{milestone.objective}",
            candidate_memories=context.relevant_notes,
            max_selected=5,
        ),
        advisor=_default_rerank_advisor(),
    )
    return context, rerank
```

### Decision 3: Selection filters the prompt, not the stored context

`milestone_memory_contexts[milestone_id]` keeps the **full** retrieved context (traceability, future use, parity with goal-level). The rerank's `selected_memories` IDs are used only to **filter which notes get formatted into `SKILLPATH_PROMPT`**. If the rerank selects nothing (or fallback returns all), the prompt simply uses the available notes.

Implementation: build the formatted memory string from the subset of `context` notes whose `memory_id ∈ selected_ids`; if `selected_ids` is empty, fall back to the full context (no worse than today).

### Decision 4: LLM-first, deterministic fallback — reuse the existing flag

Gate via `_default_rerank_advisor()` (existing `ENABLE_MEMORY_RERANK_ADVISOR` + credentials). When off/uncredentialed/invalid, `arerank_memories` returns `_fallback_result` = first `max_selected` candidates by retrieval order. So even without the LLM, the prompt is narrowed to top-N rather than all — strictly no worse than current behaviour, and deterministic for tests.

### Decision 5: candidates = `context.relevant_notes`

`relevant_notes` is the unified ranked list the retriever already produced; it spans all 5 types. Passing it as `candidate_memories` lets the advisor pick across types for the milestone. (The typed buckets in the context are derived from the same notes, so no information is lost.)

## Risks / Trade-offs

**Extra LLM call per milestone** → one rerank call per `skillpath_worker`. The worker already makes a skillpath-generation LLM call, so this roughly doubles per-milestone LLM cost. Acceptable for roadmap generation (not a hot path); deterministic fallback avoids the call when the flag is off.

**Rerank drops a note the milestone actually needed** → `max_selected=5` is generous relative to typical pools; empty selection falls back to the full context. The advisor is instructed to select only relevant notes, not to be aggressive.

**Purpose proliferation** → one new enum value, consistent with the existing three. Low risk.

## Migration Plan

No DB migration. Additive enum value + prompt branch + worker wiring. Rollback: stop calling rerank in `skillpath_worker` (revert to injecting the full context); the new enum value can remain inert. Depends on `add-planner-memory-injection` being applied first.
