# FastAPI, Agent, And Frontend API Wiring

This document explains how the backend should wire product APIs, services,
agents, MCP tools, and the database after the Discovery Agent and multi-goal
roadmap changes.

## Backend Boundary Rule

Keep frontend traffic on FastAPI. The frontend should not call MCP servers or
the LangGraph agent-server directly.

```text
Frontend
-> FastAPI route
-> service or internal agent-server client
-> agent graph or deterministic service
-> MCP tools when the agent needs backend capabilities
-> service layer
-> database
```

The service layer remains the final owner of validation and persistence. Agents
can reason, ask questions, generate plans, or call tools, but services should
still enforce ownership, IDs, state transitions, and database writes.

## Main Service And Agent Patterns

### Deterministic HTTP Service Path

Use this shape for product actions where the frontend already has explicit UI
context, such as updating a specific milestone.

```text
Frontend
-> FastAPI route
-> deterministic service
-> database
-> response DTO
```

Examples:

- `GET /v1/roadmaps`
- `GET /v1/roadmaps/{roadmap_id}`
- `POST /v1/roadmaps/{roadmap_id}/milestones/{milestone_id}/customize`
- `POST /v1/roadmaps/{roadmap_id}/skillpaths/{skillpath_id}/status`

### Internal Agent-Server Proxy Path

Use this shape when a user-facing conversation needs agent reasoning and tool
use. FastAPI is still the only public API.

```text
Frontend
-> FastAPI /v1/discovery/*
-> DiscoveryAgentServerClient
-> internal LangGraph agent-server
-> discovery_agent graph
-> MCP tools
-> goal/profile/memory services
-> Learning Director handoff
-> roadmap/content services
-> database
```

The internal agent-server is configured through `AGENT_SERVER_URL`. In Docker,
the backend points at `http://agent-server:2024`.

### MCP Tool Path

Use MCP tools for agent access to backend capabilities, not as frontend APIs.
MCP tools should call the same services that FastAPI routes use.

Examples:

- Discovery Agent calls safe goal/profile/memory tools.
- Learning Director calls goal, roadmap, memory, and content-related tools.
- Code correction MCP tools call `app.services.code_correction`.
- Memory hint MCP tools call `app.services.memory_service`.

## Discovery Conversation API For Frontend

Discovery is used for "create new goal" and "discuss this existing goal"
workflows.

### Create A New Discovery Conversation

Use this when the user starts a new goal from a create-new screen.

```http
POST /v1/discovery/conversations
Content-Type: application/json
```

Request:

```json
{
  "user_id": "user-123"
}
```

Response:

```json
{
  "conversation_id": "192faf7e-de51-4292-b734-3fee9af9a0fd"
}
```

The conversation starts with `goal_id = null`. When Discovery saves a new goal,
the backend binds the conversation to the generated `goal_id`.

### Create A Conversation Bound To An Existing Goal

Use this when the UI already knows which goal the user is discussing, such as a
per-roadmap or per-goal screen.

```http
POST /v1/discovery/conversations
Content-Type: application/json
```

Request:

```json
{
  "user_id": "user-123",
  "goal_id": "goal-abc"
}
```

FastAPI stores the `goal_id` on the conversation. Later message turns load that
stored value and pass it into the agent-server runtime context.

### Send A Discovery Message

```http
POST /v1/discovery/conversations/{conversation_id}/messages
Content-Type: application/json
```

Request:

```json
{
  "message": "I want to learn FastAPI async database access in four weeks."
}
```

Response:

```json
{
  "message": "What target outcome would prove this goal is complete?",
  "ui_hints": {
    "type": "text_input",
    "options": []
  },
  "session_complete": false,
  "roadmap_job_id": null,
  "roadmap_status": null
}
```

`ui_hints.type` can be:

- `text_input`
- `single_choice`
- `multi_choice`
- `confirm`

Choice hints include non-empty `options`.

When Discovery has saved the goal/profile and handed off to Learning Director,
the response should look like:

```json
{
  "message": "I've saved your goal and started generating your roadmap.",
  "ui_hints": null,
  "session_complete": true,
  "roadmap_job_id": "728d9444-893a-4724-888a-c9383c682222",
  "roadmap_status": "running"
}
```

After this, the frontend can poll/list roadmaps for the user.

```http
GET /v1/roadmaps?user_id=user-123
```

Then fetch the nested roadmap:

```http
GET /v1/roadmaps/{roadmap_id}?user_id=user-123
```

### Resume A Discovery Interrupt

If the agent uses an interrupt/resume interaction, send the selected value here.

```http
POST /v1/discovery/conversations/{conversation_id}/resume
Content-Type: application/json
```

Request:

```json
{
  "selection": "Yes, generate roadmap"
}
```

Response is the same `DiscoveryResponse` shape as `/messages`.

### Frontend Conversation Rules

- Store `conversation_id` in the current create-new/discovery view.
- Do not send `goal_id` on message turns; FastAPI loads it from the conversation.
- For create-new flows, omit `goal_id` on conversation creation.
- For per-goal/per-roadmap discussion flows, create the conversation with the
  known `goal_id`.
- Treat `session_complete: true` as "roadmap generation has started", not
  "all content is fully generated".
- Use `roadmap_job_id` and later roadmap reads to update the UI.

## Multi-Goal And Roadmap Ownership

One user can have multiple goals. Each new goal has a stable `goal_id`.

For new writes:

```text
user_id -> many goals
goal_id -> one primary roadmap
conversation_id -> zero or one bound goal_id
```

This is why a Discovery conversation must bind back to the goal it creates. If a
conversation has no `goal_id`, later turns only know the user, which becomes
ambiguous once the user has more than one goal.

## Milestone Customization API For Frontend

Use this when the user is looking at a specific roadmap milestone and asks to
customize it. The route requires explicit roadmap and milestone context.

```http
POST /v1/roadmaps/{roadmap_id}/milestones/{milestone_id}/customize?user_id=user-123
Content-Type: application/json
```

Request with concrete updates:

```json
{
  "instructions": "Make this milestone more project-based.",
  "title": "Async API Project Foundations",
  "objective": "Build a small async FastAPI feature with tested DB access.",
  "estimated_hours": 5,
  "mark_skillpaths_for_regeneration": true
}
```

Response:

```json
{
  "applied": true,
  "message": "Milestone updated.",
  "milestone": {
    "milestone_id": "milestone-123",
    "roadmap_id": "roadmap-123",
    "title": "Async API Project Foundations",
    "description": "...",
    "objective": "Build a small async FastAPI feature with tested DB access.",
    "estimated_hours": 5,
    "order_index": 1,
    "dependency_titles": [],
    "prerequisite_milestone_ids": [],
    "status": "ready",
    "need_modification": false,
    "revision_reason": null
  },
  "affected_skillpath_ids": ["skillpath-1", "skillpath-2"],
  "follow_up_required": false
}
```

If the request only has vague instructions and no concrete fields to apply, the
service asks for a follow-up instead of making an unsafe change:

```json
{
  "applied": false,
  "message": "What would you like to change about this milestone?",
  "milestone": null,
  "affected_skillpath_ids": [],
  "follow_up_required": true
}
```

Frontend behavior:

- Call this from a milestone-specific UI, not from a global freeform chat.
- Send only fields the user actually wants to change.
- If `follow_up_required` is true, keep the user in the customization UI and
  ask for a more specific change.
- If `affected_skillpath_ids` is non-empty, treat those skillpaths as stale and
  show regeneration/review UI.
- Ownership failures or missing roadmap/milestone return `404`.

## Hint And Code-Correction Wiring

### Current Frontend Hint API

`POST /v1/signals/struggle` is the current frontend-facing hint-like endpoint.
It accepts a struggle signal, asks the LLM for a short hint/concept, and inserts
a review concept into the FSRS loop.

Request:

```json
{
  "user_id": "user-123",
  "roadmap_id": "roadmap-123",
  "milestone_id": "milestone-123",
  "skillpath_id": "skillpath-123",
  "code_context": "The learner's current code or editor context.",
  "diagnostic_message": "Runtime error or validation feedback.",
  "language": "python"
}
```

Response:

```json
{
  "hint": "Check where the coroutine is created and where it is awaited.",
  "concept_name": "Python async await",
  "action_required": true
}
```

### Memory-Aware Hint Service

The deeper memory-aware hint path exists behind the service/MCP boundary:

```text
agent or service caller
-> memory_service.generate_memory_aware_hint(...)
-> retrieve learner memory
-> rerank bounded memory candidates
-> optional hint advisor
-> validated low-spoiler HintResponse
```

Agents can call the MCP `learning_memory_generate_memory_aware_hint` tool. A
dedicated frontend HTTP wrapper can be added later if the product wants this
same memory-aware hint behavior outside an agent flow.

If a FastAPI wrapper is added, it should accept the `HintRequest` shape and
return `HintResponse`.

#### `HintRequest`

Required:

- `user_id: string`
- `task_prompt: string`

Optional:

- `skillpath_id: string | null = null`
- `content_id: string | null = null`
- `submitted_code: string = ""`
- `language: string = "python"`
- `concept_keys: string[] = []`
- `validation_feedback: string | null = null`
- `hint_level: "nudge" | "conceptual" | "specific" | "near_solution" = "nudge"`

Example request:

```json
{
  "user_id": "user-123",
  "skillpath_id": "skillpath-async-db",
  "content_id": "content-coding-problem-1",
  "task_prompt": "Fix the FastAPI route so it awaits the async database call.",
  "submitted_code": "def get_item(id):\n    item = repo.get_item(id)\n    return item",
  "language": "python",
  "concept_keys": ["async", "await", "FastAPI dependency injection"],
  "validation_feedback": "The route returned a coroutine object instead of the item.",
  "hint_level": "nudge"
}
```

#### `HintResponse`

Required:

- `hint: string`
- `hint_level: "nudge" | "conceptual" | "specific" | "near_solution"`

Optional/defaulted:

- `teaching_action: "normal_hint" | "quick_recap" | "contrast_example" | "quick_recap_then_hint" = "normal_hint"`
- `selected_memory_ids: string[] = []`
- `selected_memories: SelectedMemoryMetadata[] = []`
- `focused_concepts: string[] = []`
- `quick_recap: string | null = null`
- `contrast_example: string | null = null`
- `used_memory: boolean = false`

`SelectedMemoryMetadata`:

Required:

- `memory_id: string`
- `memory_type: "background" | "error_pattern" | "heuristic" | "mastery_signal" | "preference_signal"`
- `title: string`

Optional:

- `reason: string = ""`

Example response:

```json
{
  "hint": "Look at the call that returns a coroutine. What keyword turns that coroutine into the actual result?",
  "hint_level": "nudge",
  "teaching_action": "normal_hint",
  "selected_memory_ids": ["memory-await-error"],
  "selected_memories": [
    {
      "memory_id": "memory-await-error",
      "memory_type": "error_pattern",
      "title": "Forgets to await async DB calls",
      "reason": "Same async/await failure pattern."
    }
  ],
  "focused_concepts": ["async", "await"],
  "quick_recap": null,
  "contrast_example": null,
  "used_memory": true
}
```

### Code Correction Path

Code correction currently exists as service and MCP entrypoints:

```text
agent or service caller
-> code_correction.submit_code_attempt(...)
-> validator agent
-> code_correction.process_code_correction(...)
-> memory retrieval/rerank
-> attempt persistence
-> memory consolidation
-> CodeSubmissionResult
```

MCP tools:

- `code_correction_submit_code_attempt`
- `code_correction_process_code_correction`

There is not yet a dedicated frontend HTTP route for the full code-attempt
submission path. If the frontend needs direct submission, add a FastAPI route
that calls `app.services.code_correction.submit_code_attempt(...)` and keeps the
same service-owned validation/persistence boundary.

There are two useful wrapper levels.

### Wrapper Level 1: Submit Raw Code Attempt

Use this when the frontend has raw submitted code and wants backend validation,
correction, memory retrieval, attempt persistence, and memory consolidation in
one call.

Suggested route:

```http
POST /v1/code-attempts
Content-Type: application/json
```

The route should call:

```python
code_correction.submit_code_attempt(request, session)
```

Request schema: `CodeValidationRequest`.

#### `CodeValidationRequest`

Required:

- `user_id: string`
- `skillpath_id: string`
- `content_id: string`
- `language: string`
- `coding_problem_prompt: string`
- `submitted_code: string`

Optional:

- `starter_code: string | null = null`
- `expected_output: string | null = null`
- `compile_error: string | null = null`
- `runtime_error: string | null = null`
- `stdout: string | null = null`
- `stderr: string | null = null`
- `test_results: TestCaseResult[] = []`
- `timeout_seconds: integer = 20`

`TestCaseResult`:

Required:

- `name: string`
- `passed: boolean`

Optional:

- `message: string | null = null`

Example request:

```json
{
  "user_id": "user-123",
  "skillpath_id": "skillpath-async-db",
  "content_id": "content-coding-problem-1",
  "language": "python",
  "coding_problem_prompt": "Implement an async FastAPI route that fetches one item from the database.",
  "submitted_code": "async def get_item(id):\n    item = repo.get_item(id)\n    return item",
  "starter_code": "async def get_item(id):\n    pass",
  "expected_output": "Returns a JSON item object.",
  "test_results": [
    {
      "name": "returns item json",
      "passed": false,
      "message": "Got coroutine object instead of item."
    }
  ],
  "timeout_seconds": 20
}
```

Response schema: `CodeSubmissionResult`.

#### `CodeSubmissionResult`

Required:

- `validation: CodeValidationResult`
- `correction: CodeCorrectionResult`

`CodeValidationResult` required:

- `correctness: "correct" | "partially_correct" | "incorrect" | "runtime_error"`
- `has_serious_blocker: boolean`
- `validation_strategy: string`
- `feedback_summary: string`

`CodeValidationResult` optional/defaulted:

- `blocker_reason: string | null = null`
- `compile_error: string | null = null`
- `runtime_error: string | null = null`
- `stdout: string | null = null`
- `stderr: string | null = null`
- `test_results: TestCaseResult[] = []`
- `generated_artifacts: GeneratedValidationArtifact[] = []`
- `detected_concepts: string[] = []`
- `detected_mistakes: string[] = []`
- `confidence_score: number = 0.0`

`GeneratedValidationArtifact` required:

- `path: string`
- `purpose: string`

`GeneratedValidationArtifact` optional:

- `content: string | null = null`

### Wrapper Level 2: Process Evaluated Correction Evidence

Use this when another sandbox or evaluator already produced compile/runtime/test
evidence and the backend only needs to normalize, retrieve memory, persist the
attempt, and consolidate memory.

Suggested route:

```http
POST /v1/code-corrections
Content-Type: application/json
```

The route should call:

```python
code_correction.process_code_correction(request, session)
```

Request schema: `CodeCorrectionRequest`.

#### `CodeCorrectionRequest`

Required:

- `user_id: string`
- `skillpath_id: string`
- `content_id: string`
- `coding_problem_prompt: string`
- `submitted_code: string`
- `language: string`

Optional:

- `compile_error: string | null = null`
- `runtime_error: string | null = null`
- `test_results: TestCaseResult[] = []`
- `correctness: "correct" | "partially_correct" | "incorrect" | "runtime_error" | null = null`
- `score: number | null = null`
- `feedback_summary: string | null = null`
- `detected_concepts: string[] = []`
- `detected_mistakes: string[] = []`
- `top_k_notes: integer = 5`
- `top_k_attempts: integer = 3`

Example request:

```json
{
  "user_id": "user-123",
  "skillpath_id": "skillpath-async-db",
  "content_id": "content-coding-problem-1",
  "coding_problem_prompt": "Implement an async FastAPI route that fetches one item from the database.",
  "submitted_code": "async def get_item(id):\n    item = repo.get_item(id)\n    return item",
  "language": "python",
  "runtime_error": "TypeError: Object of type coroutine is not JSON serializable",
  "test_results": [
    {
      "name": "returns item json",
      "passed": false,
      "message": "Got coroutine object instead of item."
    }
  ],
  "detected_concepts": ["async", "await"],
  "detected_mistakes": ["missing await"],
  "top_k_notes": 5,
  "top_k_attempts": 3
}
```

Response schema: `CodeCorrectionResult`.

#### `CodeCorrectionResult`

Required:

- `inferred_correctness: "correct" | "partially_correct" | "incorrect" | "runtime_error"`
- `feedback_summary: string`
- `retrieval_context: LearningMemoryContext`
- `persistence_result: RecordAndConsolidateAttemptResult`

Optional/defaulted:

- `suggested_focus: string[] = []`
- `memory_rerank: MemoryRerankResult`

`RecordAndConsolidateAttemptResult` required:

- `attempt: CodingProblemAttempt`

Optional/defaulted:

- `updated_notes: LearnerMemoryNote[] = []`

`CodingProblemAttempt` required:

- `attempt_id: string`
- `user_id: string`
- `skillpath_id: string`
- `content_id: string`
- `submitted_code: string`
- `language: string`
- `correctness: "correct" | "partially_correct" | "incorrect" | "runtime_error"`
- `feedback_summary: string`
- `submitted_at: datetime string`

`CodingProblemAttempt` optional/defaulted:

- `detected_concepts: string[] = []`
- `detected_mistakes: string[] = []`
- `compile_error: string | null = null`
- `runtime_error: string | null = null`
- `score: number | null = null`
- `test_results: TestCaseResult[] = []`

`LearningMemoryContext` optional/defaulted fields:

- `mastery_state: SkillMasteryState | null = null`
- `recent_attempts: CodingProblemAttempt[] = []`
- `active_error_patterns: LearnerMemoryNote[] = []`
- `mastery_signals: LearnerMemoryNote[] = []`
- `teaching_heuristics: LearnerMemoryNote[] = []`
- `background_notes: LearnerMemoryNote[] = []`
- `relevant_notes: LearnerMemoryNote[] = []`

`MemoryRerankResult` fields:

- `purpose: "hint_generation" | "code_correction" | "content_generation"`
- `selected_memories: SelectedMemoryMetadata[] = []`
- `teaching_action: "normal_hint" | "quick_recap" | "contrast_example" | "quick_recap_then_hint" = "normal_hint"`
- `focused_concepts: string[] = []`
- `guidance: string = ""`

`LearnerMemoryNote` important response fields:

- `memory_id: string`
- `user_id: string`
- `memory_type: "background" | "error_pattern" | "heuristic" | "mastery_signal" | "preference_signal"`
- `title: string`
- `summary: string`
- `tags: string[] = []`
- `linked_concepts: string[] = []`
- `linked_skillpath_ids: string[] = []`
- `linked_content_ids: string[] = []`
- `evidence_attempt_ids: string[] = []`
- `salience_score: number = 0.5`
- `status: "active" | "watch" | "resolved" = "active"`
- `created_at: datetime string`
- `last_seen_at: datetime string | null = null`
- `last_used_at: datetime string | null = null`

Frontend behavior:

- Use `CodeValidationRequest` if the backend should run the validator agent.
- Use `CodeCorrectionRequest` if the caller already has evaluator evidence.
- Display `validation.feedback_summary` or `correction.feedback_summary` as the
  main learner-facing result.
- Use `correction.suggested_focus` for next-step UI chips.
- Use `correction.memory_rerank.guidance` and selected memory titles only for
  internal/adaptive teaching UI unless product explicitly wants to expose memory
  context.
- Do not let the frontend directly create or mutate memory notes; let the
  correction service consolidate memory through the service boundary.

## Recommended Frontend Flow

### Create-New Goal

```text
1. POST /v1/discovery/conversations with user_id.
2. Store conversation_id in UI state.
3. POST learner messages to /messages.
4. Render message and ui_hints each turn.
5. When session_complete is true, show roadmap generation state.
6. GET /v1/roadmaps?user_id=...
7. GET /v1/roadmaps/{roadmap_id}?user_id=...
```

### Existing Goal Discussion

```text
1. UI already knows selected goal_id or roadmap context.
2. POST /v1/discovery/conversations with user_id and goal_id.
3. Send messages to /messages.
4. Backend keeps every turn scoped to that bound goal_id.
```

### Customize Milestone

```text
1. User opens a milestone inside one roadmap.
2. UI calls POST /v1/roadmaps/{roadmap_id}/milestones/{milestone_id}/customize.
3. If applied, refresh the roadmap.
4. If affected_skillpath_ids is non-empty, show those skillpaths as needing
   review/regeneration.
5. If follow_up_required, ask for a more concrete customization request.
```
