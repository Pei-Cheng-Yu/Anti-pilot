## MODIFIED Requirements

### Requirement: Use LLM Advisor As Bounded Recommendation
The system MAY use an LLM integrity advisor to recommend duplicate or conflict actions over a bounded candidate set, but the service MUST validate the advisor output before persistence. When advisor execution is enabled and deterministic evidence indicates an ambiguous duplicate or conflict, the integrity advisor SHALL be invoked before finalizing the service-owned decision.

#### Scenario: Advisor recommends merge
- **WHEN** the advisor recommends merging incoming memory into an existing candidate
- **THEN** the service validates that all target memory IDs were present in the candidate set before applying any merge

#### Scenario: Advisor returns invalid output
- **WHEN** the advisor returns invalid schema, unknown target IDs, or an unsupported action
- **THEN** the service ignores the invalid recommendation and falls back to deterministic integrity behavior

#### Scenario: Advisor receives bounded evidence
- **WHEN** the integrity advisor is invoked
- **THEN** it receives only the incoming memory, candidate memories, deterministic evidence, and allowed actions

### Requirement: Preserve Memory Service Authority
The system MUST ensure that all memory integrity decisions are applied through service validation and service-owned database writes.

#### Scenario: Advisor cannot write directly
- **WHEN** an LLM advisor recommends an integrity action
- **THEN** only the memory service validates and persists the resulting change

#### Scenario: Advisor disabled
- **WHEN** integrity advisor execution is disabled by configuration
- **THEN** deterministic integrity behavior still prevents obvious duplicate writes and preserves lifecycle semantics
