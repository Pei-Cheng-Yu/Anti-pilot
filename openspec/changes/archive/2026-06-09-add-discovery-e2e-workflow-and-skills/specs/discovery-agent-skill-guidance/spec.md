## ADDED Requirements

### Requirement: Discovery Agent has dedicated skill guidance
The system SHALL provide a dedicated Discovery Agent skill or runbook that defines the agent's mission, session phases, tool policy, memory policy, response shape, and handoff checklist.

#### Scenario: Skill guidance exists
- **WHEN** a developer inspects the Discovery Agent package
- **THEN** they SHALL find a Discovery Agent skill or runbook file that explains the expected onboarding flow.

#### Scenario: Skill guidance can be loaded by the agent
- **WHEN** DeepAgents skill loading is enabled for the Discovery Agent
- **THEN** the Discovery Agent SHALL include the discovery skill directory in its construction.

---

### Requirement: Discovery Agent skill documents allowed MCP tools
The Discovery Agent skill SHALL document the exact MCP tool names the agent is allowed to use.

#### Scenario: Allowed tools are listed
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL list `goal_get_goal`, `goal_save_goal`, `learning_profile_get_learning_profile`, `learning_profile_save_learning_profile`, `learning_memory_retrieve_learning_memory`, `learning_memory_get_skill_mastery_state`, and `learning_memory_add_memory_note`.

#### Scenario: Prohibited tools are listed
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL state that Discovery Agent must not call planner/content generation directly, record coding attempts, update/delete/resolve memory notes, or write code-correction-owned memory lifecycle types.

---

### Requirement: Discovery Agent skill documents source-of-truth entities
The Discovery Agent skill SHALL explain that goals and learning profiles are source-of-truth entities, not memory-note duplicates.

#### Scenario: Goal fields documented
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL list the required `GoalSpec` fields: `title`, `description`, `target_outcome`, `deadline`, `criteria`, and `constraints`.

#### Scenario: Profile fields documented
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL list the required `LearningProfile` fields: `baseline_level`, `prior_knowledges`, `weak_areas`, `pace_preference`, `confidence_level`, `needs_recap`, `prefers_examples_first`, and `overload_risk`.

---

### Requirement: Discovery Agent skill documents memory policy
The Discovery Agent skill SHALL explain when discovery may write durable memory and which memory types are allowed.

#### Scenario: Allowed memory types documented
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL state that discovery-authored memory notes may only be `preference_signal` or `background`.

#### Scenario: Memory write examples documented
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL include examples of durable preference and background signals that should be written as memory notes.

---

### Requirement: Discovery Agent skill documents handoff behavior
The Discovery Agent skill SHALL describe when and how to launch Learning Director.

#### Scenario: Handoff checklist documented
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL state that Learning Director handoff occurs only after goal and profile entities are confirmed and saved.

#### Scenario: Response after handoff documented
- **WHEN** a developer reads the Discovery Agent skill
- **THEN** it SHALL state that the agent response after handoff includes `session_complete: true`, a roadmap job id, and a roadmap status.
