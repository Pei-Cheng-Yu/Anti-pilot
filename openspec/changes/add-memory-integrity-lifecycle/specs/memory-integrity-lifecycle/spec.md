## ADDED Requirements

### Requirement: Prevent Duplicate Memory Writes Across All Types
The system SHALL evaluate incoming learner memory writes against existing related notes before creating a new `LearnerMemoryNote`.

#### Scenario: Duplicate error pattern
- **WHEN** an incoming error-pattern memory matches an unresolved existing error pattern by scope or concept overlap
- **THEN** the system updates or reinforces the existing note instead of creating an unnecessary duplicate

#### Scenario: Duplicate preference signal
- **WHEN** an incoming preference signal expresses the same learner preference as an existing active preference signal
- **THEN** the system updates the existing preference signal or skips the duplicate write

#### Scenario: Duplicate background note
- **WHEN** an incoming background note repeats an existing stable learner fact
- **THEN** the system updates or reuses the existing note instead of creating an unnecessary duplicate

### Requirement: Build Integrity Evidence Before Advisor Calls
The system SHALL build deterministic evidence for candidate duplicate or conflict decisions before invoking any optional LLM advisor.

#### Scenario: Candidate evidence built
- **WHEN** an incoming memory note is checked for integrity
- **THEN** the service computes evidence such as type compatibility, concept overlap, tag overlap, scope overlap, semantic similarity, status, recency, and salience

### Requirement: Use LLM Advisor As Bounded Recommendation
The system MAY use an LLM integrity advisor to recommend duplicate or conflict actions over a bounded candidate set, but the service MUST validate the advisor output before persistence.

#### Scenario: Advisor recommends merge
- **WHEN** the advisor recommends merging incoming memory into an existing candidate
- **THEN** the service validates that all target memory IDs were present in the candidate set before applying any merge

#### Scenario: Advisor returns invalid output
- **WHEN** the advisor returns invalid schema, unknown target IDs, or an unsupported action
- **THEN** the service ignores the invalid recommendation and falls back to deterministic integrity behavior

### Requirement: Merge Existing Duplicate Memory Notes
The system SHALL provide an explicit merge operation that combines duplicate memory notes into a primary note while preserving evidence.

#### Scenario: Merge duplicate notes
- **WHEN** duplicate memory notes are merged into a primary note
- **THEN** the primary note retains the combined tags, linked concepts, linked skillpaths, linked contents, evidence attempt IDs, salience, and refreshed search/embedding data

### Requirement: Resolve Memory Conflicts Conservatively
The system SHALL provide conflict handling that prefers watch, resolved, scoped, or linked states over destructive deletion.

#### Scenario: Mastery signal conflicts with error pattern
- **WHEN** a strong mastery signal conflicts with an active error pattern for the same concept and supporting evidence exists
- **THEN** the service can move the error pattern to watch or resolved while preserving evidence attempt links

#### Scenario: Preference conflict
- **WHEN** two preference signals conflict
- **THEN** the service can keep the newer or stronger-evidence preference active and downgrade the weaker conflicting note to watch

### Requirement: Preserve Memory Service Authority
The system MUST ensure that all memory integrity decisions are applied through service validation and service-owned database writes.

#### Scenario: Advisor cannot write directly
- **WHEN** an LLM advisor recommends an integrity action
- **THEN** only the memory service validates and persists the resulting change
