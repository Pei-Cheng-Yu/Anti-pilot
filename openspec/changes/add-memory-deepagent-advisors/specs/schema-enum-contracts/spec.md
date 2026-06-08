## ADDED Requirements

### Requirement: Centralize Shared Enums
The system SHALL define shared schema enum vocabulary in `backend/app/schema/enums.py`.

#### Scenario: Memory advisor enums imported from enum module
- **WHEN** services, schemas, tests, MCP tools, or agents need `MemoryIntegrityAction`, `HintLevel`, `TeachingAction`, or `MemoryRerankPurpose`
- **THEN** they import those enums from `app.schema.enums`

#### Scenario: Entities only reference enum definitions
- **WHEN** Pydantic entity models use hint, teaching, rerank, or integrity enums
- **THEN** `entities.py` imports those enums instead of defining them locally

### Requirement: Preserve Serialized Enum Values
The system MUST preserve the existing serialized string values for moved enums.

#### Scenario: Hint response serialized
- **WHEN** a `HintResponse` is serialized after the enum move
- **THEN** `hint_level` and `teaching_action` use the same string values as before the move

#### Scenario: Integrity decision serialized
- **WHEN** a `MemoryIntegrityDecision` is serialized after the enum move
- **THEN** `action` uses the same string value as before the move

### Requirement: Prevent Stale Enum Imports
The system SHALL include verification that catches stale imports from the old enum location.

#### Scenario: Compile verification
- **WHEN** backend compile or focused tests run
- **THEN** stale enum imports from `app.schema.entities` fail before merge
