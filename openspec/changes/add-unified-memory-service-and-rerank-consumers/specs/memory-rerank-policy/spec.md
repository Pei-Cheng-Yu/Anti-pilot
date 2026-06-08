## ADDED Requirements

### Requirement: Code Correction Consumes Rerank Guidance
The system SHALL rerank retrieved learner memories for code-correction purpose before producing correction focus or feedback guidance.

#### Scenario: Code correction rerank request
- **WHEN** code correction retrieves learner memory for a submitted coding problem attempt
- **THEN** the system calls the memory rerank policy with `purpose=code_correction`, the current task context, learner feedback context, recent attempts, and retrieved candidate memories

#### Scenario: Code correction bounded selection
- **WHEN** the rerank result selects memory notes for code correction
- **THEN** the correction service uses only selected memory IDs that were present in the retrieved candidate set

#### Scenario: Code correction fallback
- **WHEN** the rerank advisor is unavailable or returns invalid output
- **THEN** code correction continues with deterministic rerank guidance and still returns a valid `CodeCorrectionResult`

### Requirement: Content Generation Consumes Rerank Guidance
The system SHALL rerank retrieved learner memories for content-generation purpose before building generation prompts.

#### Scenario: Content generation rerank request
- **WHEN** the content-generation graph retrieves learner memory for a skillpath
- **THEN** the system calls the memory rerank policy with `purpose=content_generation`, skillpath context, and retrieved candidate memories

#### Scenario: Content generation prompt context
- **WHEN** content-generation rerank returns selected memories and guidance
- **THEN** the generation request or prompt context includes the selected memories and guidance in addition to retrieval diagnostics

#### Scenario: Content generation fallback
- **WHEN** memory retrieval is empty, rerank is unavailable, or rerank output is invalid
- **THEN** content generation continues with a valid empty or deterministic memory guidance result

### Requirement: Rerank Remains Non-Mutating
The system MUST keep rerank policy advisory and non-persistent for all consumers.

#### Scenario: Code correction uses rerank
- **WHEN** code correction consumes a rerank result
- **THEN** the rerank result does not create, update, merge, resolve, delete, or flag memory notes

#### Scenario: Content generation uses rerank
- **WHEN** content generation consumes a rerank result
- **THEN** the rerank result does not mutate learner memory, goal, learning profile, roadmap, milestone, or skillpath state

### Requirement: Rerank Consumer Diagnostics
The system SHALL expose enough diagnostics to verify which memory selection shaped code correction and content generation.

#### Scenario: Code correction diagnostics
- **WHEN** code correction completes after memory rerank
- **THEN** the result exposes or logs the rerank purpose, selected memory IDs, teaching action, and guidance used for correction

#### Scenario: Content generation diagnostics
- **WHEN** content generation completes after memory rerank
- **THEN** graph state or generation diagnostics expose the rerank purpose, selected memory IDs, teaching action, and guidance used for generation
