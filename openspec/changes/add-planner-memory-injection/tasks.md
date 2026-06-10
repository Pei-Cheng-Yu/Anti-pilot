## 1. Wire user_id into the planner end-to-end

- [x] 1.1 Add `user_id: str` to `PlannerState` in `backend/app/langgraph/planner/schema/state.py`
- [x] 1.2 Update the Learning Director to pass `resolved_user_id` in `_planner.invoke({"goal_spec": ..., "learning_profile": ..., "user_id": resolved_user_id})` (`learning_director/agent.py:274`)
- [x] 1.3 Add `"user_id": state["user_id"]` to every `Send("skillpath_worker", {...})` payload in `route_after_milestone_quick_review` (`generate_roadmap/nodes.py:159-164`)
- [x] 1.4 Write a unit test confirming `user_id` is accessible in `generate_milestone` and inside `skillpath_worker`

## 2. Extend PlannerState with memory fields and reducer

- [x] 2.1 Add `goal_memory_context: Optional[LearningMemoryContext]` to `PlannerState`
- [x] 2.2 Define `_merge_contexts(left, right)` returning `{**(left or {}), **(right or {})}` in `state.py`
- [x] 2.3 Add `milestone_memory_contexts: Annotated[dict[str, LearningMemoryContext], _merge_contexts]` to `PlannerState`
- [x] 2.4 Import `LearningMemoryContext` and `RetrieveLearningMemoryInput` into the planner schema/nodes module
- [x] 2.5 Write a unit test confirming two concurrent `{milestone_id: context}` writes both survive the reducer

## 3. Extend LearningMemoryContext with linked mastery states (bridge)

- [x] 3.1 Add `linked_mastery_states: dict[str, SkillMasteryState] = Field(default_factory=dict)` to `LearningMemoryContext` in `app/schema/entities.py`
- [x] 3.2 Add `load_mastery_states_for_skillpaths(user_id, skillpath_ids, session) -> dict[str, SkillMasteryState]` batch loader in `learning_memory.py`
- [x] 3.3 In `retrieve_learning_memory()`, after note retrieval, collect unique `linked_skillpath_ids` from all note buckets and populate `context.linked_mastery_states` via the batch loader
- [x] 3.4 Write a unit test: notes with `linked_skillpath_ids` → correct mastery states loaded and attached
- [x] 3.5 Write a unit test: notes with no `linked_skillpath_ids` → `linked_mastery_states` is empty dict, no DB query issued

## 4. Add the goal-level retrieval node

- [x] 4.1 Add `retrieve_goal_memory(state)` in `generate_roadmap/nodes.py` — sync node wrapping `asyncio.run()` + `async with get_session()`, calling `memory_service.retrieve_learning_memory()` with a `RetrieveLearningMemoryInput` built from goal title + description + target outcome and `skillpath_id=None`
- [x] 4.2 Store the result in `state["goal_memory_context"]`
- [x] 4.3 Handle empty context gracefully (no notes → empty buckets, no error)
- [x] 4.4 Wire the node into `build_planner_graph()` between `init_roadmap_context` and `generate_milestone` (`generate_roadmap/graph.py`)
- [x] 4.5 Write a unit test with a mock memory service confirming the node populates `goal_memory_context`
- [x] 4.6 Write a unit test confirming the node handles an empty `LearningMemoryContext` without raising

## 5. Inject goal-level memory into generate_milestone

- [x] 5.1 Add a `_format_memory_for_prompt(context: LearningMemoryContext) -> str` util rendering each bucket with clear labels (mastery signals, error patterns, background, preferences, heuristics, linked mastery states)
- [x] 5.2 Read `goal_memory_context` in `generate_milestone` and inject the formatted summary into `MILESTONE_PROMPT`
- [x] 5.3 Update `MILESTONE_PROMPT` instructions to describe how each memory type affects milestone decisions (skip/compress mastery, expand error patterns, adjust depth from background, adjust pacing from preferences)
- [x] 5.4 Write a unit test confirming the formatted memory string appears in the prompt sent to the LLM

## 6. Inject goal-level memory into milestone_quick_review

- [x] 6.1 Read `goal_memory_context` in `milestone_quick_review` (no re-retrieval) and inject into `QUICK_REVIEW_PROMPT`
- [x] 6.2 Update review instructions to not flag memory-driven omissions/expansions as structural defects
- [x] 6.3 Write a unit test confirming `milestone_quick_review` reads from state and does not call the memory service

## 7. Inject goal-level memory into revise_milestones

- [x] 7.1 Read `goal_memory_context` in `revise_milestones` (no re-retrieval) and inject into `REVISE_MILESTONE_PROMPT`
- [x] 7.2 Update revision instructions to preserve memory-driven personalization across revisions
- [x] 7.3 Write a unit test confirming revised milestones still reflect injected memory and the node does not call the memory service

## 8. Milestone-level retrieval + injection inside skillpath_worker

- [x] 8.1 In `skillpath_worker`, build a `RetrieveLearningMemoryInput` from `milestone.title` + `milestone.objective` and retrieve via the same sync `asyncio.run()` + `get_session()` wrapper
- [x] 8.2 Inject the formatted milestone-scoped memory into `SKILLPATH_PROMPT` (reuse `_format_memory_for_prompt`)
- [x] 8.3 Update `SKILLPATH_PROMPT` to describe how each memory type affects skillpath decisions (remediation skillpaths for error patterns, skip/fast-track mastered concepts)
- [x] 8.4 Return `{"skillpath_drafts": drafts, "milestone_memory_contexts": {milestone.milestone_id: context}}` from the worker
- [x] 8.5 Write a unit test confirming milestone-scoped memory appears in the skillpath prompt
- [x] 8.6 Write a unit test confirming N workers produce N entries in `milestone_memory_contexts` keyed by milestone_id
- [x] 8.7 Write a unit test confirming a milestone with no memory yields empty buckets without error

## 9. Verification and documentation

- [x] 9.1 Run a full planner graph integration test with a learner who has existing memory notes — confirm generated milestones and skillpaths reflect the memory context *(test_live_planner_injects_predefined_memory, live, real embeddings — passes)*
- [ ] 9.2 Run a full planner graph integration test with a new learner (no memory) — confirm output is equivalent to current baseline
- [ ] 9.3 Verify in LangSmith that `goal_memory_context` and `milestone_memory_contexts` appear in the graph state trace
- [x] 9.4 Confirm the `evaluate` graph files were not modified
- [x] 9.5 Update `docs/five-layer-memory-access.md` — Planner Graph row now shows read access to all 5 memory types and `linked_mastery_states`
- [x] 9.6 Update `docs/system-interaction-memory-flow.md` — Planner Graph section now shows goal-level retrieval (pre-generation) and milestone-level retrieval (in worker)
