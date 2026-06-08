## ADDED Requirements

### Requirement: Invoke Real Memory Advisors
The system SHALL provide real DeepAgent/LLM-backed advisors for hint generation, memory reranking, and memory integrity recommendations.

#### Scenario: Hint advisor invoked
- **WHEN** a memory-aware hint is requested and advisor execution is enabled
- **THEN** the system invokes the hint advisor with task context, submitted code, requested hint level, and retrieved learner memory

#### Scenario: Rerank advisor invoked
- **WHEN** memory candidates are reranked for hint generation, content generation, or code correction and advisor execution is enabled
- **THEN** the system invokes the rerank advisor with a bounded candidate set and the requested purpose

#### Scenario: Integrity advisor invoked
- **WHEN** an incoming memory note has ambiguous duplicate or conflict candidates and advisor execution is enabled
- **THEN** the system invokes the integrity advisor with the incoming memory, bounded candidates, deterministic evidence, and allowed actions

### Requirement: Validate Advisor Outputs
The system MUST validate all advisor outputs before returning them to callers or applying service actions.

#### Scenario: Invalid selected memory ID
- **WHEN** an advisor references a memory ID that was not present in the candidate set
- **THEN** the system rejects the advisor output and uses the deterministic fallback

#### Scenario: Invalid structured output
- **WHEN** an advisor response does not match the expected Pydantic schema
- **THEN** the system rejects the response and uses the deterministic fallback

#### Scenario: Low-spoiler violation
- **WHEN** the hint advisor returns complete corrected code for a low-level hint
- **THEN** the system rejects or rewrites the response through the fallback path

### Requirement: Preserve Service-Owned Persistence
Advisor modules MUST NOT directly mutate learner memory or roadmap state.

#### Scenario: Integrity advisor recommends merge
- **WHEN** the integrity advisor recommends a merge action
- **THEN** only the memory service validates the recommendation and performs any database write

#### Scenario: Rerank advisor returns guidance
- **WHEN** the rerank advisor selects memories
- **THEN** the result contains selected memory IDs and teaching guidance but does not persist memory changes

### Requirement: Provide Observable Live Smoke Path
The system SHALL include a gated live smoke path that exercises at least one real advisor invocation and can be inspected in LangSmith.

#### Scenario: LangSmith trace contains advisor fields
- **WHEN** the live advisor smoke test runs with tracing enabled
- **THEN** the trace includes advisor request/response data, selected memory IDs, and fallback status
