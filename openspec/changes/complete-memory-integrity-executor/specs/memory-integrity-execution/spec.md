## ADDED Requirements

### Requirement: Shared memory writes apply integrity decisions
The system SHALL apply validated memory integrity decisions through the shared learning-memory write path used by direct memory writes and coding-attempt consolidation.

#### Scenario: New memory is created
- **WHEN** a memory write proposal has no matching integrity candidates or receives `create_new`
- **THEN** the system creates a new learner memory note from the proposal

#### Scenario: Existing memory is updated
- **WHEN** a memory write proposal receives `update_existing` with one valid target memory ID
- **THEN** the system reinforces the target memory note with incoming tags, concepts, scope, evidence, salience, and refreshed retrieval indexes

#### Scenario: Duplicate memory is skipped
- **WHEN** a memory write proposal receives `skip_duplicate` with one valid target memory ID
- **THEN** the system returns the target memory note without creating a new note or mutating the target note

#### Scenario: Scoped memory is kept separately
- **WHEN** a memory write proposal receives `keep_both_scoped` with valid related target memory IDs
- **THEN** the system creates a new memory note and leaves the related target notes unchanged

### Requirement: Merge decisions are executable
The system SHALL execute `merge` decisions safely without creating extra duplicate notes.

#### Scenario: Merge with one target reinforces target
- **WHEN** a memory write proposal receives `merge` with exactly one valid target memory ID
- **THEN** the system treats the proposal as an update to the target memory note

#### Scenario: Merge with multiple targets resolves duplicates
- **WHEN** a memory write proposal receives `merge` with multiple valid target memory IDs of the same memory type
- **THEN** the system merges duplicate target notes into one primary note, marks duplicate target notes as `resolved`, adds incoming evidence to the primary note, and refreshes retrieval indexes

#### Scenario: Merge rejects unsafe targets
- **WHEN** a merge decision references unknown, cross-user, or incompatible memory target IDs
- **THEN** the system rejects the advisor decision and falls back to safe deterministic behavior

### Requirement: Conflict decisions are conservative
The system SHALL execute `flag_conflict` decisions without deleting learner memory.

#### Scenario: Conflict creates incoming note and downgrades target
- **WHEN** a memory write proposal receives `flag_conflict` with valid target memory IDs
- **THEN** the system creates the incoming memory note, marks conflicting target notes as `watch`, lowers their salience conservatively, and keeps both sides available for future retrieval

#### Scenario: Conflict rejects unsafe targets
- **WHEN** a conflict decision references unknown or cross-user memory target IDs
- **THEN** the system rejects the advisor decision and falls back to safe deterministic behavior

### Requirement: Advisor field updates are bounded
The system SHALL apply only validated advisor-provided `title` and `summary` updates during memory integrity execution.

#### Scenario: Safe title and summary are applied
- **WHEN** a validated advisor decision includes non-empty `title` or `summary` field updates within configured length limits
- **THEN** the system applies those updates to the memory note selected by the executed action and refreshes retrieval indexes

#### Scenario: Unsafe field updates are ignored
- **WHEN** a validated advisor decision includes field updates for identity, ownership, type, status, salience, evidence, embedding, search text, or timestamps
- **THEN** the system ignores those unsafe field updates and preserves deterministic service-owned values

### Requirement: Implementation follows TDD
The system SHALL add or update tests before production code for each integrity execution behavior.

#### Scenario: Action behavior is introduced test-first
- **WHEN** implementation begins for a memory integrity action
- **THEN** a failing test demonstrating the expected action behavior is added and observed before production code is changed

#### Scenario: Live advisor proof remains bounded
- **WHEN** live LLM smoke tests are run with memory advisor flags enabled
- **THEN** tests verify advisor invocation, target-ID bounds, and service-owned DB mutation behavior without relying on exact advisor wording
