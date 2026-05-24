# Improve Code Submission Memory Lifecycle

## Summary

Add a product-level code submission orchestrator and strengthen learner memory lifecycle updates so successes and failures both maintain a coherent learner model. Keep persistence deterministic, but allow an optional bounded consolidation judgment/reranker to improve salience, mastery confidence, duplicate matching, and evidence quality.

## Motivation

The current implementation has the core parts:

- `validate_code_submission` analyzes submitted code and runtime/test evidence.
- `build_correction_request_from_validation` converts validator output into correction input.
- `process_code_correction` retrieves memory, stores the attempt, and calls memory consolidation.
- `consolidate_attempt_memory` creates/updates error patterns, heuristics, mastery signals, and mastery state.
- content generation can later retrieve memory and personalize output.

But the product shape is still incomplete:

- There is no single `submit_code_attempt` boundary that VS Code/frontend/agents can call.
- MCP currently exposes `code_correction.process_code_correction`, which starts after validation rather than accepting `CodeValidationRequest`.
- Successful attempts update mastery, but they do not yet meaningfully reduce, downgrade, or resolve related old `ERROR_PATTERN` notes.
- Good-at and bad-at evidence is split across `SkillMasteryState` and `LearnerMemoryNote`; the system needs a clearer consolidation lifecycle to keep those views consistent.
- Pure deterministic rules can be too blunt for evidence quality. A pass may be shallow, copied, or trivial; a failure may be syntax noise rather than concept weakness.
- The validator can judge the current attempt, but it does not currently compare that attempt against retrieved memory/history to decide whether an old pattern has improved, recurred, or should be merged.

## Goals

- Add a deterministic product-level orchestrator such as `submit_code_attempt` or `validate_and_process_code_submission`.
- Accept `CodeValidationRequest` as the external input shape for the product boundary.
- Run `validate_code_submission`, then convert to `CodeCorrectionRequest`, then call `process_code_correction`.
- Expose the product boundary as an MCP tool, and optionally as an HTTP/API endpoint if the backend has a route layer.
- Strengthen `consolidate_attempt_memory` so successful related attempts can update mastery, create mastery signals, lower salience for old error patterns, move old error patterns to `WATCH`, and eventually resolve them after enough evidence.
- Add a structured `MemoryConsolidationJudgment` contract for optional agent/reranker advice.
- Define what belongs in the validator versus the consolidation judgment so one agent prompt does not become responsible for everything.
- Keep all DB writes and lifecycle transitions bounded and deterministic even when a judgment is used.
- Add tests that prove failed attempts create weakness memory and successful attempts can improve/resolve related weakness memory.

## Non-Goals

- Do not let an LLM directly mutate DB rows.
- Do not require the optional consolidation judgment in default unit tests.
- Do not replace existing deterministic consolidation rules.
- Do not make live LLM calls part of default CI.
- Do not build a broad UI flow in this change.

## Success Criteria

- A caller can submit one `CodeValidationRequest` and receive both validation and correction/memory results.
- The product boundary persists `CodingProblemAttempt` and updates `LearnerMemoryNote` without requiring the caller to manually call low-level memory tools.
- A failed FastAPI async attempt creates or updates an `ERROR_PATTERN`.
- A later successful related attempt updates mastery and reduces/downgrades or resolves the related old `ERROR_PATTERN` according to bounded lifecycle rules.
- Optional consolidation judgment output can adjust salience/mastery within strict caps and schema validation.
- MCP tool tests prove the new product boundary accepts structured Pydantic input.
- Service tests prove memory lifecycle consistency across failure-then-success attempt sequences.
- Tests prove the validator can remain focused on per-attempt validation while consolidation judgment handles memory-relative questions such as same-old-mistake, meaningful success, and merge candidates.
