## Why

The discovery FastAPI endpoint currently tries to invoke a module-local Discovery Agent graph, which returns HTTP 500 when the backend process has not initialized that graph. The target architecture keeps the frontend on FastAPI only while the internal agent-server owns LangGraph graph execution, thread persistence, and async Learning Director handoff.

## What Changes

- Change the FastAPI discovery message and resume endpoints to proxy requests to the internal LangGraph agent-server instead of calling a local graph object.
- Keep FastAPI responsible for conversation ownership, `conversation_id -> user_id` validation, request/response normalization, and frontend-facing API shape.
- Keep agent-server responsible for Discovery Agent execution, LangGraph thread state, persistence, and async subagent task lifecycle.
- Add backend configuration for `AGENT_SERVER_URL`, defaulting to local dev but using the Docker service URL in compose.
- Normalize LangGraph API responses into the existing `DiscoveryResponse` contract.
- Remove FastAPI dependency on module-level `discovery_agent.graph` for discovery message handling.

## Capabilities

### New Capabilities

- `discovery-agent-server-proxy`: FastAPI discovery endpoints proxy conversation turns to the internal LangGraph agent-server while preserving the frontend-facing `DiscoveryResponse` API.

### Modified Capabilities

- None. Discovery specs are still active under `add-discovery-agent` and have not been archived as base specs yet.

## Impact

- Affected code:
  - `backend/app/routers/discovery.py`
  - `backend/app/core/config.py`
  - `docker-compose.yml`
  - discovery API tests
- Affected runtime systems:
  - FastAPI backend
  - internal `agent-server`
  - LangGraph API thread/run endpoints
- No frontend breaking change: frontend continues calling `/v1/discovery/*` only.
