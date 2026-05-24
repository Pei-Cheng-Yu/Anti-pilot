# Design

## Architecture

The desired runtime path is:

```text
VS Code / frontend / external agent
        |
submit_code_attempt(CodeValidationRequest)
        |
validate_code_submission
        |
CodeValidationResult
        |
build_correction_request_from_validation
        |
process_code_correction
        |
retrieve existing LearningMemoryContext
        |
record_and_consolidate_attempt
        |
CodingProblemAttempt + SkillMasteryState + LearnerMemoryNote updates
        |
CodeSubmissionResult
```

This removes the need for a separate always-on submission agent. The backend orchestrator owns the product flow. The validator remains the only required LLM/agent step.

## Validator vs Consolidation Judgment

The validator already answers an important subset of memory questions, but only for the current submitted code:

- how well the user did on this problem
- whether the result is correct, partial, incorrect, or runtime-error
- what compile/runtime/test evidence matters
- which concepts are involved
- which mistakes are visible in this attempt
- learner-facing feedback for this attempt

It can partially answer:

- whether a success was meaningful, if the prompt/test evidence is rich enough
- whether a failure is conceptual versus mechanical, if evidence is clear

But the validator should not be the only component deciding memory lifecycle, because it usually lacks the full memory/history context:

- existing `ERROR_PATTERN` notes
- older attempts and evidence timelines
- current mastery state
- duplicate or overlapping memory notes
- previous salience/status values
- teaching heuristics already in use

The consolidation judgment/reranker should answer memory-relative questions:

- Did this attempt match an existing error pattern?
- Did the learner actually overcome that old pattern, or was this success too shallow?
- Is this failure the same old mistake or a new one?
- Should two memory notes be merged?
- How strong should salience/mastery change be, within bounded caps?
- What teaching heuristic best fits the pattern over time?

So the intended split is:

```text
Validator = attempt-local evaluation
Consolidation judgment = attempt + memory/history interpretation
Memory service = deterministic bounded state mutation
```

The consolidation judgment may reuse the same model/provider family as the validator, but it should use a different prompt and schema because it has a different job.

## Product Boundary

Add a schema like:

```python
class CodeSubmissionResult(BaseModel):
    validation: CodeValidationResult
    correction: CodeCorrectionResult
```

Add a service function:

```python
async def submit_code_attempt(
    request: CodeValidationRequest,
    session: AsyncSession,
    *,
    validator_backend: CodeValidationBackend | None = None,
) -> CodeSubmissionResult:
    validation = await validate_code_submission(request, backend=validator_backend)
    correction_request = build_correction_request_from_validation(
        user_id=request.user_id,
        skillpath_id=request.skillpath_id,
        content_id=request.content_id,
        coding_problem_prompt=request.coding_problem_prompt,
        submitted_code=request.submitted_code,
        language=request.language,
        validation=validation,
    )
    correction = await process_code_correction(correction_request, session)
    return CodeSubmissionResult(validation=validation, correction=correction)
```

Expose it as MCP:

```text
code_correction_submit_code_attempt
```

Input:

```text
CodeValidationRequest
```

Output:

```text
CodeSubmissionResult
```

The existing `code_correction_process_code_correction` remains useful for callers that already have validation/evaluation evidence and want to skip validator invocation.

## Memory Lifecycle Owner

`learning_memory.consolidate_attempt_memory` remains the source of truth for memory lifecycle updates. It should own:

- `SkillMasteryState`
- `ERROR_PATTERN`
- `MASTERY_SIGNAL`
- `HEURISTIC`
- `salience_score`
- `status`
- `evidence_attempt_ids`
- `last_seen_at`
- `last_used_at`

Normal callers should not manually call `learning_memory_update_memory_note` for routine learning evolution. Direct memory MCP tools remain for explicit/manual edits, background facts, and exceptional correction.

## Success Handling

Current consolidation mostly rewards correct attempts through mastery state and optional mastery signal creation. The improved lifecycle should also find related active error patterns.

For a correct attempt:

```text
find active/watch ERROR_PATTERN notes for same skillpath/content/concept overlap
        |
lower salience by bounded amount
        |
if enough related success evidence:
    active -> watch
        |
if stronger repeated success evidence:
    watch -> resolved
        |
create/update MASTERY_SIGNAL
```

Suggested deterministic defaults:

- one related success lowers salience by at most `0.10`
- one related success may move `ACTIVE -> WATCH` only when mastery score is above a threshold or the note already has low salience
- resolving an error pattern requires at least two related successful attempts after the last failure, or an optional high-confidence judgment plus one success
- failed related attempts reactivate `WATCH` notes back to `ACTIVE`
- resolved notes stay excluded from default retrieval unless explicitly requested

## Optional Consolidation Judgment

Pure rules are stable but can miss nuance. Add an optional structured judgment/reranker stage that advises but does not directly mutate state.

Inputs to the judgment should include:

- the newly persisted `CodingProblemAttempt`
- current `SkillMasteryState`
- candidate related `LearnerMemoryNote` rows
- recent attempts for the same skillpath/content/concepts
- validator output fields copied into the attempt/correction request

The judgment should not call MCP or write DB rows. It only returns structured advice.

Example schema:

```python
class MemorySalienceAdjustment(BaseModel):
    memory_id: str
    delta: float = Field(ge=-0.15, le=0.15)
    reason: str

class MemoryConsolidationJudgment(BaseModel):
    attempt_importance: Literal["low", "medium", "high"]
    success_quality: Literal["none", "shallow", "normal", "strong"]
    failure_kind: Literal["none", "same_pattern", "new_pattern", "mechanical_error"]
    related_error_pattern_ids: list[str] = []
    merge_candidate_ids: list[list[str]] = []
    salience_adjustments: list[MemorySalienceAdjustment] = []
    mastery_delta: float = Field(ge=-0.1, le=0.2)
    should_create_heuristic: bool = False
    should_mark_resolved: bool = False
    teaching_heuristic_summary: str | None = None
    rationale: str
```

The service applies guardrails:

- validate schema
- clamp deltas
- ignore IDs outside the user scope
- require deterministic evidence thresholds before resolving a note
- treat `should_mark_resolved` as a recommendation, not an automatic transition
- require merge candidates to be same user and overlapping concept scope
- log/return diagnostics when judgment is unavailable

## Default Test Strategy

Unit tests should monkeypatch/fake validator and optional judgment providers. No live model calls in default tests.

Test sequences:

1. failed async attempt creates `ERROR_PATTERN`
2. successful related attempt updates mastery and lowers/downgrades the error pattern
3. repeated successful related attempts resolve the error pattern and create/update `MASTERY_SIGNAL`
4. failed related attempt after `WATCH` reactivates the pattern
5. optional judgment can adjust salience within caps
6. invalid/excessive judgment is clamped or ignored
7. MCP `submit_code_attempt` accepts `CodeValidationRequest` as structured input

## Live Verification

Keep live verification gated:

```bash
RUN_LIVE_AGENT_MEMORY_TESTS=1 PYTHONPATH=. ../venv/bin/python -m pytest -m live_llm tests/test_live_agent_memory_integration.py -q -s
```

The live path should prove:

- `submit_code_attempt` invokes the validator
- correction persists attempt and memory
- content generation later retrieves memory
- successful follow-up evidence changes memory lifecycle as expected
