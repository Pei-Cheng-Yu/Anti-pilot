## 1. Add the ROADMAP_PLANNING rerank purpose

- [x] 1.1 Add `ROADMAP_PLANNING = "roadmap_planning"` to `MemoryRerankPurpose` in `app/schema/enums.py`
- [x] 1.2 Extend `build_rerank_advisor_prompt` in `app/advisors/memory_advisors.py` so the guidance line covers roadmap planning ("select notes that shape which skillpaths to include and how to scope this milestone")
- [x] 1.3 Write a unit test: a `MemoryRerankRequest(purpose=ROADMAP_PLANNING, ...)` validates and `build_rerank_advisor_prompt` includes planning guidance + the purpose value

## 2. Rerank inside skillpath_worker

- [x] 2.1 In `skillpath_worker`, fold the rerank into the existing async retrieval wrapper: after `retrieve_learning_memory`, call `memory_rerank_policy.arerank_memories(MemoryRerankRequest(purpose=ROADMAP_PLANNING, task_context=milestone.title+"\n"+milestone.objective, candidate_memories=context.relevant_notes, max_selected=5), advisor=_default_rerank_advisor())`
- [x] 2.2 Return both the full `context` and the rerank result from the wrapper
- [x] 2.3 Compute `selected_ids` from `rerank.selected_memories`; build a filtered context (notes whose `memory_id ∈ selected_ids`) for prompt formatting; if `selected_ids` is empty, use the full context
- [x] 2.4 Inject the filtered memory string into `SKILLPATH_PROMPT` (reuse `_format_memory_for_prompt`)
- [x] 2.5 Still store the full `context` in `milestone_memory_contexts[milestone_id]` (unchanged)
- [x] 2.6 Import `MemoryRerankRequest`, `MemoryRerankPurpose`, `memory_rerank_policy` (or expose `rerank_memories` via `memory_service`) in the planner nodes module

## 3. Tests

- [x] 3.1 Unit test: `skillpath_worker` with a fake rerank (monkeypatch `arerank_memories` / advisor) selecting a subset → only selected notes appear in the captured `SKILLPATH_PROMPT`; full context still stored in `milestone_memory_contexts`
- [x] 3.2 Unit test: rerank returns empty selection → prompt falls back to the full context (no crash, no worse than baseline)
- [x] 3.3 Unit test: flag disabled (`ENABLE_MEMORY_RERANK_ADVISOR` unset) → deterministic fallback (top-`max_selected` by order) used, no LLM invoked
- [x] 3.4 Confirm goal-level path unchanged: `retrieve_goal_memory` / `generate_milestone` still receive the full goal context (no rerank)

## 4. Verification

- [x] 4.1 Run the new unit tests — confirm they pass (isolated, no live LLM)
- [ ] 4.2 Update the live planner test (or add a case): with `ENABLE_MEMORY_RERANK_ADVISOR=1`, seed ≥6 topically-distinct notes and assert that at least two milestones produce **different** selected-note sets
- [ ] 4.3 In LangSmith: confirm a `ROADMAP_PLANNING` rerank run appears per milestone and the selected notes differ across milestones
- [x] 4.4 Update `docs/five-layer-memory-access.md` — note the milestone-level rerank step in the Planner Graph row
