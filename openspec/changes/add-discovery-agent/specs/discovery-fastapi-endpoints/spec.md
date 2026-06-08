## ADDED Requirements

### Requirement: Frontend can create a discovery conversation
The system SHALL expose `POST /v1/discovery/conversations` that creates a new discovery conversation for a user, stores the `conversation_id → user_id` mapping in the DB, and returns the `conversation_id`. The `conversation_id` is the LangGraph `thread_id` used by the checkpointer.

#### Scenario: New conversation created
- **WHEN** frontend calls `POST /v1/discovery/conversations` with a valid `user_id`
- **THEN** the system SHALL return `{"conversation_id": "<uuid>"}` and persist the mapping in the `discovery_conversations` table

#### Scenario: Same user creates multiple conversations
- **WHEN** a user has an existing conversation and creates a new one
- **THEN** both conversations SHALL be persisted independently; the previous conversation is not deleted

---

### Requirement: Frontend can send a message and receive a DiscoveryResponse
The system SHALL expose `POST /v1/discovery/conversations/{conversation_id}/messages` that accepts `{"message": string}`, invokes the Discovery Agent with the given `thread_id` and `user_id`, and returns a `DiscoveryResponse`.

#### Scenario: Successful message turn
- **WHEN** frontend sends a message to an existing conversation
- **THEN** the system SHALL return a `DiscoveryResponse` with `message`, optional `ui_hints`, `session_complete`, and optional `roadmap_job_id` / `roadmap_status`

#### Scenario: Conversation not found
- **WHEN** frontend sends a message to a non-existent `conversation_id`
- **THEN** the system SHALL return HTTP 404

#### Scenario: Conversation state persists across requests
- **WHEN** a learner sends a message, receives a response, and sends a follow-up in a later HTTP request
- **THEN** the agent SHALL have full message history from prior turns available via the checkpointer

---

### Requirement: Frontend can resume from a structured interrupt
The system SHALL expose `POST /v1/discovery/conversations/{conversation_id}/resume` that accepts `{"selection": string}` and resumes the agent from a LangGraph interrupt using `Command(resume=selection)`.

#### Scenario: Successful resume after interrupt
- **WHEN** a prior turn returned an agent interrupt and the frontend calls resume with the learner's selection
- **THEN** the agent SHALL continue execution from the interrupt point with the selection and return the next `DiscoveryResponse`

#### Scenario: Resume without prior interrupt
- **WHEN** resume is called but the agent has no pending interrupt
- **THEN** the system SHALL return HTTP 400 with a clear error message

---

### Requirement: Conversation thread persistence survives restarts
The system SHALL use `AsyncPostgresSaver` from `langgraph-checkpoint-postgres` as the checkpointer. Conversation message history and agent state SHALL survive FastAPI process restarts.

#### Scenario: Learner resumes session after server restart
- **WHEN** a learner had a partial discovery conversation, the server restarted, and the learner sends a new message with the same `conversation_id`
- **THEN** the agent SHALL have full prior message history and continue from where it left off

#### Scenario: Checkpointer setup on startup
- **WHEN** the FastAPI application starts
- **THEN** `AsyncPostgresSaver.setup()` SHALL be called in the lifespan handler to ensure checkpoint tables exist before any request is handled
