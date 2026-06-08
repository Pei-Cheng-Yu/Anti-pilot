## MODIFIED Requirements

### Requirement: Rerank Retrieved Memories For A Purpose
The system SHALL provide a memory rerank policy that receives a bounded candidate memory set and returns selected memories ranked for a specified purpose. When advisor execution is enabled, the rerank advisor SHALL be invoked as the normal path and deterministic ranking SHALL be used as fallback only.

#### Scenario: Content generation purpose
- **WHEN** the rerank purpose is content generation
- **THEN** the result includes selected memories and content guidance suitable for generation prompts

#### Scenario: Hint generation purpose
- **WHEN** the rerank purpose is hint generation
- **THEN** the result includes selected memories and hint guidance suitable for a learner-facing hint

#### Scenario: Code correction purpose
- **WHEN** the rerank purpose is code correction
- **THEN** the result includes selected memories and feedback guidance suitable for correction output

#### Scenario: Advisor rerank path
- **WHEN** advisor execution is enabled and candidate memories are available
- **THEN** the rerank policy invokes the real rerank advisor and returns validated advisor guidance

### Requirement: Restrict Rerank Output To Candidate Memories
The system MUST reject or ignore selected memory IDs that were not present in the candidate set.

#### Scenario: Invalid selected memory ID
- **WHEN** an LLM rerank advisor returns a selected memory ID not present in the input candidates
- **THEN** the system falls back to validated candidate selections and does not expose the invalid ID to callers

### Requirement: Provide Deterministic Fallback
The system SHALL provide a deterministic fallback when the LLM rerank advisor is unavailable, times out, or returns invalid structured output.

#### Scenario: Advisor unavailable
- **WHEN** the LLM rerank advisor fails
- **THEN** the system returns a valid rerank result based on existing deterministic memory ranking

#### Scenario: Advisor disabled
- **WHEN** advisor execution is disabled by configuration
- **THEN** the system returns a valid rerank result based on existing deterministic memory ranking

### Requirement: Keep Reranker Advisory
The memory rerank policy MUST NOT create, update, resolve, merge, or delete learner memory notes.

#### Scenario: Reranker returns guidance only
- **WHEN** the rerank policy returns a result
- **THEN** the result contains selected memories and teaching guidance but no persisted DB writes
