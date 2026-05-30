## ADDED Requirements

### Requirement: Planner emits roadmap metadata
The generate-roadmap planner SHALL include a populated `RoadmapItem` in its final state whenever planning succeeds with generated milestones and skillpaths.

#### Scenario: Successful planner output includes roadmap item
- **WHEN** the planner completes roadmap generation for a valid goal and learning profile
- **THEN** the final state includes a non-null `roadmap` with `roadmap_id`, `title`, `version`, `summary`, `target_outcome`, and `assumptions`

### Requirement: Roadmap metadata is deterministic
The planner SHALL construct initial roadmap metadata from existing planner inputs and outputs without requiring an additional LLM call.

#### Scenario: Roadmap item is derived from planner state
- **WHEN** the planner finalizes generated skillpaths
- **THEN** the roadmap item uses the planner roadmap UUID, goal title, goal target outcome, generated milestone count, generated skillpath count, and conservative learner-profile assumptions

### Requirement: Planner assumptions are conservative
The planner SHALL avoid blindly copying all learner prior knowledge into roadmap assumptions.

#### Scenario: Assumptions summarize relevant declared context
- **WHEN** the planner builds roadmap assumptions
- **THEN** assumptions summarize stated constraints, baseline level, weak areas, and pace preference without claiming unrelated prior knowledge is directly relevant
