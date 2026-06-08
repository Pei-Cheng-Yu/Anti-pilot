## ADDED Requirements

### Requirement: Customization uses explicit roadmap and milestone context
The system SHALL support milestone-scoped roadmap customization through endpoints or agent invocations that include explicit `roadmap_id` and `milestone_id` context. The system MUST NOT require the agent to infer the active roadmap or milestone from a user's freeform text.

#### Scenario: Customize milestone from roadmap UI
- **WHEN** the frontend submits a customization request from a specific milestone UI
- **THEN** FastAPI passes the corresponding `roadmap_id` and `milestone_id` to the customization service or agent

#### Scenario: Reject missing milestone context
- **WHEN** a milestone-scoped customization request omits `milestone_id`
- **THEN** the system rejects the request or asks the learner to choose a milestone before applying changes

#### Scenario: Reject cross-user roadmap access
- **WHEN** a user submits customization for a roadmap they do not own
- **THEN** the system rejects the request instead of exposing or modifying roadmap data

### Requirement: Roadmap Customizer has narrow write authority
The system SHALL use a narrow Roadmap Customizer boundary for roadmap edits. The customizer MAY reason about the requested change, but persistence SHALL go through roadmap services that validate ownership, allowed fields, and downstream effects.

#### Scenario: Update milestone through service validation
- **WHEN** the customizer proposes changes to a milestone
- **THEN** the roadmap service validates ownership and updates only allowed milestone fields

#### Scenario: Mark affected skillpaths for regeneration
- **WHEN** a milestone change affects existing skillpaths or content
- **THEN** the system marks affected skillpaths for revision or regeneration instead of silently leaving stale generated content

#### Scenario: Customizer cannot write goals or profiles
- **WHEN** a customization agent is created
- **THEN** its tool allowlist excludes goal writes, learning profile writes, and Discovery memory writes

### Requirement: Customization returns learner-facing status
The system SHALL return a structured learner-facing response after a customization request. The response SHALL indicate whether the milestone was updated, whether downstream skillpaths need regeneration, and whether any follow-up choice is needed.

#### Scenario: Successful milestone update
- **WHEN** a customization request is accepted and applied
- **THEN** the response confirms the milestone update and identifies any affected downstream skillpaths

#### Scenario: Ambiguous customization request
- **WHEN** a customization request is too vague to apply safely within the selected milestone
- **THEN** the response asks one focused follow-up question instead of applying an inferred change

### Requirement: Freeform cross-goal chatbot is deferred
The system SHALL NOT introduce a general chatbot that chooses among unrelated goals or roadmaps in this change. Goal creation and roadmap customization SHALL be entered through explicit UI context.

#### Scenario: User starts new goal from create-new UI
- **WHEN** the learner enters the create-new flow
- **THEN** the system treats the conversation as a new goal flow rather than attempting to customize an existing roadmap

#### Scenario: User customizes from roadmap UI
- **WHEN** the learner enters the customize flow from a roadmap or milestone
- **THEN** the system treats the conversation as scoped to that roadmap or milestone rather than creating a new goal
