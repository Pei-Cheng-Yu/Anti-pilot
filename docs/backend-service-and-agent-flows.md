# Backend Service And Agent Flows

This document summarizes what each backend service is responsible for, which agents are involved, and which product flows are already wrapped versus still needing an API/service wrapper.

## Service Map

### `app.services.goal`

Owns goal-level data. Use this service when the product needs to create, update, or retrieve the learner's high-level learning goal.

Typical responsibility:

- Store the user's target outcome, constraints, criteria, and deadline.
- Provide goal context to roadmap planning and downstream learning flows.

Agent involvement:

- Goal data is usually input context for planner/content agents.
- The service itself is deterministic persistence/retrieval logic.

### `app.services.learning_profile`

Owns learner profile data. Use this service when the product needs the learner's baseline level, confidence, weak areas, prior knowledge, pace, recap preference, and similar personalization inputs.

Typical responsibility:

- Store and retrieve learner profile fields.
- Provide stable learner context for roadmap planning, content generation, and memory-aware adaptation.

Agent involvement:

- Profile data is context for agents.
- The service itself is deterministic.

### `app.services.roadmap`

Owns roadmap structure persistence and retrieval.

Main functions:

- `save_roadmap(...)`: persists planner output into roadmap, milestone, skillpath, and content tables.
- `get_roadmap_full(user_id, roadmap_id, session)`: returns a nested `RoadmapFull`.
- `update_milestone(...)`: patches a saved milestone.
- `update_skillpath(...)`: patches a saved skillpath.
- `save_generated_skillpaths(...)`: persists generated learning content for existing skillpaths.

Important ordering behavior:

- Milestones are returned sorted by `milestone.order_index`.
- Learning contents are returned sorted by `learning_content.order_index`.
- Skillpaths currently do not have `order_index`; their order comes from stored relationship/list order and `prerequisite_skillpath_ids` can be used by clients to derive dependency order.

Agent involvement:

- The planner graph generates milestone and skillpath plans.
- The learning director calls `save_roadmap(...)` after generation.
- The content-generation flow calls `get_roadmap_full(...)` to load saved roadmap context.

Existing wrappers:

- MCP tool exists for `get_roadmap_full`.
- Normal frontend/API endpoint should be checked separately; this service is ready to be wrapped by one.

### `app.services.learning_memory`

Owns learner memory, attempts, mastery state, and memory lifecycle.

Main responsibilities:

- Record coding attempts.
- Retrieve relevant memory context for a user/task.
- Create and update memory notes such as error patterns, heuristics, and mastery signals.
- Update skill mastery state from attempt outcomes.
- Consolidate repeated failures and successes into long-lived learning memory.

Important functions:

- `retrieve_learning_memory(...)`: returns `LearningMemoryContext`.
- `record_and_consolidate_attempt(...)`: records an attempt and updates memory/mastery.
- `add_memory_note(...)`, `update_memory_note(...)`, `resolve_memory_note(...)`: lower-level memory note operations.

Memory lifecycle examples:

- Bad attempt creates or reactivates an `ERROR_PATTERN`.
- Related repeated bad attempts increase salience.
- Correct follow-up lowers salience and can move an error pattern from `active` to `watch`.
- Repeated related successes can resolve an old error pattern and create/update a `MASTERY_SIGNAL`.

Agent involvement:

- The normal memory update path is deterministic.
- An optional `MemoryConsolidationJudgmentProvider` can let an agent/reranker advise bounded salience and mastery changes.
- The service remains the final DB authority; an agent does not directly write memory state.

### `app.services.learning_memory_retriever`

Owns candidate retrieval for memory notes.

Retrieval sources:

- Vector candidates using pgvector cosine distance.
- Keyword candidates using Postgres full-text search.
- Scope candidates using skillpath/content/concept links.

Final rerank happens in `learning_memory.py` using:

```python
0.55 * vector_score
+ 0.25 * keyword_score
+ 0.15 * concept_boost
+ 0.05 * salience_component
```

Agent involvement:

- No agent is involved in retrieval itself.
- Retrieved memory is passed into downstream agents as context.

### `app.services.code_correction`

Owns the coding-submission correction and memory update pipeline.

There are two levels:

1. `process_code_correction(request, session)`

   Use when validation/evaluator evidence already exists.

   Input:

   - `CodeCorrectionRequest`
   - compile/runtime/test evidence
   - detected concepts/mistakes if available

   Behavior:

   - Infers correctness when needed.
   - Retrieves relevant learning memory.
   - Records and consolidates the attempt.
   - Returns `CodeCorrectionResult`.

2. `submit_code_attempt(request, session, ...)`

   Use when the caller has raw learner code and wants the whole product flow.

   Input:

   - `CodeValidationRequest`

   Behavior:

   - Calls the validator agent.
   - Converts validator output into a correction request.
   - Calls `process_code_correction(...)`.
   - Returns `CodeSubmissionResult`.

Existing wrappers:

- MCP tool exists for `process_code_correction`.
- MCP tool exists for `submit_code_attempt`.
- A normal frontend/API endpoint for `submit_code_attempt` still appears to be the missing product-facing wrapper.

## Main Flows

### Roadmap Planning Flow

```text
User goal/profile
-> planner LangGraph
-> milestone generation
-> skillpath generation
-> learning_director saves output
-> roadmap.save_roadmap(...)
-> DB roadmap/milestone/skillpath rows
```

Agents involved:

- Planner graph / roadmap planner.

Services involved:

- `goal`
- `learning_profile`
- `roadmap`

What is deterministic:

- DB persistence through `roadmap.save_roadmap(...)`.

### Roadmap Retrieval Flow

```text
client or agent asks for roadmap
-> roadmap.get_roadmap_full(user_id, roadmap_id, session)
-> RoadmapFull
```

Returned shape:

```text
RoadmapFull
  -> milestones sorted by order_index
    -> skillpaths nested under milestones
      -> learning_contents sorted by order_index
```

Agents involved:

- None in the retrieval itself.
- Learning director/content generation may call this to load context.

Still needed:

- If frontend needs direct HTTP access, expose this through a route if not already present.

### Learning Content Generation Flow

```text
saved roadmap
-> learning_director loads roadmap via roadmap.get_roadmap_full(...)
-> content generation LangGraph
-> retrieve memory per skillpath
-> ADK content generator creates article/practice/quiz content
-> roadmap.save_generated_skillpaths(...)
-> DB learning_contents
```

Agents involved:

- Content-generation LangGraph orchestration.
- ADK content generator agent for skillpath content.

Services involved:

- `roadmap`
- `learning_memory`
- `learning_memory_retriever`

What to observe in LangSmith:

- `learning_memory_retrieval_diagnostics_by_skillpath`
- `learning_memory_contexts_by_skillpath`
- `generated_skillpaths`

Successful memory-aware generation should show:

```json
{
  "status": "retrieved"
}
```

And generated content should adapt to retrieved memory, for example by mentioning prior `await`, `async`, coroutine, or route-handler mistakes when those memories are relevant.

### Code Submission Flow

This is the full product-level coding attempt flow that already exists as a service function:

```text
CodeValidationRequest
-> app.services.code_correction.submit_code_attempt(...)
-> app.validators.deepagent_validator.validate_code_submission(...)
-> CodeValidationResult
-> build_correction_request_from_validation(...)
-> CodeCorrectionRequest
-> app.services.code_correction.process_code_correction(...)
-> learning_memory.retrieve_learning_memory(...)
-> learning_memory.record_and_consolidate_attempt(...)
-> CodeSubmissionResult
```

Agents involved:

- `deepagent_validator.validate_code_submission(...)` is the validator agent step.

Deterministic service steps:

- Building `CodeCorrectionRequest`.
- Retrieving memory.
- Recording the attempt.
- Consolidating memory/mastery state.
- Returning `CodeSubmissionResult`.

Existing wrappers:

- Service wrapper: `code_correction.submit_code_attempt(...)`.
- MCP wrapper: `code_correction.submit_code_attempt` tool.

Still needed for frontend:

- A normal API endpoint that accepts `CodeValidationRequest`, calls `code_correction.submit_code_attempt(...)`, and returns `CodeSubmissionResult`.

Suggested route shape:

```python
@router.post("/code-submissions", response_model=CodeSubmissionResult)
async def submit_code_attempt_api(
    request: CodeValidationRequest,
    session: AsyncSession = Depends(get_session),
):
    return await code_correction.submit_code_attempt(request, session)
```

## What Still Needs A Product-Facing Service Or API

### 1. Frontend code submission endpoint

Current status:

- Full service exists.
- MCP tool exists.
- Normal frontend/API route appears missing.

Needed:

- Add an HTTP route for learner code submission.
- The route should call `app.services.code_correction.submit_code_attempt(...)`.
- The route should return `CodeSubmissionResult`.

Why:

- This lets VS Code/frontend submit learner code and get validation, correction, attempt persistence, and memory update in one call.

### 2. Optional roadmap item read endpoints

Current status:

- `get_roadmap_full(...)` exists.
- `update_milestone(...)` and `update_skillpath(...)` can fetch rows internally before patching.
- Clean read-only functions like `get_milestone(...)` or `get_skillpath(...)` do not appear to exist.

Needed only if product requires it:

- `get_milestone(user_id, milestone_id, session)`
- `get_skillpath(user_id, skillpath_id, session)`

Why:

- Useful if frontend wants to render or refresh one milestone/skillpath without fetching the whole roadmap.

### 3. Optional skillpath ordering contract

Current status:

- Skillpaths do not have `order_index`.
- Frontend/team may use `prerequisite_skillpath_ids` for dependency sorting.

Needed only if product requires exact display order:

- Add `skillpath.order_index`.
- Sort skillpaths by `order_index` in `get_roadmap_full(...)`.

Why:

- Prerequisites define dependency, not always display order.
- Parallel skillpaths can have ambiguous ordering without an explicit order field.

## Quick Reference

| Need | Current best entrypoint | Agent involved? | Notes |
| --- | --- | --- | --- |
| Save generated roadmap | `roadmap.save_roadmap(...)` | Planner before service | Deterministic persistence |
| Retrieve full roadmap | `roadmap.get_roadmap_full(...)` | No | Milestones/content ordered; skillpath order not explicit |
| Generate content | Learning director + content graph | Yes, ADK content generator | Retrieves memory before generation |
| Validate submitted code only | `validate_code_submission(...)` | Yes, validator | Does not persist memory by itself |
| Submit code and update memory | `code_correction.submit_code_attempt(...)` | Yes, validator | Full service wrapper already exists |
| Process already-validated correction | `code_correction.process_code_correction(...)` | No | Deterministic memory/correction pipeline |
| Retrieve learner memory | `learning_memory.retrieve_learning_memory(...)` | No | Uses vector, keyword, scope, salience scoring |
| Update memory from attempt | `learning_memory.record_and_consolidate_attempt(...)` | Optional judgment provider | Service owns final DB update |
