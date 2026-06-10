## 1. Advisor schema and output model

- [x] 1.1 Add `SkillpathCompletionAdvisorOutput` Pydantic schema to `app/schema/` with fields: `suggested_mastery_status: MasteryStatus`, `mastery_signal_salience: float`, `signal_strength: Literal["none","weak","moderate","strong"]`, `reasoning: str`
- [x] 1.2 Add validation: `mastery_signal_salience` must be 0.0–1.0
- [x] 1.3 Write unit test confirming schema rejects invalid `suggested_mastery_status` and out-of-range salience

## 2. Skillpath Completion Advisor

- [x] 2.1 Add `advise_skillpath_completion(skillpath, mastery_state, recent_attempts)` to `app/advisors/memory_advisors.py` following the same DeepAgent + structured output pattern as `advise_memory_integrity()`
- [x] 2.2 Write advisor prompt: include skillpath title + objectives + description, current mastery state fields, recent attempt correctness summary; instruct that `"mastered"` requires at least one correct attempt
- [x] 2.3 Add `ENABLE_SKILLPATH_COMPLETION_ADVISOR` flag check — return deterministic fallback (`practicing`, salience=0.5, `weak`) when flag off or credentials missing *(`_default_completion_advisor` in learning_memory.py)*
- [x] 2.4 Add output validation: reject invalid `MasteryStatus`, clamp salience to 0.0–1.0; fall back to deterministic on invalid output *(model_validate + try/except in service)*
- [x] 2.5 Write unit test with fake advisor returning valid output — confirm output parsed correctly
- [x] 2.6 Write unit test with fake advisor returning invalid `suggested_mastery_status` — confirm fallback used *(test_invalid_advisor_output_falls_back_to_practicing)*
- [x] 2.7 Write unit test with flag disabled — confirm DeepAgent never invoked *(test_flag_disabled_uses_deterministic_fallback)*

## 3. mark_skillpath_completed service function

- [x] 3.1 Add `mark_skillpath_completed(user_id, skillpath_id, session)` to `app/services/learning_memory.py`
- [x] 3.2 Step 1: call `roadmap.update_skillpath(user_id, skillpath_id, session, status="completed")` unconditionally
- [x] 3.3 Step 2: load `SkillMasteryState` and recent `CodingProblemAttempts` for the skillpath from DB
- [x] 3.4 Step 3: call `advise_skillpath_completion()` with skillpath content + mastery state + attempts
- [x] 3.5 Add hard guard: if `recent_attempts` is empty and advisor suggests `"mastered"` → override to `"practicing"`; if all attempts incorrect and advisor suggests `"mastered"` → override to `"in_progress"`
- [x] 3.6 Step 4: upsert `SkillMasteryState` with advisor's `suggested_mastery_status`
- [x] 3.7 Step 5: build an `AddMemoryNoteInput(memory_type="mastery_signal", title=..., summary=..., linked_skillpath_ids=[skillpath_id], linked_concepts=skillpath.learning_objectives, evidence_attempt_ids=[...], salience_score=advisor_salience)` and call `add_memory_note(payload, session)` — integrity lifecycle handles conflict with error_pattern notes automatically
- [x] 3.8 Write unit test: no attempts → status stays `"practicing"` regardless of advisor
- [x] 3.9 Write unit test: correct attempts present → advisor suggestion honoured
- [x] 3.10 Write unit test: idempotent — calling twice does not duplicate mastery_signal note (integrity returns skip_duplicate or update_existing)

## 4. MCP tool

- [x] 4.1 Add `learning_memory_mark_skillpath_completed(user_id, skillpath_id)` tool to `app/mcp/tools/learning_memory.py` delegating to `memory_facade.mark_skillpath_completed()`
- [x] 4.2 Write unit test confirming MCP tool calls the service with correct args

## 5. HTTP endpoint

- [x] 5.1 Route completion through the **existing** `POST /v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/status` endpoint: when `request.status == "completed"` call `mark_skillpath_completed()`, else `update_skillpath()`. (Frontend already uses `/status`; no separate `/complete` route.)
- [x] 5.2 Return the refreshed roadmap (`RoadmapFull`) for both branches
- [x] 5.3 Return 404 if skillpath/roadmap not found or does not belong to the user
- [x] 5.4 Unit test: `/status` with `{"status":"completed"}` → runs `mark_skillpath_completed`, NOT `update_skillpath` (test_status_completed_runs_completion_pipeline)
- [x] 5.5 Unit test: completed branch unknown skillpath → 404; non-completion status still uses `update_skillpath`

## 6. Verification

- [x] 6.1 Run all new unit tests — confirm they pass *(14 in test_skillpath_completion.py + 2 in test_api.py, all pass)*
- [x] 6.2 Integration test: learner with active error_pattern notes marks skillpath done — confirm error_pattern notes move to watch in DB *(test_active_error_pattern_moves_to_watch_on_completion)*
- [x] 6.3 Integration test: learner with no attempts marks skillpath done — confirm status is `"practicing"`, not `"mastered"` *(test_no_attempts_blocks_mastered + test_flag_disabled_uses_deterministic_fallback)*
- [x] 6.4 Verify advisor runs live: test_live_mark_skillpath_completed_full_workflow passes with ENABLE_SKILLPATH_COMPLETION_ADVISOR=1; observed advisor_used=True, suggested_mastery=mastered, salience=0.8 via -s. LangSmith trace visible when LANGCHAIN_TRACING_V2=true.
- [x] 6.5 Update `docs/five-layer-memory-access.md` — add endpoint and MCP tool to the service layer section
