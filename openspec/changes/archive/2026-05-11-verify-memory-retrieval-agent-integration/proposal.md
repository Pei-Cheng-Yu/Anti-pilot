# Verify Memory Retrieval and Agent Integration

## Summary

Add repeatable smoke and integration coverage that proves learner memory is not only stored and retrievable, but actually influences correction and content-generation agent behavior. This extends the archived structured-output/pgvector memory work by testing realistic retrieval ranking, database candidate search, and live agent prompt/runtime paths.

## Motivation

The previous change established the memory architecture and pgvector-backed retrieval path. Existing tests prove the service contracts and graph plumbing, but the remaining confidence gap is behavioral:

- Does hybrid retrieval rank the right memory notes above unrelated notes in realistic data?
- Does consolidation create useful `ERROR_PATTERN` and `HEURISTIC` notes after repeated failed attempts?
- Does the correction flow retrieve and persist memory in the same end-to-end path a learner will use?
- Does live content generation receive memory context and produce content adapted to prior mistakes?
- Does the validator work with live structured output or a safe fallback under configured credentials?

This change turns those questions into explicit commands, tests, and inspection helpers.

## Goals

- Add a deterministic retrieval-quality test with multiple related and unrelated memory notes.
- Add an integration test proving repeated failed coding attempts create grouped memory and later retrieval returns the relevant notes.
- Add a correction-flow smoke test that starts from validation/correction evidence and verifies DB rows plus retrieval.
- Add a content-generation smoke path that seeds learner memory, runs the real ADK content generator, and exposes whether generated content uses memory context.
- Add a validator live smoke path for structured output, gated so it does not run in normal unit tests without credentials.
- Provide developer commands/scripts for manually verifying `LearningMemoryContext` and agent prompts/results.

## Non-Goals

- Do not require live LLM calls in the default CI/unit test suite.
- Do not add a separate search/resource recommendation agent unless one already exists.
- Do not replace the current hybrid scoring formula with a learned reranker.
- Do not depend on a paid cloud sandbox for validation.

## Success Criteria

- A DB-backed retrieval-quality test proves a FastAPI async error note outranks unrelated notes for `"fastapi async await route"`.
- A DB-backed consolidation test proves repeated failed attempts create `ERROR_PATTERN` plus `HEURISTIC` notes and retrieval groups them into `LearningMemoryContext`.
- A correction integration test proves correction evidence creates a `CodingProblemAttempt`, updates `LearnerMemoryNote`, and retrieves that note later.
- A real content-generation smoke command can run after seeded memory and print/inspect generated content and memory context evidence.
- Live LLM smoke tests are explicitly marked or script-gated and document required environment variables.
- OpenSpec tasks include exact commands for local WSL execution.
