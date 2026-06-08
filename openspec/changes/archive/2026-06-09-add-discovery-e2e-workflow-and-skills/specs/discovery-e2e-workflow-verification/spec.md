## ADDED Requirements

### Requirement: Full discovery workflow can be verified end to end
The system SHALL provide a gated test or smoke script that verifies the learner onboarding workflow from Discovery Agent conversation through roadmap and learning content persistence.

#### Scenario: Live workflow completes durable outputs
- **WHEN** the live discovery workflow verification is run with required Docker services and credentials
- **THEN** the system SHALL create or update a goal, create or update a learning profile, optionally create allowed memory notes, launch Learning Director, persist a roadmap, and persist generated learning content.

#### Scenario: Live workflow is gated
- **WHEN** normal non-live tests are run
- **THEN** the live discovery workflow verification SHALL NOT run unless an explicit environment flag is set.

---

### Requirement: Discovery workflow verifies source-of-truth entity persistence
The workflow verification SHALL confirm that Discovery Agent saves goal and learning profile entities through their source-of-truth paths.

#### Scenario: Goal is persisted
- **WHEN** the Discovery Agent has collected and confirmed the learner goal
- **THEN** the verification SHALL confirm a persisted `GoalSpec` exists for the test user with non-empty `title`, `description`, `target_outcome`, `deadline`, `criteria`, and `constraints`.

#### Scenario: Learning profile is persisted
- **WHEN** the Discovery Agent has collected and confirmed the learner profile
- **THEN** the verification SHALL confirm a persisted `LearningProfile` exists for the test user with non-empty level, prior knowledge or weak-area signals, pace preference, confidence level, recap preference, examples-first preference, and overload risk.

---

### Requirement: Discovery workflow verifies memory write policy
The workflow verification SHALL confirm that discovery-authored memory notes are limited to durable preference and background context.

#### Scenario: Preference memory is written
- **WHEN** the learner gives a durable teaching preference during discovery
- **THEN** the verification SHALL confirm any discovery-authored memory note uses `memory_type` equal to `preference_signal` or `background`.

#### Scenario: Lifecycle memory types are not written
- **WHEN** the Discovery Agent writes memory during onboarding
- **THEN** the verification SHALL confirm it does not write `error_pattern`, `mastery_signal`, or `heuristic`.

---

### Requirement: Discovery workflow verifies Learning Director handoff
The workflow verification SHALL confirm that Discovery Agent launches Learning Director only after required entities are confirmed.

#### Scenario: Handoff creates roadmap job
- **WHEN** required goal and profile data are confirmed
- **THEN** the Discovery Agent SHALL return `session_complete: true` with a non-empty `roadmap_job_id` or equivalent async task identifier.

#### Scenario: Roadmap and content are persisted after handoff
- **WHEN** Learning Director completes the handoff task
- **THEN** the verification SHALL confirm a roadmap exists for the test user with at least one milestone, one skillpath, and one generated learning content item.

---

### Requirement: Live workflow provides observation guidance
The live workflow verification SHALL print or document what the tester should inspect in API responses, DB state, agent-server logs, and LangSmith traces.

#### Scenario: LangSmith trace observation
- **WHEN** LangSmith tracing is enabled for a live workflow run
- **THEN** the guidance SHALL tell the tester to look for Discovery Agent calls to goal, learning profile, learning memory, and async task tools.

#### Scenario: Failure output is actionable
- **WHEN** the live workflow verification fails before completion
- **THEN** it SHALL print the current conversation id, user id, last response, and suggested logs to inspect.
