## Context

When a learner marks a skillpath as done, three separate concerns need updating: the skillpath record itself, the aggregate mastery state, and the learner's long-term memory notes. No composite service function handles this today.

The key design tension is that "done" does not equal "mastered." A learner might mark a skillpath done after reading the article but before submitting any code. Blindly writing `mastered` to `skill_mastery_states` would overclaim competence and corrupt downstream memory retrieval for content generation and hints. The system needs to judge the strength of the signal from available evidence before deciding what to write.

Existing related services:
- `roadmap.update_skillpath(**fields)` — patches any skillpath field including `status`
- `learning_memory.add_memory_note()` — creates memory notes through the integrity lifecycle
- `memory_advisors.advise_memory_integrity()` — existing Integrity Advisor pattern
- `record_and_consolidate_attempt()` — evidence-driven mastery update from code submission

The new service must fit into the existing advisor pattern: LLM is the normal path, deterministic fallback when unavailable or invalid.

## Goals / Non-Goals

**Goals:**
- Mark `skillpaths.status` → `"completed"` unconditionally
- Use a new Skillpath Completion Advisor to judge signal strength from available evidence
- Update `skill_mastery_states.status` based on advisor judgment — only write `"mastered"` when attempt evidence supports it
- Create a `mastery_signal` memory note with advisor-suggested salience through the integrity lifecycle
- Let the existing Memory Integrity Advisor handle the mastery_signal vs error_pattern conflict resolution automatically
- Expose as MCP tool and HTTP endpoint

**Non-Goals:**
- No DB schema changes — `"completed"` already valid in `SkillPathItem` Literal, `MasteryStatus.MASTERED` already in enum
- No triggering content generation for the next skillpath — separate concern
- No changes to `record_and_consolidate_attempt()` — that path is for code submission evidence only
- No new memory types or rerank purposes

## Decisions

### Decision 1: New dedicated Skillpath Completion Advisor

A new `advise_skillpath_completion()` function in `app/advisors/memory_advisors.py`, following the identical DeepAgent + structured output pattern as `advise_memory_integrity()` and `rerank_memory_advice()`.

Input passed to advisor:
- Skillpath title, learning objectives, description
- Current `SkillMasteryState` (status, score, successful/failed attempts, strong/weak concepts)
- Recent `CodingProblemAttempts` for this skillpath (last N, may be empty)

Output schema:
```python
class SkillpathCompletionAdvisorOutput(BaseModel):
    suggested_mastery_status: MasteryStatus
    mastery_signal_salience: float  # 0.0–1.0
    signal_strength: Literal["none", "weak", "moderate", "strong"]
    reasoning: str
```

Fallback (flag off / no credentials / invalid schema): `suggested_mastery_status="practicing"`, `salience=0.5`, `signal_strength="weak"`.

**Alternative considered:** Reuse the Memory Integrity Advisor to judge the mastery_signal write and infer mastery status from it. Rejected because the Integrity Advisor only receives memory note candidates — it has no access to the skillpath content or structured mastery state. A dedicated advisor is needed.

### Decision 2: "done" always sets skillpaths.status = "completed", regardless of advisor

The advisor judges mastery evidence; it does not gate the completion of the skillpath record itself. A learner who clicked "done" has completed the activity regardless of their performance. Calling `roadmap.update_skillpath(status="completed")` is unconditional.

### Decision 3: Integrity Advisor handles error_pattern → watch automatically

When `mark_skillpath_completed()` calls `memory_service.add_memory_note(mastery_signal, ...)` scoped to the skillpath's concepts and skillpath_id, the Memory Integrity Service will find overlapping active `error_pattern` notes. The Integrity Advisor will recognize the semantic conflict (mastery evidence vs struggle evidence) and recommend `flag_conflict`. The executor then moves the error_pattern notes to `watch` and lowers their salience.

No explicit "downgrade error patterns" step is needed — it falls out of the existing integrity lifecycle.

### Decision 4: skill_mastery_states is a direct DB upsert, not through the integrity lifecycle

`SkillMasteryState` is an aggregate tracker in `skill_mastery_states`, not a `learner_memory_notes` entry. The integrity advisor cannot reach it. The service upserts `status` and `mastery_score` directly based on the advisor's output. This is consistent with how `record_and_consolidate_attempt()` currently updates mastery state.

### Decision 5: Env flag for Skillpath Completion Advisor

`ENABLE_SKILLPATH_COMPLETION_ADVISOR=1` — consistent with other advisor flags. Uses `MEMORY_ADVISOR_MODEL` for the model, same as other advisors.

## Risks / Trade-offs

**Advisor suggests "mastered" with no attempt evidence** → Mitigation: advisor prompt explicitly instructs that `"mastered"` requires at least one correct attempt. Service also validates: if `recent_attempts` is empty, cap suggestion at `"practicing"`.

**Integrity Advisor not enabled — error_pattern notes stay active** → Mitigation: deterministic fallback in integrity service still finds overlap candidates; with deterministic scoring a mastery_signal vs error_pattern conflict should still trigger `flag_conflict`. Document that enabling `ENABLE_MEMORY_INTEGRITY_ADVISOR` gives better semantic resolution.

**Learner marks done repeatedly** → Mitigation: `update_skillpath(status="completed")` is idempotent. Memory Integrity lifecycle handles duplicate mastery_signal writes (skip_duplicate or update_existing). `SkillMasteryState` upsert is idempotent.

**Skillpath has no coding problem attempts — advisor has weak signal** → Mitigation: advisor returns `signal_strength="weak"` and service writes `"practicing"` with low salience. This is correct behaviour — reading an article is a completion, not mastery.

## Migration Plan

No DB migrations. New service function, new advisor, new MCP tool, new HTTP endpoint. Existing callers of `update_skillpath()` are unaffected. Rollback: remove the endpoint and MCP tool; the service function can remain inert.
