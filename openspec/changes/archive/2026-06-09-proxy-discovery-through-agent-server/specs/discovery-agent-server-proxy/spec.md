## ADDED Requirements

### Requirement: FastAPI proxies discovery message turns to agent-server
The system SHALL keep FastAPI as the only frontend-facing discovery API while proxying Discovery Agent execution to the internal LangGraph agent-server.

#### Scenario: Message turn proxies to agent-server
- **WHEN** the frontend posts a message to `POST /v1/discovery/conversations/{conversation_id}/messages`
- **THEN** FastAPI SHALL validate the `conversation_id` ownership and send the turn to the internal agent-server using the same `conversation_id` as the LangGraph thread id.

#### Scenario: Agent-server is unreachable
- **WHEN** FastAPI cannot reach the configured agent-server URL
- **THEN** FastAPI SHALL return HTTP 503 with a clear discovery-agent unavailable error instead of HTTP 500.

#### Scenario: Frontend API remains stable
- **WHEN** the frontend sends a discovery message through FastAPI
- **THEN** the response SHALL still conform to `DiscoveryResponse` and SHALL NOT expose LangGraph run, thread, or assistant internals.

---

### Requirement: FastAPI proxies discovery resume turns to agent-server
The system SHALL route structured resume selections through the internal agent-server so interrupted Discovery Agent state is resumed by LangGraph API persistence.

#### Scenario: Resume proxies to same thread
- **WHEN** the frontend posts to `POST /v1/discovery/conversations/{conversation_id}/resume`
- **THEN** FastAPI SHALL validate the `conversation_id` ownership and send a LangGraph resume command to the internal agent-server using the same thread id.

#### Scenario: Resume without pending interrupt
- **WHEN** agent-server reports that no interrupt is pending for the conversation thread
- **THEN** FastAPI SHALL return HTTP 400 with a clear message.

---

### Requirement: Agent-server URL is configurable
The backend SHALL read an `AGENT_SERVER_URL` setting for internal Discovery Agent proxy calls.

#### Scenario: Docker Compose runtime
- **WHEN** the backend runs in Docker Compose
- **THEN** `AGENT_SERVER_URL` SHALL point to the internal agent-server service URL.

#### Scenario: Local development runtime
- **WHEN** the backend runs locally outside Docker
- **THEN** `AGENT_SERVER_URL` SHALL be configurable through environment variables and may point to localhost.

---

### Requirement: Agent-server responses are normalized
The backend SHALL normalize LangGraph API responses into the existing `DiscoveryResponse` schema.

#### Scenario: Structured response returned
- **WHEN** agent-server returns a `structured_response`
- **THEN** FastAPI SHALL validate it as `DiscoveryResponse` and return it to the frontend.

#### Scenario: Final message content returned
- **WHEN** agent-server returns final assistant message content but no `structured_response`
- **THEN** FastAPI SHALL parse that content as `DiscoveryResponse`, using the existing fallback wrapper for invalid JSON.
