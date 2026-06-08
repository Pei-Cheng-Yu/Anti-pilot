## Why

Memory writes, retrieval, hint generation, code correction, and content generation now have working pieces, but callers can still treat them as separate service details. Before adding a discovery agent, the backend needs one public memory boundary so agents, MCP tools, and future API routes use the same integrity-protected write path and the same purpose-aware rerank policy.

## What Changes

- Add a unified public memory service facade for durable memory operations.
- Adapt current memory-facing workflows to use the unified facade or explicitly remain internal helper implementation.
- Route MCP memory tools through the unified facade instead of exposing lower-level memory write details directly.
- Define the discovery-agent memory write contract: goal/profile remain source-of-truth entities, while durable learner facts and preferences may be written as memory notes through the unified memory service.
- Update code correction to rerank retrieved memories with `purpose=code_correction` before producing correction focus/guidance.
- Update content generation to rerank retrieved memories with `purpose=content_generation` before building generation prompts.
- Keep memory rerank advisory only: rerank output may shape feedback and prompts but must not persist memory or mutate roadmaps.
- Do not add scheduled memory decay, predictive forgetting, conflict-review queues, or roadmap adaptation in this change.

## Capabilities

### New Capabilities

- `unified-memory-service`: Provide one public service boundary for memory writes, retrieval, attempt consolidation, hints, and future agent-facing memory use.

### Modified Capabilities

- `memory-rerank-policy`: Code correction and content generation must consume purpose-specific rerank results rather than only raw retrieved memory context.

## Impact

- Affects memory services, MCP memory tools, code-correction service, content-generation graph nodes/prompts, direct memory write paths, attempt-consolidation paths, hint generation, and memory tests.
- Adds or adjusts tests proving memory write callers use the unified service boundary.
- Adds a workflow audit so currently implemented memory consumers are migrated, documented as internal helpers, or intentionally deferred.
- Adds tests proving code correction and content generation call the rerank policy with the correct purpose and validate selected memory IDs.
- Adds docs describing which agents should update goal/profile entities and when they should also write `preference_signal` or `background` memory notes.
