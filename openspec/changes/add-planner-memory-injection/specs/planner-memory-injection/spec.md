## ADDED Requirements

### Requirement: Planner receives user_id
The planner graph SHALL accept `user_id` as part of its input. `user_id` is not present on `goal_spec` or `learning_profile`, so the Learning Director SHALL pass it explicitly (from its `resolved_user_id`) when invoking the planner. `user_id` SHALL also be included in every `Send(...)` payload that dispatches a `skillpath_worker`, because workers only receive the keys placed in their Send payload.

#### Scenario: user_id available for goal-level retrieval
- **WHEN** the Learning Director invokes the planner graph
- **THEN** `user_id` is accessible within `PlannerState` for the goal-level retrieval node

#### Scenario: user_id available inside each skillpath worker
- **WHEN** `route_after_milestone_quick_review` dispatches a `skillpath_worker` per milestone
- **THEN** each Send payload includes `user_id` so the worker can run milestone-level retrieval

---

### Requirement: Scope limited to the active generate_roadmap graph
The planner memory injection SHALL apply only to the active `generate_roadmap` graph (`build_planner_graph()`). The `evaluate` graph (`build_evaluate_graph`, `skillpath_review_worker`, `distribute_skillpath_review`, `merge_revised_skillpaths`) is not wired into any active path and SHALL NOT be modified by this change.

#### Scenario: Evaluate graph left untouched
- **WHEN** this change is implemented
- **THEN** no files under `app/langgraph/planner/graphs/evaluate/` are modified and no skillpath-level review node is added

---

### Requirement: Goal-level memory retrieved before milestone generation
The planner graph SHALL add a `retrieve_goal_memory` node that runs after `init_roadmap_context` and before `generate_milestone`. It SHALL retrieve a `LearningMemoryContext` using the goal title, description, and target outcome as the query, calling `memory_service.retrieve_learning_memory()` directly (not via MCP) with `skillpath_id=None`. The node SHALL be synchronous and wrap the async call using the `asyncio.run()` + `get_session()` pattern established in the content generation graph. The result SHALL be stored in `PlannerState.goal_memory_context`.

#### Scenario: Memory exists for the learner
- **WHEN** the planner starts and the learner has existing memory notes
- **THEN** `goal_memory_context` is populated with notes relevant to the goal before any milestone is generated

#### Scenario: No memory exists for the learner
- **WHEN** the planner starts and the learner has no existing memory notes
- **THEN** `goal_memory_context` is populated with empty buckets and the planner proceeds without error

---

### Requirement: generate_milestone uses goal-level memory
The `generate_milestone` node SHALL read `goal_memory_context` from state and use all five memory-type buckets to inform milestone structure decisions, injecting a formatted memory summary into `MILESTONE_PROMPT`.

#### Scenario: Learner has mastery signals
- **WHEN** `goal_memory_context.mastery_signals` is non-empty
- **THEN** `generate_milestone` skips or compresses milestones covering areas where mastery is already demonstrated

#### Scenario: Learner has active error patterns
- **WHEN** `goal_memory_context.active_error_patterns` is non-empty
- **THEN** `generate_milestone` includes or expands milestones targeting the concepts in those error patterns

#### Scenario: Learner has background notes
- **WHEN** `goal_memory_context.background_notes` is non-empty
- **THEN** `generate_milestone` adjusts starting depth and assumed prerequisites based on the learner's background

#### Scenario: Learner has preference signals
- **WHEN** `goal_memory_context.relevant_notes` contains preference_signal notes
- **THEN** `generate_milestone` adjusts milestone granularity and pacing to match the learner's stated preferences

---

### Requirement: milestone_quick_review shares goal-level memory context
The `milestone_quick_review` node SHALL read `goal_memory_context` from the same state field written by `retrieve_goal_memory`. It SHALL NOT re-retrieve memory. It SHALL use this context to validate that personalization decisions made in `generate_milestone` are preserved and not overridden by generic quality standards.

#### Scenario: Generation intentionally skipped a milestone due to mastery
- **WHEN** `milestone_quick_review` evaluates milestones that omit a topic where the learner has a mastery signal
- **THEN** the review does not flag the omission as a structural defect requiring revision

#### Scenario: Generation expanded an area due to error patterns
- **WHEN** `milestone_quick_review` evaluates milestones with extra focus in an area with active error patterns
- **THEN** the review does not flag the extra remediation as over-scoping

---

### Requirement: revise_milestones shares goal-level memory context
The `revise_milestones` node SHALL read `goal_memory_context` from state (no re-retrieval) and inject it into `REVISE_MILESTONE_PROMPT`, so that revisions preserve memory-driven personalization rather than regenerating generic milestones.

#### Scenario: Revision preserves mastery-driven omissions
- **WHEN** `revise_milestones` regenerates milestones after a failed quick review
- **THEN** the revised milestones still reflect the learner's mastery signals, error patterns, background, and preferences

---

### Requirement: Milestone-level memory retrieved inside the skillpath fan-out worker
Milestone-level retrieval SHALL happen inside `skillpath_worker`, after fan-out, because the graph dispatches one `skillpath_worker` per milestone via `Send()`. Each worker SHALL retrieve a `LearningMemoryContext` using its milestone's title and objective as the query, inject it into `SKILLPATH_PROMPT`, and return its result keyed by `milestone_id`. The retrieval SHALL use the same synchronous `asyncio.run()` + `get_session()` pattern.

#### Scenario: Retrievals run per milestone after fan-out
- **WHEN** the fan-out dispatches N `skillpath_worker` instances
- **THEN** each worker performs its own milestone-scoped memory retrieval, producing N retrievals total

#### Scenario: No relevant memory for a milestone
- **WHEN** a milestone's topic has no related memory notes for the learner
- **THEN** that worker's `milestone_memory_contexts` entry contains empty buckets and skillpath generation proceeds without error

---

### Requirement: skillpath_worker uses milestone-level memory
The `skillpath_worker` node SHALL use the milestone-scoped `LearningMemoryContext` it retrieved to inform which skillpaths to include, which concepts to focus on, and how to sequence skillpaths within the milestone.

#### Scenario: Milestone has scoped error patterns
- **WHEN** the milestone-scoped context's `active_error_patterns` is non-empty
- **THEN** the worker includes targeted remediation skillpaths for the concepts in those error patterns

#### Scenario: Milestone has scoped mastery signals
- **WHEN** the milestone-scoped context's `mastery_signals` is non-empty
- **THEN** the worker skips or fast-tracks skillpaths covering already-mastered concepts

---

### Requirement: Concurrent milestone contexts merged via a reducer
`PlannerState.milestone_memory_contexts` SHALL be declared with a dict-merge reducer so that the parallel `skillpath_worker` instances can each write their own `{milestone_id: context}` entry without overwriting one another. `operator.add` SHALL NOT be used (it cannot merge dicts); a custom merge function (`lambda left, right: {**left, **right}`) SHALL be used instead.

#### Scenario: Parallel workers write distinct milestone keys
- **WHEN** multiple `skillpath_worker` instances return `milestone_memory_contexts` entries concurrently
- **THEN** the reducer merges all entries into a single dict keyed by `milestone_id` with no lost writes

---

### Requirement: Linked SkillMasteryStates loaded via linked_skillpath_ids bridge
Because `retrieve_learning_memory()` only loads `mastery_state` when a `skillpath_id` is supplied, and the planner has none at goal- or milestone-level, the service SHALL bridge through the notes: after retrieving notes, it SHALL collect all unique `linked_skillpath_ids` and batch-load their `SkillMasteryState` rows into a new `LearningMemoryContext.linked_mastery_states` field (keyed by `skillpath_id`).

#### Scenario: Notes reference prior skillpaths with mastery data
- **WHEN** retrieved notes carry `linked_skillpath_ids` that have `skill_mastery_states` rows
- **THEN** `linked_mastery_states` is populated with those rows so the planner can see prior per-skillpath mastery

#### Scenario: Notes have no linked skillpaths
- **WHEN** no retrieved note carries a `linked_skillpath_ids` value
- **THEN** `linked_mastery_states` is an empty dict and no mastery query is issued

---

### Requirement: PlannerState extended with memory context fields
`PlannerState` SHALL include:
- `user_id: str` — passed in by the Learning Director
- `goal_memory_context: Optional[LearningMemoryContext]` — populated once by `retrieve_goal_memory`
- `milestone_memory_contexts: Annotated[dict[str, LearningMemoryContext], _merge_contexts]` — populated per milestone inside `skillpath_worker`, keyed by `milestone_id`

#### Scenario: Fields default empty before retrieval runs
- **WHEN** the planner graph starts
- **THEN** `goal_memory_context` is `None` and `milestone_memory_contexts` is an empty dict until the retrieval steps execute

---

### Requirement: No Rerank Advisor used in planner memory path
The planner memory injection SHALL NOT invoke the Memory Rerank Advisor. The full `LearningMemoryContext` SHALL be passed directly to planner node prompts. No new rerank purpose enum values are required.

#### Scenario: Memory injected without rerank
- **WHEN** the planner retrieves memory at goal-level or milestone-level
- **THEN** the full `LearningMemoryContext` is stored in state and injected into prompts without a rerank step
