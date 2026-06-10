## Context

The Planner Graph is a pure LangGraph graph (not a DeepAgent) that generates roadmap structure — milestones and skillpaths — from `goal_spec` and `learning_profile` only. It has no awareness of the learner's existing knowledge, past struggles, or preferences stored in `learner_memory_notes`. Every roadmap is generated as if the learner is starting from scratch.

The Content Generation Graph already demonstrates the correct pattern for a LangGraph graph to use memory: a synchronous node wraps an async retrieval (`asyncio.run()` + `async with get_session()`) and calls `memory_service.retrieve_learning_memory()` directly (`content_generation/.../nodes.py:114-140`). The Planner should follow this same pattern.

**Verified facts about the current planner (as of this change):**

- The active graph is `build_planner_graph()` in `generate_roadmap/graph.py`. Its nodes are: `init_roadmap_context` → `generate_milestone` → `milestone_quick_review` ⇄ `revise_milestones` → (fan-out) `skillpath_worker` → `finalize_skillpath` → END.
- `skillpath_worker` is dispatched **once per milestone** via `Send()` in `route_after_milestone_quick_review` (`nodes.py:146-169`). Each Send payload currently carries only `roadmap_uuid`, `goal_spec`, `learning_profile`, `milestone`.
- There is **no active skillpath-level review node**. A complete `evaluate` graph (`skillpath_review_worker`, `distribute_skillpath_review`, `merge_revised_skillpaths`) exists but is **dead code** — `build_evaluate_graph()` is never invoked anywhere in the backend. It is out of scope for this change.
- Planner nodes are **synchronous** (`def`, `llm.with_structured_output(...).invoke(...)`).
- `PlannerState` already uses `Annotated[list[...], operator.add]` reducers for the fan-out-written fields `skillpath_drafts` and `skillpath_revisions`.
- `goal_spec` and `learning_profile` do **not** carry `user_id`. The Learning Director has it as `resolved_user_id` (`learning_director/agent.py:255`) but does not pass it into `_planner.invoke(...)` (`agent.py:274`).
- `LearningMemoryContext` exists (`entities.py:546-574`) with buckets `mastery_state`, `recent_attempts`, `active_error_patterns`, `mastery_signals`, `teaching_heuristics`, `background_notes`, `relevant_notes`. Notes carry `linked_skillpath_ids` (`entities.py:511-513`).
- `retrieve_learning_memory(payload: RetrieveLearningMemoryInput, session)` takes a payload with `skillpath_id: Optional[str] = None`. When `skillpath_id` is None, `mastery_state` is null. Only a single-key `get_skill_mastery_state(user_id, skillpath_id, session)` loader exists — no batch loader.

## Goals / Non-Goals

**Goals:**
- Add a `retrieve_goal_memory` node before `generate_milestone`; inject goal-level memory into `generate_milestone`, `milestone_quick_review`, and `revise_milestones`.
- Retrieve milestone-level memory **inside** `skillpath_worker` (after fan-out), inject into the skillpath prompt, and accumulate per-milestone contexts into state via a dict reducer.
- Bridge to `SkillMasteryState` through notes' `linked_skillpath_ids` since the planner has no `skillpath_id`.
- Pass `user_id` into the planner and into each `skillpath_worker` Send payload.

**Non-Goals:**
- No Rerank Advisor — the planner makes structural decisions where all 5 memory types contribute differently; narrowing candidates is not appropriate here.
- **No changes to the dead `evaluate` graph.** No skillpath-level review node is added or wired in.
- No DB schema changes — `PlannerState` is a Python TypedDict; the only entity change is one additive field on `LearningMemoryContext`.
- No new memory types, enums, or MCP tools.
- No changes to how memory is written — planner is read-only with respect to memory.

## Decisions

### Decision 1: Direct service call, not MCP

The Planner is a LangGraph graph, not a DeepAgent. Memory retrieval is a direct import of `memory_service.retrieve_learning_memory()` inside the planner nodes, wrapped synchronously exactly like `_retrieve_learning_memory_context()` in the content generation graph:

```python
def _retrieve(payload):
    async def _run():
        async with get_session() as session:
            return await memory_service.retrieve_learning_memory(payload, session)
    return asyncio.run(_run())
```

**Alternative considered:** Retrieve in the Learning Director and pass context into planner input. Rejected — couples the orchestrator to planner memory and diverges from the content-gen pattern where retrieval is co-located with use.

### Decision 2: Goal-level retrieval is its own node before generate_milestone

`retrieve_goal_memory` runs after `init_roadmap_context`, before `generate_milestone`. Query = goal title + description + target outcome. Result stored in `goal_memory_context`. This context is read (not re-retrieved) by `generate_milestone`, `milestone_quick_review`, and `revise_milestones`.

Injecting into all three milestone-stage nodes (not just generation) ensures review and revision preserve memory-driven personalization rather than regenerating generic milestones — this is what addresses the "review undoes the draft" concern, since the only *active* review/revision is at the milestone level.

> **Update (see add-planner-milestone-rerank):** milestone-level retrieval was later moved *out* of `skillpath_worker` into a single pre-fan-out node (`retrieve_and_rerank_milestones`) that runs all milestones in one event loop, because running an LLM rerank via `asyncio.run` inside the parallel worker threads deadlocked the subsequent sync `get_gemini().invoke()` (loop-bound Google client). The worker is now pure-sync and reads its pre-computed, rerank-filtered context from the Send payload. The decision below describes the original in-worker retrieval.

### Decision 3: Milestone-level retrieval happens inside skillpath_worker, after fan-out

Because `skillpath_worker` is dispatched per-milestone via `Send()`, each worker already has exactly one milestone. The cleanest place to scope milestone memory is **inside the worker**: query = milestone title + objective, inject into `SKILLPATH_PROMPT`, and return the context keyed by `milestone_id`.

`user_id` must be added to each Send payload in `route_after_milestone_quick_review`, since workers only see Send-payload keys.

**Alternative considered:** Retrieve all milestone contexts in a single pre-fan-out node. Rejected per project decision — retrieval is co-located with the per-milestone worker that consumes it, matching how the fan-out already distributes work.

### Decision 4: Concurrent dict writes need a custom reducer

Parallel `skillpath_worker` instances each return `{"milestone_memory_contexts": {milestone_id: context}}`. To merge these without clobbering, `milestone_memory_contexts` is declared with a dict-merge reducer:

```python
def _merge_contexts(left, right):
    return {**(left or {}), **(right or {})}

milestone_memory_contexts: Annotated[dict[str, LearningMemoryContext], _merge_contexts]
```

`operator.add` (used by the existing list fields) cannot merge dicts, so a dedicated function is required.

### Decision 5: Load multi-skillpath SkillMasteryStates via the linked_skillpath_ids bridge

`retrieve_learning_memory()` returns `mastery_state=null` when no `skillpath_id` is passed — which is always the case for the planner. To still surface mastery data, bridge through the notes: collect all unique `linked_skillpath_ids` from the returned notes and batch-load `skill_mastery_states` for those IDs.

```python
all_skillpath_ids = {
    sid for note in context.relevant_notes for sid in (note.linked_skillpath_ids or [])
}
# also union from the typed buckets (error patterns, mastery signals, etc.)
if all_skillpath_ids:
    context.linked_mastery_states = await load_mastery_states_for_skillpaths(
        user_id, all_skillpath_ids, session
    )  # dict[skillpath_id, SkillMasteryState]
```

`LearningMemoryContext` gains one additive field:

```python
class LearningMemoryContext(BaseModel):
    # ... existing fields ...
    linked_mastery_states: dict[str, SkillMasteryState] = Field(default_factory=dict)
```

A new batch loader is required (`load_mastery_states_for_skillpaths`) — only single-key `get_skill_mastery_state` exists today. Populating the bridge inside `retrieve_learning_memory()` means every caller benefits, not just the planner.

**Alternative considered:** Accept `mastery_state=null` and rely on notes only. Rejected — notes reference skillpath IDs that have mastery data; ignoring it loses the "already mastered here" vs "struggled here" distinction at skillpath granularity.

### Decision 6: No Rerank Advisor for the planner

The Rerank Advisor narrows which notes shape a specific piece of content or feedback. The planner produces structure, not content. All 5 memory types contribute differently and non-competitively:

| Type | Structural decision it informs |
|---|---|
| `mastery_signal` | Skip or compress this milestone/skillpath |
| `error_pattern` | Expand or add remediation focus here |
| `background` | Adjust starting depth and assumed prerequisites |
| `preference_signal` | Adjust pacing and milestone granularity |
| `heuristic` | Shape skillpath ordering and progression style |

Passing the full `LearningMemoryContext` lets each type be read from its named bucket. No selection step is needed.

### Decision 7: user_id sourced from the Learning Director

`goal_spec`/`learning_profile` do not carry `user_id`. Add `user_id: str` to `PlannerState`, pass `resolved_user_id` in `_planner.invoke({..., "user_id": ...})`, and include `user_id` in each `skillpath_worker` Send payload.

## Risks / Trade-offs

**Sync node calling async retrieval** → Mitigation: use the proven `asyncio.run()` + `get_session()` wrapper from the content generation graph. The planner is already invoked via a lambda in the Learning Director.

**Reducer mistakenly set to operator.add** → Mitigation: explicit custom merge function; unit test that two concurrent worker writes both survive.

**user_id missing from Send payload** → Mitigation: first task wires `user_id` end-to-end (PlannerState → invoke → Send payload) before any retrieval task.

**Goal-level query too broad** → Mitigation: milestone-level retrieval inside each worker provides targeted context per milestone. Goal-level is intentionally macro.

**Milestone-level retrieval adds one DB call per worker** → Mitigation: retrieval is a fast DB call (vector + keyword + scope), not an LLM call; workers already run in parallel.

**Memory-absent learners (new users)** → `LearningMemoryContext` returns empty buckets and empty `linked_mastery_states` gracefully; prompts must handle empty context without degrading generation quality.

## Migration Plan

No DB migrations. One additive Pydantic field on `LearningMemoryContext` (`linked_mastery_states`, default empty). New planner state fields and a `retrieve_goal_memory` node; `skillpath_worker`, `route_after_milestone_quick_review`, and the milestone-stage prompts are modified. Learning Director passes `user_id`. The `evaluate` graph is untouched. Rollback: remove new state fields, the retrieval node, the Send-payload `user_id`, and prompt injections; the `linked_mastery_states` field can remain inert.
