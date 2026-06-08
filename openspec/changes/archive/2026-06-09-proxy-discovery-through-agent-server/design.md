## Context

The active Discovery Agent implementation added FastAPI endpoints and an internal LangGraph agent-server. The containers now start far enough for the agent-server to load graphs, but the FastAPI `/v1/discovery/conversations/{id}/messages` endpoint still calls a local module-level `discovery_agent.graph`. In normal backend runtime that graph is intentionally not initialized, so message turns return HTTP 500 with `Discovery Agent graph is not initialized.`

The target product boundary is clear: the frontend calls FastAPI only. The agent-server is internal infrastructure for LangGraph graph execution, thread persistence, and async Discovery Agent to Learning Director handoff.

## Goals / Non-Goals

**Goals:**

- Keep `/v1/discovery/*` as the only frontend-facing discovery API.
- Move Discovery Agent execution behind an internal FastAPI-to-agent-server proxy.
- Preserve `conversation_id` as the frontend-visible conversation identifier and LangGraph `thread_id`.
- Keep FastAPI responsible for conversation ownership and user scoping.
- Let LangGraph API own graph persistence through `POSTGRES_URI`.
- Normalize agent-server responses into the existing `DiscoveryResponse` schema.
- Remove the current local graph initialization failure path from FastAPI message handling.

**Non-Goals:**

- Do not expose agent-server directly to the frontend.
- Do not replace MCP tools or service-layer persistence.
- Do not change the `DiscoveryResponse` frontend contract.
- Do not implement streaming/SSE in this change.
- Do not build a new custom checkpointer path inside FastAPI for discovery turns.

## Decisions

### Decision 1: FastAPI proxies to agent-server instead of invoking a local graph

FastAPI will call the internal LangGraph API server over HTTP for message and resume turns. This keeps product routing, auth, CORS, and user scoping in FastAPI while delegating thread/run semantics to LangGraph API.

Alternative considered: initialize a Discovery Agent graph inside FastAPI with `AsyncPostgresSaver`. This works for direct in-process invocation but duplicates responsibilities with agent-server, creates two execution modes, and conflicts with the current two-container design.

### Decision 2: `conversation_id` remains the LangGraph `thread_id`

The `discovery_conversations` table remains the ownership mapping:

```text
conversation_id -> user_id
```

The agent-server uses the same `conversation_id` as LangGraph `thread_id`. FastAPI validates ownership before proxying the request.

Alternative considered: let agent-server create opaque thread ids and return them directly. This leaks LangGraph concepts to the product API and complicates frontend state.

### Decision 3: Configure agent-server URL explicitly

Add `AGENT_SERVER_URL` to backend settings. In Docker Compose this points to:

```text
http://agent-server:2024
```

Local development can set:

```text
http://localhost:2024
```

### Decision 4: Normalize LangGraph API outputs in one client module

Create a small agent-server client module that:

- sends message/resume requests
- includes graph id, thread id, user context, and input payload
- parses `structured_response` or final message content
- returns `DiscoveryResponse`
- converts HTTP/network/API errors into clear FastAPI errors

This keeps `routers/discovery.py` thin and testable.

## Risks / Trade-offs

- [Risk] Exact LangGraph API endpoint shape may differ by `langgraph-api` version.
  - Mitigation: inspect the running agent-server OpenAPI/docs and isolate version-specific request handling in the client module.

- [Risk] Agent-server may return a response shape without `structured_response`.
  - Mitigation: reuse `parse_discovery_response` fallback logic against final assistant message content.

- [Risk] Context propagation into MCP tools may differ between direct graph invocation and LangGraph API invocation.
  - Mitigation: include `context={"user_id": ...}` or supported equivalent in the run request and verify in a live smoke trace that MCP calls receive the correct `user_id`.

- [Risk] Backend can start before agent-server is ready.
  - Mitigation: return a clear `503` from discovery message/resume endpoints when agent-server is unreachable.

## Migration Plan

1. Add `AGENT_SERVER_URL` setting and Docker Compose environment value.
2. Add agent-server HTTP client for Discovery Agent runs.
3. Replace local graph calls in `routers/discovery.py` with the client.
4. Update tests to mock agent-server HTTP responses instead of fake local graph objects.
5. Verify `docker compose up --build backend mcp agent-server` starts.
6. Manually create a discovery conversation and send a message through FastAPI.

Rollback: restore local graph invocation in `routers/discovery.py` and unset `AGENT_SERVER_URL`, but this reintroduces the local graph initialization/checkpointer problem.

## Open Questions

- Resolved: use `POST /threads/{thread_id}/runs/wait`, with `assistant_id: "discovery_agent"`, `input: {"messages": [...]}` for message turns, `command: {"resume": selection}` for resume turns, `context: {"user_id": ...}`, and `config: {"configurable": {"thread_id": conversation_id}}`. This matches the LangGraph Agent Server run/wait API shape for graph-name assistants and keeps `conversation_id` as the LangGraph thread id.
