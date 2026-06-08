## ADDED Requirements

### Requirement: Public Memory Service Boundary
The system SHALL provide a public memory service boundary for durable learner memory operations used by MCP tools, API routes, services, and future agents.

#### Scenario: Durable memory write
- **WHEN** a caller requests a durable learner memory note write through the public memory service
- **THEN** the system applies the memory integrity flow before creating, updating, merging, skipping, or flagging memory notes

#### Scenario: Memory context retrieval
- **WHEN** a caller requests learner memory context through the public memory service
- **THEN** the system returns the existing `LearningMemoryContext` contract with mastery state, recent attempts, grouped memory notes, and relevant notes

#### Scenario: Attempt consolidation
- **WHEN** a caller records a coding problem attempt through the public memory service
- **THEN** the system persists the attempt, updates mastery state, and consolidates durable memory through the existing integrity-protected write path

### Requirement: MCP Tools Use Public Memory Service
The system SHALL route memory MCP tool operations through the public memory service boundary.

#### Scenario: MCP add memory note
- **WHEN** an agent calls the MCP `add_memory_note` tool
- **THEN** the tool delegates to the public memory service write method rather than directly creating database rows or bypassing integrity checks

#### Scenario: MCP generate hint
- **WHEN** an agent calls the MCP `generate_memory_aware_hint` tool
- **THEN** the tool delegates to the public memory service hint method so retrieval, rerank, and hint validation stay behind one service boundary

### Requirement: Existing Memory Workflows Are Adapted
The system SHALL audit currently implemented memory-facing workflows and adapt public callers to the public memory service boundary.

#### Scenario: Current memory write workflow
- **WHEN** an existing workflow creates or reinforces durable learner memory notes
- **THEN** the workflow calls the public memory service boundary or an internal helper that is reachable only through that boundary

#### Scenario: Current memory retrieval workflow
- **WHEN** an existing workflow retrieves learner memory for code correction, content generation, hint generation, or future agent use
- **THEN** the workflow calls the public memory service boundary or a documented internal helper owned by that boundary

#### Scenario: Workflow intentionally remains internal
- **WHEN** a lower-level helper remains outside the public facade
- **THEN** implementation documentation identifies it as internal and tests verify public callers do not use it directly

### Requirement: Discovery Agent Memory Contract
The system SHALL define how future discovery agents update goal, learning profile, and durable memory without duplicating source-of-truth data.

#### Scenario: Goal and profile are source of truth
- **WHEN** a discovery agent learns the learner's goal, baseline, weak areas, pace, or constraints
- **THEN** the agent updates goal and learning-profile services as source-of-truth structured entities

#### Scenario: Durable teaching fact becomes memory
- **WHEN** a discovery agent identifies a stable preference or background fact that should influence future teaching
- **THEN** the agent writes a `preference_signal` or `background` memory note through the public memory service

#### Scenario: Temporary onboarding answer is not memory
- **WHEN** a discovery agent receives a transient answer that is only needed for the current conversation
- **THEN** the agent does not create a durable learner memory note for that answer

### Requirement: Direct Model Writes Are Not Public API
The system MUST keep direct `LearnerMemoryNoteModel` creation and mutation outside agent-facing and MCP-facing code paths.

#### Scenario: Future memory consumer
- **WHEN** a new agent-facing or API-facing feature needs to persist learner memory
- **THEN** it uses the public memory service boundary rather than directly mutating `LearnerMemoryNoteModel`
