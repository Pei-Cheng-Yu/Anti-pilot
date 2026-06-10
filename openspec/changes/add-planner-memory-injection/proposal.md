## Why

The Planner Graph generates roadmaps with no awareness of who the learner is — it receives only a goal spec and learning profile, meaning every roadmap starts from scratch regardless of what the learner already knows or struggles with. Injecting learner memory at the right granularity lets the planner generate a personalized structure from the first pass, rather than producing a generic draft.

## What Changes

- Add a `retrieve_goal_memory` node to the active `generate_roadmap` graph, before `generate_milestone`, using the goal title + description + target outcome as the query
- Retrieve milestone-level memory **inside `skillpath_worker`** (after the per-milestone `Send()` fan-out), using each milestone's title and objective as the query
- Extend `PlannerState` with `user_id`, `goal_memory_context`, and a reducer-merged `milestone_memory_contexts`
- Inject goal-level memory into `generate_milestone`, `milestone_quick_review`, and `revise_milestones`; inject milestone-level memory into `skillpath_worker` — so the only active review/revision (milestone-level) preserves memory-driven personalization
- Bridge to `SkillMasteryState` via notes' `linked_skillpath_ids` (the planner has no `skillpath_id`), adding a `linked_mastery_states` field to `LearningMemoryContext`
- Pass `user_id` from the Learning Director into the planner invocation and into each `skillpath_worker` Send payload
- No Rerank Advisor — full `LearningMemoryContext` is injected directly; all 5 types drive different structural decisions
- **Out of scope:** the dead `evaluate` graph (`skillpath_review_worker`) is not modified or wired in

## Capabilities

### New Capabilities

- `planner-memory-injection`: Goal-level and milestone-level memory retrieval inside the active Planner Graph, injected into state and prompts to personalize roadmap structure

### Modified Capabilities

- none

## Impact

- `backend/app/langgraph/planner/schema/state.py` — add `user_id`, `goal_memory_context`, `milestone_memory_contexts` (with dict-merge reducer) to `PlannerState`
- `backend/app/langgraph/planner/graphs/generate_roadmap/nodes.py` — add `retrieve_goal_memory`; add `user_id` to Send payloads; memory-aware prompt injection in `generate_milestone`, `milestone_quick_review`, `revise_milestones`, `skillpath_worker`
- `backend/app/langgraph/planner/graphs/generate_roadmap/graph.py` — wire `retrieve_goal_memory` between `init_roadmap_context` and `generate_milestone`
- `backend/app/langgraph/planner/graphs/generate_roadmap/prompt.py` — memory sections in milestone and skillpath prompts
- `backend/app/langgraph/learning_director/agent.py` — pass `resolved_user_id` into the planner invocation
- `backend/app/schema/entities.py` — add additive `linked_mastery_states: dict[str, SkillMasteryState]` field to `LearningMemoryContext`
- `backend/app/services/learning_memory.py` — add `load_mastery_states_for_skillpaths()` batch loader; populate `linked_mastery_states` in `retrieve_learning_memory()`
- No DB schema changes, no MCP tool changes; the `evaluate` graph is untouched
- Reads from `learner_memory_notes`, `skill_mastery_states` (all existing tables)
