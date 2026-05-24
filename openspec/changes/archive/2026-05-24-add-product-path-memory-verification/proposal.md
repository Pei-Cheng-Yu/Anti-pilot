# Add Product-Path Memory Verification

## Summary

Add a product-boundary verification path that proves a real bad coding attempt can create learner memory, and that later learning-content generation for the same user retrieves and uses that memory.

## Motivation

The current memory work is strong at the service, graph, and live-agent test layers. It proves:

- memory can be stored and retrieved through the DB-backed hybrid retriever
- correction services can persist attempts and update learner memory
- content-generation graph state can expose memory diagnostics
- live ADK content generation can use seeded memory

The remaining confidence gap is the product path a learner will actually use. We still need one realistic flow that starts from a submitted bad coding attempt, goes through validation/correction as the app would call it, confirms memory persistence, then generates learning content for the same user and confirms the graph retrieves and applies that memory.

Current inspection shows no learner-submission FastAPI route under `backend/app`. The exposed product boundary is currently MCP:

- `code_correction.process_code_correction`
- `learning_memory.record_and_consolidate_attempt`

`code_correction.process_code_correction` already invokes memory consolidation internally. This change should verify that MCP/service boundary first, then decide whether an additional HTTP/API endpoint is needed for the actual frontend/app flow.

## Goals

- Add a product-path smoke test or scripted verification that submits a bad coding attempt through the actual MCP/API/service boundary used by the app.
- Confirm whether a learner-facing HTTP/API endpoint exists; if not, document MCP as the current product boundary or add the missing endpoint in a follow-up.
- Confirm validator or correction processing receives runtime/test evidence and produces structured feedback.
- Confirm `CodingProblemAttempt` is persisted.
- Confirm `LearnerMemoryNote` is created or updated, especially `ERROR_PATTERN` and optionally `HEURISTIC`.
- Confirm subsequent content generation for the same user produces `learning_memory_retrieval_diagnostics_by_skillpath[...].status == "retrieved"`.
- Confirm `learning_memory_contexts_by_skillpath` contains the generated memory note.
- Confirm generated learning content adapts to the remembered mistake.
- Document exactly what to inspect in terminal output, DB rows, and LangSmith traces.

## Non-Goals

- Do not make live LLM/API tests part of the default CI suite.
- Do not require paid sandbox execution.
- Do not replace the existing service-level tests.
- Do not add broad UI automation unless the backend/API path is insufficient to prove the product behavior.

## Success Criteria

- A gated product-path test or script can run locally with WSL credentials and a live test flag.
- The flow starts with a bad coding attempt, not pre-seeded memory.
- The flow proves the attempt triggers memory creation through the app's validation/correction path.
- The same run then generates content for the same user and observes retrieved memory in LangGraph state.
- Generated content includes evidence of personalization around the original mistake, such as missing `await`, async route handlers, or the specific runtime failure.
- The docs explain whether the flow calls the validator, correction MCP tool/service, content graph, and ADK agent.
- The result clearly states whether the current implementation has an HTTP app endpoint or only MCP/service entrypoints.
