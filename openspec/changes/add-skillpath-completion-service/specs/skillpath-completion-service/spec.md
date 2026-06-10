## ADDED Requirements

### Requirement: mark_skillpath_completed service function
The system SHALL provide a `mark_skillpath_completed(user_id, skillpath_id, session)` function in `app/services/learning_memory.py` that orchestrates all effects of a learner marking a skillpath as done.

#### Scenario: Full completion flow runs
- **WHEN** `mark_skillpath_completed(user_id, skillpath_id)` is called
- **THEN** the function executes in order: update skillpath status, invoke completion advisor, upsert mastery state, write mastery_signal note through integrity lifecycle

---

### Requirement: skillpaths.status always set to completed
The service SHALL unconditionally update `skillpaths.status` to `"completed"` via `roadmap.update_skillpath()` regardless of advisor output or attempt evidence.

#### Scenario: Status updated even with no coding attempts
- **WHEN** the learner has no coding attempts for the skillpath
- **THEN** `skillpaths.status` is still set to `"completed"`

#### Scenario: Status update is idempotent
- **WHEN** `mark_skillpath_completed()` is called more than once for the same skillpath
- **THEN** `skillpaths.status` remains `"completed"` without error

---

### Requirement: skill_mastery_states updated using advisor judgment
The service SHALL upsert `skill_mastery_states` using the Skillpath Completion Advisor's `suggested_mastery_status`. If the advisor is unavailable or returns an invalid response, the service SHALL fall back to `"practicing"`.

#### Scenario: Advisor suggests mastered with attempt evidence
- **WHEN** the advisor returns `suggested_mastery_status="mastered"` and the learner has at least one correct attempt
- **THEN** `skill_mastery_states.status` is set to `MasteryStatus.MASTERED`

#### Scenario: Advisor suggests mastered but no attempts exist
- **WHEN** the advisor returns `suggested_mastery_status="mastered"` but `recent_attempts` is empty
- **THEN** the service overrides the suggestion and sets `skill_mastery_states.status` to `"practicing"`

#### Scenario: Advisor unavailable — fallback to practicing
- **WHEN** `ENABLE_SKILLPATH_COMPLETION_ADVISOR` is not set or advisor returns invalid output
- **THEN** `skill_mastery_states.status` is set to `"practicing"`

---

### Requirement: mastery_signal note written through integrity lifecycle
The service SHALL call `memory_service.add_memory_note()` with `memory_type="mastery_signal"`, `linked_skillpath_ids=[skillpath_id]`, `linked_concepts=skillpath.learning_objectives`, and `salience_score` from the advisor (fallback: `0.5`). This write SHALL go through the Memory Integrity Service and optionally the Memory Integrity Advisor.

#### Scenario: Mastery signal created for new learner competence
- **WHEN** no existing mastery_signal note covers the skillpath concepts
- **THEN** a new mastery_signal note is created with the advisor-suggested salience

#### Scenario: Integrity lifecycle resolves conflict with error_pattern
- **WHEN** active error_pattern notes exist for the same skillpath concepts
- **THEN** the Memory Integrity Advisor recommends flag_conflict and the executor moves those error_pattern notes to watch status with lower salience

#### Scenario: Duplicate mastery signal merged
- **WHEN** an existing mastery_signal note already covers the same skillpath concepts
- **THEN** the integrity executor applies update_existing or skip_duplicate — no duplicate note is created

---

### Requirement: HTTP endpoint for frontend
The existing `POST /v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/status` endpoint (in `app/main.py`) SHALL route to `mark_skillpath_completed()` when `request.status == "completed"`, and to plain `update_skillpath()` for all other status values. No separate `/complete` route is added (the frontend already uses `/status`).

#### Scenario: Frontend marks skillpath done
- **WHEN** the frontend sends `POST .../status` with `{"status": "completed"}`
- **THEN** `mark_skillpath_completed()` runs (not a plain status write) and the endpoint returns the updated roadmap with the skillpath `status="completed"`

#### Scenario: Non-completion status transition
- **WHEN** the frontend sends `POST .../status` with any status other than `"completed"`
- **THEN** the endpoint calls `update_skillpath(status=...)` only — the completion pipeline does NOT run

#### Scenario: Skillpath not found
- **WHEN** the skillpath_id or roadmap_id does not exist or does not belong to the user
- **THEN** the endpoint returns 404

---

### Requirement: MCP tool for agent access
The system SHALL expose a `learning_memory_mark_skillpath_completed` MCP tool that calls `mark_skillpath_completed()`.

#### Scenario: Agent marks skillpath complete via MCP
- **WHEN** an agent calls `learning_memory_mark_skillpath_completed(user_id, skillpath_id)`
- **THEN** the full completion flow runs identically to the HTTP path
