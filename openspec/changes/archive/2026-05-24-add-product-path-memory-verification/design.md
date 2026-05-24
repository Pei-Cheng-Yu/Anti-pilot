# Design

## Current State

Existing coverage already verifies most building blocks:

- `validate_code_submission` can run as a live validator smoke.
- `process_code_correction` can persist attempts and consolidate memory from runtime/test evidence.
- `retrieve_learning_memory` can return hybrid-ranked memory context.
- `build_learning_content_graph` can retrieve DB memory and invoke real ADK content generation.

The missing piece is a single product-shaped flow that connects those pieces without pre-seeding learner memory.

Repository inspection currently shows the product-facing backend entrypoint is MCP, not a FastAPI learner-submission route:

- `backend/app/mcp/server.py` mounts `code_correction_mcp`.
- `backend/app/mcp/tools/code_correction.py` exposes `process_code_correction`.
- `backend/app/services/code_correction.py` calls `learning_memory.record_and_consolidate_attempt`.

So memory generation is in the workflow when callers use `code_correction.process_code_correction`, but it may not yet be wired to a separate HTTP endpoint because no such endpoint is currently visible in `backend/app`.

## Proposed Flow

The verification should run as a gated live/integration test or script:

```text
create user + roadmap + skillpath + coding content
        ↓
submit bad coding attempt through current product boundary
        - preferred current boundary: MCP code_correction.process_code_correction
        - if an HTTP route is added/found: call that route
        ↓
validator/correction path processes evidence
        ↓
CodingProblemAttempt row is persisted
        ↓
LearnerMemoryNote ERROR_PATTERN/HEURISTIC is created or updated
        ↓
run learning-content generation for the same user
        ↓
LangGraph state exposes diagnostics + memory context
        ↓
real ADK content adapts to memory
```

## Validator and Memory Generation

The bad coding attempt should pass through the same path used by correction, because memory generation is tied to persisted attempt evidence and consolidation.

The validator alone can identify correctness, runtime errors, and concepts, but the memory note is created when the attempt is recorded and consolidated. In practice, the product-path verification should assert this chain:

```text
bad attempt + runtime evidence
        ↓
validation/correction result
        ↓
record_and_consolidate_attempt
        ↓
LearnerMemoryNote
```

If the app API endpoint already wraps validation plus correction, the test should call that endpoint. Current code inspection suggests no such endpoint exists, so the first implementation should call the MCP tool or its underlying service and name the remaining HTTP/API gap explicitly.

If the frontend needs an HTTP endpoint rather than MCP, a follow-up implementation should add an endpoint equivalent to:

```text
POST /coding-problem-attempts/validate-and-correct
        ↓
validate_code_submission
        ↓
build_correction_request_from_validation
        ↓
process_code_correction
```

That endpoint should return both learner-facing feedback and enough debug/diagnostic identifiers to inspect created attempt and memory rows.

## Test Shape

Add one gated test, probably in `backend/tests/test_live_agent_memory_integration.py` or a new product-path test file:

- marker: `pytest.mark.live_llm`
- env gate: `RUN_LIVE_AGENT_MEMORY_TESTS=1`
- requires DB and model credentials
- invokes the current product boundary, preferring MCP `code_correction.process_code_correction` if no HTTP endpoint exists
- prints redacted diagnostic snippets for LangSmith matching

Assertions should be stronger than the existing seeded-memory live graph test:

- no memory note exists for the user before the bad attempt
- bad attempt creates one `CodingProblemAttempt`
- consolidation creates or updates at least one active memory note
- content graph diagnostics status is `retrieved`
- graph state includes the memory note under `learning_memory_contexts_by_skillpath`
- generated content is not the fake deterministic test marker
- generated content mentions the mistake theme

## PR Strategy

This should be included in the same PR as the memory feature if implemented before push, because it is final verification for that feature. It should be a separate commit inside the PR:

1. runtime memory feature
2. graph diagnostics and integration tests
3. product-path verification

This keeps review clean while proving the branch is merge-ready.

## Risks

- A full API-path test may require app server setup, auth, or frontend fixtures.
- Live LLM behavior may be slightly variable, so behavioral assertions should focus on stable themes rather than exact wording.
- If the endpoint does not yet route through memory consolidation, this change may reveal a real product gap rather than only adding tests.
