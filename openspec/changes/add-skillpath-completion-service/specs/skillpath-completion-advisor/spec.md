## ADDED Requirements

### Requirement: Skillpath Completion Advisor function
The system SHALL provide an `advise_skillpath_completion()` function in `app/advisors/memory_advisors.py` that invokes a DeepAgent with structured output to judge the strength of a skillpath completion signal.

#### Scenario: Advisor invoked with full evidence
- **WHEN** `advise_skillpath_completion()` is called with skillpath content, mastery state, and recent attempts
- **THEN** the advisor returns a `SkillpathCompletionAdvisorOutput` with `suggested_mastery_status`, `mastery_signal_salience`, `signal_strength`, and `reasoning`

---

### Requirement: Advisor input includes skillpath content and mastery evidence
The advisor SHALL receive: skillpath title, learning objectives, description; current `SkillMasteryState` (status, score, successful_attempts, failed_attempts, strong_concepts, weak_concepts); and recent `CodingProblemAttempts` for the skillpath (may be empty list).

#### Scenario: Advisor receives all evidence fields
- **WHEN** the advisor is called
- **THEN** the prompt contains skillpath objectives, current mastery status, attempt count, correctness summary, and strong/weak concepts

---

### Requirement: Advisor output schema is validated
The service SHALL validate that `suggested_mastery_status` is a valid `MasteryStatus` enum value and `mastery_signal_salience` is between 0.0 and 1.0. Invalid output SHALL trigger deterministic fallback.

#### Scenario: Advisor returns invalid mastery status
- **WHEN** the advisor returns a `suggested_mastery_status` not in `MasteryStatus` enum
- **THEN** service falls back to `suggested_mastery_status="practicing"` and `salience=0.5`

#### Scenario: Advisor returns salience out of range
- **WHEN** the advisor returns `mastery_signal_salience` outside 0.0–1.0
- **THEN** service clamps or falls back to `salience=0.5`

---

### Requirement: Advisor is LLM-first with deterministic fallback
The advisor SHALL be invoked when `ENABLE_SKILLPATH_COMPLETION_ADVISOR=1` is set and credentials are available. The deterministic fallback SHALL return `suggested_mastery_status="practicing"`, `mastery_signal_salience=0.5`, `signal_strength="weak"`.

#### Scenario: Flag disabled — fallback used
- **WHEN** `ENABLE_SKILLPATH_COMPLETION_ADVISOR` is not set
- **THEN** fallback values are returned without invoking the DeepAgent

#### Scenario: Credentials missing — fallback used
- **WHEN** no `GOOGLE_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_GENAI_API_KEY` is available
- **THEN** fallback values are returned without error

---

### Requirement: mastered only suggested with attempt evidence
The advisor prompt SHALL instruct that `"mastered"` is only appropriate when the learner has at least one correct attempt. The service SHALL enforce this as a hard guard regardless of advisor output.

#### Scenario: No attempts exist — mastered blocked
- **WHEN** recent_attempts is empty and advisor suggests `"mastered"`
- **THEN** service overrides to `"practicing"` before writing

#### Scenario: All attempts incorrect — mastered blocked
- **WHEN** all recent attempts have correctness != correct and advisor suggests `"mastered"`
- **THEN** service overrides to `"in_progress"` before writing

---

### Requirement: Advisor uses MEMORY_ADVISOR_MODEL
The advisor SHALL use the model configured in `MEMORY_ADVISOR_MODEL` environment variable, defaulting to `google_genai:gemini-3.1-flash-lite-preview`, consistent with all other memory advisors.

#### Scenario: Custom model configured
- **WHEN** `MEMORY_ADVISOR_MODEL` is set to a different model
- **THEN** the Skillpath Completion Advisor uses that model
