## Why

When a learner marks a skillpath as done on the frontend, there is no service to handle the downstream effects — the skillpath status is not updated, the mastery state is not assessed, and no memory signal is created. Without this, the memory system never learns from self-reported completion and the roadmap never reflects progress.

## What Changes

- Add `mark_skillpath_completed()` service function that orchestrates all effects of a learner marking a skillpath as done
- Add a new **Skillpath Completion Advisor** (DeepAgent, structured output) that judges how strong the completion signal is, given the skillpath content and the learner's existing mastery state and attempts — same LLM-first pattern as other memory advisors
- Update `skillpaths.status` → `"completed"` (always, regardless of advisor)
- Update `skill_mastery_states.status` using the advisor's judgment (fallback: `"practicing"`) — `"mastered"` is only suggested when attempt evidence supports it
- Create a `mastery_signal` memory note with advisor-suggested salience, routed through the Memory Integrity lifecycle — the Integrity Advisor may automatically flag-conflict with active `error_pattern` notes, moving them to `watch`
- Expose via an MCP tool (`learning_memory_mark_skillpath_completed`) and the existing `/status` endpoint's `completed` branch (the frontend already calls `/status`)

## Capabilities

### New Capabilities

- `skillpath-completion-service`: Composite service for marking a skillpath done — updates skillpath status, assesses mastery with an LLM advisor, writes mastery_signal through integrity lifecycle
- `skillpath-completion-advisor`: DeepAgent advisor that judges completion signal strength and suggests `skill_mastery_states.status` and `mastery_signal` salience from skillpath content + existing mastery state + recent attempts

### Modified Capabilities

- none

## Impact

- `backend/app/services/learning_memory.py` — add `mark_skillpath_completed()` function
- `backend/app/advisors/memory_advisors.py` — add `advise_skillpath_completion()` function
- `backend/app/mcp/tools/learning_memory.py` — add `learning_memory_mark_skillpath_completed` tool
- `backend/app/main.py` — route the existing `POST /v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/status` endpoint to `mark_skillpath_completed()` when `status == "completed"` (no separate `/complete` route)
- `backend/app/schema/entities.py` — verify `SkillPathItem.status` Literal includes `"completed"` ✓ (already present)
- `backend/app/schema/enums.py` — verify `MasteryStatus` enum includes `"mastered"` ✓ (already present)
- No DB schema changes — all columns are plain String, all required values already valid
- Reads: `skillpaths`, `skill_mastery_states`, `coding_problem_attempts`, `learner_memory_notes`
- Writes: `skillpaths.status`, `skill_mastery_states`, `learner_memory_notes` (via integrity executor)
