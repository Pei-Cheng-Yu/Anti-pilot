## 1. Agent-Server API Discovery

- [x] 1.1 Inspect the running agent-server OpenAPI/docs or routes to identify the correct `langgraph-api==0.7.71` thread/run endpoint for invoking `discovery_agent`
- [x] 1.2 Identify the supported payload shape for thread id, graph id/assistant id, input messages, context, and resume commands
- [x] 1.3 Record the chosen endpoint and payload shape in `design.md` or implementation comments

## 2. Configuration

- [x] 2.1 Add `AGENT_SERVER_URL` to backend settings with local default `http://localhost:2024`
- [x] 2.2 Set backend container `AGENT_SERVER_URL` to `http://agent-server:2024` in `docker-compose.yml`
- [x] 2.3 Keep `agent-server` internal-only and avoid exposing it as a frontend API surface

## 3. Agent-Server Client

- [x] 3.1 Add a small Discovery Agent client module that posts message turns to the configured agent-server
- [x] 3.2 Add resume support that sends `Command(resume=selection)` or the LangGraph API equivalent to the same conversation thread
- [x] 3.3 Normalize `structured_response` and final assistant message content into `DiscoveryResponse`
- [x] 3.4 Convert agent-server connection failures into a typed unavailable error for FastAPI to return as HTTP 503
- [x] 3.5 Convert no-pending-interrupt responses into a typed resume error for FastAPI to return as HTTP 400

## 4. FastAPI Router Integration

- [x] 4.1 Replace local `get_discovery_graph().ainvoke(...)` message handling with the agent-server client
- [x] 4.2 Replace local resume handling with the agent-server client
- [x] 4.3 Keep `discovery_conversations` ownership lookup before proxying any request
- [x] 4.4 Remove or deprecate FastAPI dependency on module-level `discovery_agent.graph` for message/resume routes

## 5. Tests

- [x] 5.1 Update discovery API tests to mock the agent-server HTTP client instead of a local fake graph
- [x] 5.2 Add a test that message turns pass `conversation_id` as thread id and include `user_id` context
- [x] 5.3 Add a test that agent-server unavailable maps to HTTP 503
- [x] 5.4 Add a test that invalid or missing conversations still return HTTP 404 before any agent-server call
- [x] 5.5 Add a test that resume failures without pending interrupts map to HTTP 400
- [x] 5.6 Run focused discovery tests and existing API tests

## 6. Live Verification

- [x] 6.1 Run `docker compose up --build backend mcp agent-server` and verify all three services stay running
- [x] 6.2 Create a discovery conversation through FastAPI
- [x] 6.3 Send a discovery message through FastAPI and verify no local graph initialization error occurs
- [x] 6.4 Confirm agent-server logs show `discovery_agent` handling the turn
- [x] 6.5 Confirm LangSmith shows Discovery Agent MCP calls using the expected `user_id`
