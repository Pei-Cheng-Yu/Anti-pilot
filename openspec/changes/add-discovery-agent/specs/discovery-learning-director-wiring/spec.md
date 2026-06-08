## ADDED Requirements

### Requirement: Discovery Agent launches Learning Director as async background task
The Discovery Agent SHALL call `start_async_task("learning_director", instructions)` via the `AsyncSubAgentMiddleware` when all required entities (goal, profile) are confirmed. The call SHALL return immediately with a `task_id` and SHALL NOT block the conversation.

#### Scenario: Handoff triggered after entity confirmation
- **WHEN** the Discovery Agent has confirmed `GoalSpec` and `LearningProfile` are saved and calls `start_async_task`
- **THEN** the agent SHALL receive a `task_id` immediately and set `session_complete: true` and `roadmap_job_id: <task_id>` in the next `DiscoveryResponse`

#### Scenario: Learning Director runs non-blocking
- **WHEN** `start_async_task` is called
- **THEN** the Discovery Agent SHALL continue the conversation with the learner (e.g. "Your roadmap is being generated...") without waiting for the Learning Director to finish

#### Scenario: Discovery Agent can check task status
- **WHEN** the learner asks whether their roadmap is ready
- **THEN** the Discovery Agent SHALL call `check_async_task(task_id)` and report the current status (`pending`, `running`, `complete`, or `failed`) in its response

---

### Requirement: Learning Director is registered in langgraph.json as an async subagent
The `learning_director` graph SHALL be registered in `langgraph.json` with key `"learning_director"`. The `AsyncSubAgent` in the Discovery Agent SHALL use `graph_id="learning_director"` with no `url` (co-deployed ASGI transport in the same agent server container).

#### Scenario: Correct graph_id resolves at runtime
- **WHEN** the agent server starts and the Discovery Agent calls `start_async_task("learning_director", ...)`
- **THEN** the middleware SHALL resolve the graph to the registered `learning_director` graph without error

#### Scenario: Missing registration causes startup error
- **WHEN** `learning_director` is absent from `langgraph.json`
- **THEN** the agent server SHALL fail to start with a clear registration error rather than failing silently at runtime

---

### Requirement: Learning Director exposes a module-level graph variable for registration
`backend/app/langgraph/learning_director/agent.py` SHALL expose a module-level variable named `graph` containing the compiled DeepAgent graph, so `langgraph.json` can reference `app.langgraph.learning_director.agent:graph`.

#### Scenario: Graph variable available at import time
- **WHEN** the agent server imports `app.langgraph.learning_director.agent`
- **THEN** `graph` SHALL be a compiled LangGraph `StateGraph` (the DeepAgent) and SHALL NOT be `None` or an unawaited coroutine

---

### Requirement: Discovery Agent graph is registered in langgraph.json
The `discovery_agent` graph SHALL be registered in `langgraph.json` with key `"discovery_agent"`. The module SHALL expose a module-level `graph` variable at `app.langgraph.discovery_agent.agent:graph`.

#### Scenario: Discovery Agent graph registered
- **WHEN** the agent server starts
- **THEN** `discovery_agent` SHALL be available as a graph that can be invoked via the Agent Protocol API

---

### Requirement: Both agents share MCP server via MCP_SERVER_URL env var
Both the Discovery Agent and the Learning Director SHALL read `MCP_SERVER_URL` from the environment to connect to the FastAPI backend's MCP server. The agent server container SHALL set `MCP_SERVER_URL` to the internal Docker service URL of the backend container.

#### Scenario: MCP tools reachable from agent server container
- **WHEN** the Discovery Agent calls `goal_save_goal` or `learning_memory_retrieve_learning_memory`
- **THEN** the MCP call SHALL reach the FastAPI backend's MCP server at the configured `MCP_SERVER_URL` and return a valid response

#### Scenario: user_id injected into MCP tool calls
- **WHEN** the Discovery Agent invokes any MCP tool that accepts `user_id`
- **THEN** `user_id` SHALL be automatically injected from the `DiscoveryContext` via the `inject_user_id` tool interceptor — the agent SHALL NOT need to pass `user_id` explicitly in its tool call arguments

---

### Requirement: Agent server runs as a separate Docker container
A second Docker service (`agent-server`) SHALL run `langgraph up` using the same backend codebase. It SHALL be internal-only (not exposed to frontend) and SHALL connect to the same Postgres database and MCP server as the backend container.

#### Scenario: Agent server starts without exposing ports to frontend
- **WHEN** docker-compose starts both services
- **THEN** the `agent-server` container SHALL NOT expose any ports directly reachable by the frontend; only the `backend` container's ports are exposed

#### Scenario: Both containers share environment config
- **WHEN** both containers start
- **THEN** both SHALL use the same `DATABASE_URL` and `MCP_SERVER_URL` values so there is no split-brain between agent state and backend state
