## ADDED Requirements

### Requirement: Users can own multiple goals
The system SHALL allow a single user to own multiple learning goals. Each goal SHALL have a stable `goal_id` that is distinct from `user_id` and usable in service, API, MCP, and agent handoff contracts.

#### Scenario: Create second goal for same user
- **WHEN** a user who already has one saved goal creates a new Discovery goal
- **THEN** the system persists a second goal for the same user without overwriting the first goal

#### Scenario: Load goal by explicit goal id
- **WHEN** a service or MCP tool requests a goal with `user_id` and `goal_id`
- **THEN** the system returns only the matching goal owned by that user

#### Scenario: Reject cross-user goal access
- **WHEN** a user requests a `goal_id` owned by another user
- **THEN** the system rejects the request instead of returning or updating that goal

### Requirement: Learning profile remains user-level
The system SHALL keep exactly one learning profile per user for this change. Discovery and roadmap generation SHALL reuse the user's learning profile across multiple goals unless a future change introduces goal-specific profile overrides.

#### Scenario: New goal reuses existing profile
- **WHEN** a user with an existing learning profile creates a second goal
- **THEN** the system uses the existing user-level learning profile for roadmap generation

#### Scenario: Profile update applies to user
- **WHEN** Discovery saves a learning profile during a new goal conversation
- **THEN** the system updates the user's profile rather than creating a profile tied only to that goal

### Requirement: Each goal has one primary roadmap
The system SHALL associate generated roadmaps with a `goal_id`. For this change, each goal SHALL have at most one primary roadmap.

#### Scenario: Generate roadmap for new goal
- **WHEN** Discovery hands off a confirmed `goal_id` to Learning Director
- **THEN** Learning Director generates and persists a roadmap linked to that `goal_id`

#### Scenario: Prevent duplicate primary roadmap
- **WHEN** a primary roadmap already exists for a goal
- **THEN** the system does not create a second primary roadmap for that same goal

#### Scenario: Roadmap list distinguishes goals
- **WHEN** a user has multiple goals with roadmaps
- **THEN** roadmap responses include enough goal context to distinguish which roadmap belongs to which goal

### Requirement: Discovery conversations bind to goal context
The system SHALL bind a Discovery conversation to the goal it is creating or refining once a goal exists. Subsequent Discovery turns and agent-server invocations SHALL include the bound goal context when present.

#### Scenario: Conversation starts before goal exists
- **WHEN** a learner starts a create-new Discovery conversation
- **THEN** the conversation can be stored without a `goal_id`

#### Scenario: Conversation binds after goal save
- **WHEN** Discovery saves a new goal during the conversation
- **THEN** the system stores that `goal_id` on the Discovery conversation

#### Scenario: Subsequent turn uses bound goal
- **WHEN** the learner sends another message in a Discovery conversation that already has a `goal_id`
- **THEN** FastAPI passes the conversation's `goal_id` into the agent-server request context

### Requirement: Discovery handoff uses explicit goal context
The system SHALL require Discovery-to-Learning-Director roadmap handoff to identify the goal being planned. Learning Director SHALL load the goal by explicit `goal_id` and load the learning profile by `user_id`.

#### Scenario: Handoff includes goal id
- **WHEN** Discovery starts roadmap generation
- **THEN** the handoff instructions or runtime context include the current `goal_id`

#### Scenario: Missing goal id prevents handoff
- **WHEN** Discovery tries to start roadmap generation without a saved or bound `goal_id`
- **THEN** the system prevents handoff and returns a learner-facing request to finish goal confirmation
