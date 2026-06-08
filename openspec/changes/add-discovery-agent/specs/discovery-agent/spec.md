## ADDED Requirements

### Requirement: Discovery Agent conducts multi-turn goal and profile collection
The Discovery Agent SHALL conduct a multi-turn conversation with the learner to collect a confirmed `GoalSpec` and `LearningProfile` before triggering roadmap generation. It SHALL ask one question at a time and offer structured options via `ui_hints` where appropriate.

#### Scenario: Agent resumes existing session
- **WHEN** a learner starts a conversation and they already have a saved goal and profile
- **THEN** the agent SHALL call `goal_get_goal` and `learning_profile_get_learning_profile` at the start and confirm with the learner whether the existing data is still current rather than starting from scratch

#### Scenario: Agent collects goal through conversation
- **WHEN** the learner has no existing goal or wants to update it
- **THEN** the agent SHALL ask targeted questions to extract the current `GoalSpec` fields (`title`, `description`, `target_outcome`, `deadline`, `criteria`, and `constraints`) and call `goal_save_goal` as soon as the required goal fields are confirmed

#### Scenario: Agent offers structured options
- **WHEN** the agent asks a question with a bounded set of reasonable answers
- **THEN** the response SHALL include `ui_hints` with `type` set to `"single_choice"` or `"multi_choice"` and a non-empty `options` list

#### Scenario: Agent collects profile through conversation
- **WHEN** goal is confirmed and profile is incomplete
- **THEN** the agent SHALL ask questions to extract the current `LearningProfile` fields (`baseline_level`, `prior_knowledges`, `weak_areas`, `pace_preference`, `confidence_level`, `needs_recap`, `prefers_examples_first`, and `overload_risk`) and call `learning_profile_save_learning_profile` as soon as the required profile fields are confirmed

---

### Requirement: Discovery Agent retrieves learner memory at session start
The Discovery Agent SHALL call `learning_memory_retrieve_learning_memory` at the start of each new discovery session to understand existing mastery, error patterns, and preferences before asking questions. It SHALL use this context to skip topics the learner already knows well and personalize its questions.

#### Scenario: Memory informs discovery questions
- **WHEN** retrieved memory shows the learner has strong mastery in a skill area
- **THEN** the agent SHALL acknowledge that prior knowledge and not ask basic questions about it

#### Scenario: No existing memory
- **WHEN** `learning_memory_retrieve_learning_memory` returns an empty context (new learner)
- **THEN** the agent SHALL proceed with full discovery without error

---

### Requirement: Discovery Agent writes preference and context memory notes
The Discovery Agent SHALL call `learning_memory_add_memory_note` with type `preference_signal` or `background` when the learner volunteers strong durable preferences or context during conversation. It SHALL NOT wait until session end; notes SHALL be written as signals are discovered. Goal and learning-profile entities SHALL remain the source of truth and SHALL NOT be duplicated wholesale into memory notes.

#### Scenario: Learner signals a strong preference
- **WHEN** the learner states a preference (e.g. "I hate math-heavy content", "I only have evenings free")
- **THEN** the agent SHALL call `learning_memory_add_memory_note` with memory type `preference_signal` and a concise note body before the next turn

#### Scenario: Learner provides durable background context
- **WHEN** the learner states durable context not already captured by `GoalSpec` or `LearningProfile` (e.g. "I built one Flask project before but never used async DB access")
- **THEN** the agent SHALL call `learning_memory_add_memory_note` with memory type `background` and a concise note body before the next turn

#### Scenario: Discovery does not write lifecycle-owned memory types
- **WHEN** the Discovery Agent writes a memory note
- **THEN** the memory type SHALL be either `preference_signal` or `background`
- **AND** the agent SHALL NOT write `error_pattern`, `mastery_signal`, or `heuristic` notes

#### Scenario: Note write does not block conversation
- **WHEN** `learning_memory_add_memory_note` is called
- **THEN** the agent SHALL continue the conversation without waiting for a confirmation from the learner

---

### Requirement: Discovery Agent returns structured DiscoveryResponse on every turn
Every agent response SHALL conform to the `DiscoveryResponse` schema: `message` (str, always present), `ui_hints` (optional UIHints object), `session_complete` (bool), `roadmap_job_id` (optional str), `roadmap_status` (optional str).

#### Scenario: Normal conversational turn
- **WHEN** the agent responds with a question or follow-up
- **THEN** `message` SHALL contain the conversational text, `ui_hints` SHALL be null, and `session_complete` SHALL be false

#### Scenario: Turn with option suggestions
- **WHEN** the agent offers the learner a choice
- **THEN** `ui_hints.type` SHALL be one of `"single_choice"`, `"multi_choice"`, `"text_input"`, or `"confirm"` and `ui_hints.options` SHALL be a non-empty list when type is `single_choice` or `multi_choice`

#### Scenario: JSON parse failure fallback
- **WHEN** the model emits a response that cannot be parsed as valid `DiscoveryResponse` JSON
- **THEN** the system SHALL wrap the raw text in `{"message": raw_text, "ui_hints": null, "session_complete": false}` and return that rather than raising an HTTP 500

---

### Requirement: Discovery Agent tool access is restricted to an explicit allowlist
The Discovery Agent SHALL only have access to the following mounted MCP tools: `goal_get_goal`, `goal_save_goal`, `learning_profile_get_learning_profile`, `learning_profile_save_learning_profile`, `learning_memory_retrieve_learning_memory`, `learning_memory_get_skill_mastery_state`, `learning_memory_add_memory_note`. All other MCP tools SHALL be filtered out at agent construction time.

#### Scenario: New MCP tool added to backend
- **WHEN** a new tool is added to the MCP server
- **THEN** the Discovery Agent SHALL NOT have access to it unless it is explicitly added to the allowlist in `discovery_agent/agent.py`

#### Scenario: Allowlist enforced at construction
- **WHEN** the Discovery Agent is constructed
- **THEN** the set of tools available to it SHALL exactly match the allowlist, no more and no less
