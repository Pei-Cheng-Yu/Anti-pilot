## ADDED Requirements

### Requirement: Generate Memory-Aware Hints
The system SHALL provide a hint service that accepts learner, task, code, and optional validation context and returns a structured hint response informed by retrieved learner memory.

#### Scenario: Hint uses relevant error pattern
- **WHEN** a hint is requested for a task whose concepts overlap an active learner error pattern
- **THEN** the hint response includes a hint focused on that pattern and references the used memory ID in structured metadata

#### Scenario: Hint works without memory
- **WHEN** a hint is requested and no relevant learner memory is retrieved
- **THEN** the hint service returns a valid general hint response without failing

### Requirement: Support Progressive Hint Levels
The system SHALL support multiple hint levels so callers can request progressively stronger help without revealing the full solution by default.

#### Scenario: Low-spoiler hint
- **WHEN** the caller requests the first or lowest hint level
- **THEN** the hint response guides the learner toward the relevant concept without returning complete corrected code

#### Scenario: Stronger hint
- **WHEN** the caller requests a stronger hint level
- **THEN** the hint response may provide more specific guidance while still identifying the hint level in structured output

### Requirement: Include Teaching Guidance Metadata
The system SHALL return structured metadata describing focused concepts, selected memory IDs, hint level, and whether the hint used quick recap or contrast-example guidance.

#### Scenario: Quick recap metadata
- **WHEN** retrieved memory indicates the learner likely needs prerequisite recap
- **THEN** the hint response marks the teaching action as quick recap or quick recap then hint

#### Scenario: Contrast example metadata
- **WHEN** retrieved memory includes a teaching heuristic for contrast examples
- **THEN** the hint response can include contrast-example guidance in structured metadata
