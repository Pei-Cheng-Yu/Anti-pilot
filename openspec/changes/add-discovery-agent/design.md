## Context

The system already has a Learning Director (DeepAgent) that orchestrates roadmap generation and content creation, and an MCP server that exposes memory, goal, profile, and roadmap tools. However, there is no conversational entry point — learners must provide goal and profile data directly through API calls with no guided discovery.

The Discovery Agent fills this gap. It is a new DeepAgent that conducts multi-turn goal discovery conversation, reads and writes learner memory through MCP tools, and launches the Learning Director as a non-blocking async subagent when all required entities are confirmed.

Full architecture reference: `docs/superpowers/specs/2026-06-07-discovery-agent-design.md`

**Current state:**
- Learning Director: DeepAgent, called as Python library from FastAPI, no conversational interface
- Memory tools: available via MCP but not called by any conversational agent
- Frontend: no discovery conversation flow exists
- Docker: single FastAPI backend container

## Goals / Non-Goals

**Goals:**
- Add a Discovery Agent that handles multi-turn goal and profile collection via conversation
- Give Discovery Agent learner-state agency through MCP tools: save/retrieve `GoalSpec`, save/retrieve `LearningProfile`, retrieve memory context, and add only durable `preference_signal` or `background` memory notes
- Wire Discovery Agent → Learning Director via DeepAgents `AsyncSubAgent` so roadmap generation is non-blocking
- Add FastAPI `/v1/discovery/*` endpoints as the frontend-facing API (teammate does not interact with agent server directly)
- Add conversation persistence via LangGraph Postgres checkpointer
- Return structured `DiscoveryResponse` from every agent turn (message + optional ui_hints + session status)
- Containerize agent server separately; FastAPI backend unchanged except new routes

**Non-Goals:**
- Discovery Agent does not generate roadmaps or content (Learning Director's job)
- Discovery Agent does not write error patterns, mastery signals, or heuristics (code correction service's job)
- No voice/multimodal interface
- No changes to existing FastAPI routes, memory services, code correction, or content generation
- No LangSmith/LangGraph Cloud dependency — fully self-hosted

## Decisions

### Decision 1: DeepAgents for Discovery Agent (not ADK)

**Choice:** Build Discovery Agent as a DeepAgent (same framework as Learning Director and Code Validator), not a Google ADK agent.

**Rationale:** The Discovery Agent calls MCP tools heavily (save_goal, save_learning_profile, add_memory_note, retrieve_learning_memory). DeepAgents integrates with MCP via `langchain_mcp_adapters` natively — the same integration already proven in the Learning Director. ADK would require manually wrapping every MCP tool as an ADK `FunctionTool`, creating a maintenance burden. Framework consistency also simplifies the codebase.

**Alternative considered:** Google ADK with `LongRunningFunctionTool` for background execution. Rejected because MCP integration is not native to ADK and the async subagent pattern in DeepAgents covers the background execution need without ADK.

---

### Decision 2: Async subagent over A2A or direct tool call

**Choice:** Discovery Agent calls Learning Director via DeepAgents `AsyncSubAgent` (Agent Protocol over HTTP/ASGI).

**Rationale:** Roadmap generation is long-running (planner + content generation can take 30-120 seconds). A synchronous tool call would block the Discovery Agent's conversation for that duration. `AsyncSubAgent` gives non-blocking execution natively within the DeepAgents framework already installed (`deepagents==0.5.1`). The supervisor gets `start_async_task` / `check_async_task` tools automatically — no extra infrastructure.

**Alternative considered:** A2A (Google Agent-to-Agent protocol). Rejected — adds infrastructure and is not yet in the project stack. Can migrate later if needed.

**Alternative considered:** FastAPI `BackgroundTask`. Rejected — requires the Discovery Agent to be a FastAPI concern rather than an agent concern, and loses the native async task tracking (status, cancel, update mid-flight).

---

### Decision 3: FastAPI as frontend API surface (not direct agent server)

**Choice:** Frontend calls FastAPI `/v1/discovery/*` endpoints. FastAPI calls the Discovery Agent as a Python library with a Postgres checkpointer. The agent server runs internally for async subagent communication only.

**Rationale:** The frontend teammate already uses FastAPI for all other endpoints (roadmap, code submission, reviews, memory). Exposing a second API surface (agent server) would require the teammate to learn LangGraph SDK concepts (thread_id, run_id, StreamPart events, stream_mode). FastAPI as the single API surface keeps the teammate's integration simple and consistent. Auth, validation, and conversation_id → user_id mapping stay in the backend.

**Alternative considered:** Frontend calls agent server directly via LangGraph SDK. Rejected — adds learning curve for teammate and splits the API surface.

---

### Decision 4: Postgres checkpointer for thread persistence

**Choice:** Use `AsyncPostgresSaver` from `langgraph-checkpoint-postgres` to persist conversation state. FastAPI stores `conversation_id → user_id` in its own DB table; checkpointer stores message history keyed by `thread_id` (= `conversation_id`).

**Rationale:** Learners may drop off mid-discovery and return later. Without persistence, discovery starts over. The checkpointer handles message history, agent state, and async task metadata automatically — no custom session management needed in FastAPI.

**Alternative considered:** In-memory checkpointer. Rejected — does not survive restarts or scale horizontally.

---

### Decision 5: `response_format=DiscoveryResponse` on main agent

**Choice:** Set `response_format=DiscoveryResponse` on `create_deep_agent` so every turn returns structured JSON with `message`, `ui_hints`, `session_complete`, and `roadmap_status` fields.

**Rationale:** The teammate needs a predictable response shape to render both conversational text and optional UI option buttons. A flexible Pydantic schema with optional fields achieves both: normal conversation turns set `ui_hints=null`; turns with option suggestions set `ui_hints` with type and options list. No text parsing required on the frontend.

**Alternative considered:** Plain text streaming with `get_stream_writer()` custom events for structured data. Rejected — requires the teammate to handle two separate event streams and reconstruct state from token chunks. More frontend complexity for no meaningful gain.

---

### Decision 6: Explicit MCP tool allowlist for Discovery Agent

**Choice:** Filter the full MCP tool list to a fixed allowlist using the actual mounted MCP tool names: `{goal_get_goal, goal_save_goal, learning_profile_get_learning_profile, learning_profile_save_learning_profile, learning_memory_retrieve_learning_memory, learning_memory_get_skill_mastery_state, learning_memory_add_memory_note}`.

**Rationale:** New MCP tools added to the backend server would otherwise be automatically available to the Discovery Agent. A denylist approach is fragile. An explicit allowlist ensures the agent only has the tools it needs and new tools do not silently expand its agency.

### Decision 8: Goal/profile remain source of truth; memory stores durable teaching facts only

**Choice:** The Discovery Agent saves `GoalSpec` and `LearningProfile` through their own MCP tools and does not duplicate those entities into learner memory. It writes learner memory only for durable teaching facts that improve future personalization.

Allowed discovery-authored memory types:

- `preference_signal`: examples-first, hands-on preference, recap preference, pacing or explanation style
- `background`: durable learner context such as prior backend/project experience or concept history not already represented by the profile schema

Disallowed discovery-authored memory types:

- `error_pattern`
- `mastery_signal`
- `heuristic`

Those are owned by code correction and memory lifecycle services.

**Rationale:** Goal/profile data already has structured source-of-truth tables and schemas. Duplicating the same facts into memory would create stale/conflicting references. Memory should be used only when the fact is durable teaching context that benefits later feedback, hints, or content generation.

---

### Decision 7: Two-container deployment

**Choice:** Separate `agent-server` Docker container running `langgraph up` alongside the existing `backend` container.

**Rationale:** The async subagent pattern requires the Learning Director to be reachable via Agent Protocol HTTP. Both containers share `MCP_SERVER_URL` pointing to the FastAPI backend's MCP server. The split is clean: `backend` owns the REST API and MCP server; `agent-server` owns the conversation and orchestration graphs. Existing CI/CD and `docker-compose` patterns are preserved.

## Risks / Trade-offs

**[Risk] `response_format` constrains free-form text generation**
→ The model must emit valid JSON matching `DiscoveryResponse` on every turn. If the model hallucinates an invalid JSON structure, the turn fails. Mitigation: add a fallback parser that wraps raw text in `{"message": raw_text, "ui_hints": null, "session_complete": false}` if JSON parsing fails, same pattern used in the ADK content generator.

**[Risk] Module-level `graph` variable with async init**
→ `create_discovery_agent()` and `create_learning_director()` are async but `langgraph.json` requires a compiled graph at module import time. `asyncio.get_event_loop().run_until_complete()` works but may conflict with FastAPI's event loop if both are imported in the same process. Mitigation: the agent server and FastAPI backend are separate containers — no shared process. The graph variable is only needed in the agent server container.

**[Risk] Checkpointer table setup**
→ `AsyncPostgresSaver.setup()` must run before first use. If skipped, conversation state fails silently. Mitigation: call `setup()` in FastAPI's `lifespan` startup handler; add to implementation checklist.

**[Risk] Tool filtering drift**
→ If a developer adds a new MCP tool and forgets the Discovery Agent uses an allowlist, they may be surprised the tool is not available to the agent. Mitigation: document the allowlist in the agent module and add a test that asserts the filtered tool set matches the allowlist exactly.

**[Risk] Learning Director not registered in langgraph.json**
→ `AsyncSubAgent(graph_id="learning_director")` silently fails or errors at runtime if `learning_director` is not in `langgraph.json`. Mitigation: add an integration test that verifies the agent server can resolve the `learning_director` graph ID before launch.

## Migration Plan

1. Add `langgraph-checkpoint-postgres` to `requirements.txt`.
2. Add `DiscoveryConversationModel` to DB model and run alembic migration (no breaking changes to existing tables).
3. Add `graph` module-level variable to `learning_director/agent.py` (additive, no behavior change).
4. Update `langgraph.json` with new graph registrations.
5. Add `agent-server` service to `docker-compose.yml`.
6. Deploy backend first (migration runs), then agent server.
7. Rollback: remove `agent-server` service from compose; new `/v1/discovery/*` routes return 503 but all other routes unaffected.

## Open Questions

- Should `save_goal` and `save_learning_profile` overwrite existing data silently, or should the Discovery Agent confirm with the learner before overwriting an existing goal? (Both tools currently use "save or replace" semantics.)
- Should the `roadmap_status` polling be a separate FastAPI endpoint or should the frontend send a "check status" message to the Discovery Agent which then calls `check_async_task`? The conversational approach is more natural but adds a turn.
- Is `google_genai:gemini-3.1-pro-preview` the right model for the Discovery Agent, or should a lighter model (flash) be used for conversational turns to reduce latency?
