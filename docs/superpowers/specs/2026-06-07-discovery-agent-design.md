# Discovery Agent Design

## Context

This document covers the full design for the Discovery Agent — a new conversational agent that collects a learner's goal and learning profile before handing off to the existing Learning Director. It covers architecture, deployment, memory agency, FastAPI integration, structured output, thread management, and implementation steps.

This document is intended to be self-contained enough for implementation in a separate session (Codex or otherwise).

---

## 1. Architecture Overview

### Two-container deployment

```
┌─────────────────────────────────┐     ┌──────────────────────────────────┐
│  Container 1: FastAPI Backend   │     │  Container 2: Agent Server       │
│                                 │     │  (langgraph build → Docker)      │
│  - REST API for frontend        │     │                                  │
│  - MCP server (FastMCP)         │     │  - discovery_agent graph         │
│  - All services (memory,        │     │  - learning_director graph        │
│    code correction, roadmap,    │     │  - planner graph (existing)       │
│    reviews, etc.)               │     │  - quick_reviewer graph (exist.)  │
│  - Code Validator (DeepAgent)   │     │                                  │
│  - Content Generator (ADK)      │     │  Internal only — not exposed      │
│  - Hint Service                 │     │  to frontend                     │
│  - Memory Integrity Service     │     │                                  │
└────────────┬────────────────────┘     └──────────────────────────────────┘
             │                                        │
             │  MCP over HTTP                         │  MCP over HTTP
             │  (same MCP_SERVER_URL env var)         │  (same MCP_SERVER_URL)
             └──────────────────┬─────────────────────┘
                                ▼
                         MCP Server (FastAPI, port 8001)
                         → Postgres DB
```

**Key principle:** The agent server exists only for:
1. Discovery Agent ↔ Learning Director async communication
2. Conversation thread persistence (checkpointer)

Everything else (code submission, reviews, memory services, content generation) stays in the FastAPI backend as Python library calls — no change to existing workflows.

### What does NOT change

- Code Validator: called as Python library inside FastAPI services
- ADK Content Generator: called as Python library inside LangGraph content graph
- Planner graph: called as Python library inside Learning Director
- All memory services: deterministic service layer, unchanged
- All FastAPI routes except the new `/v1/discovery/*` endpoints

---

## 2. Discovery Agent

### Purpose

Multi-turn conversational agent that:
1. Reads existing goal and profile if the learner has been before
2. Asks clarifying and brainstorming questions to extract goal and learning profile
3. Suggests structured options (learning paths, deadlines, background levels)
4. Persists confirmed entities to DB via MCP tools
5. Optionally writes preference/context memory notes during conversation
6. When all required entities are confirmed, launches Learning Director as async subagent
7. Reports roadmap generation status back to learner

### Framework

DeepAgents (`create_deep_agent`) — same framework as Learning Director and Code Validator. Consistent MCP integration via `langchain_mcp_adapters`.

### Structured Response Format

Every turn returns a `DiscoveryResponse` — never raw text. The `message` field holds the conversational text; `ui_hints` is optional and only present when the agent wants to surface clickable options.

```python
from pydantic import BaseModel

class UIHints(BaseModel):
    type: str                        # "single_choice" | "multi_choice" | "text_input" | "confirm"
    question: str
    options: list[str] | None = None

class DiscoveryResponse(BaseModel):
    message: str                     # always — conversational text shown to learner
    ui_hints: UIHints | None = None  # optional — render as buttons/chips in UI
    session_complete: bool = False   # True when handoff to Learning Director triggered
    roadmap_job_id: str | None = None  # set after start_async_task succeeds
    roadmap_status: str | None = None  # "pending" | "running" | "complete" | "failed"
```

Normal conversation turn:
```json
{
  "message": "What is your main learning goal?",
  "ui_hints": {
    "type": "single_choice",
    "question": "Pick the closest match or describe your own",
    "options": ["Backend web development", "Data science", "System design", "Mobile dev"]
  },
  "session_complete": false,
  "roadmap_job_id": null,
  "roadmap_status": null
}
```

After entities confirmed and Learning Director launched:
```json
{
  "message": "Your personalized roadmap is being generated. I'll let you know when it's ready.",
  "ui_hints": null,
  "session_complete": true,
  "roadmap_job_id": "task-abc123",
  "roadmap_status": "pending"
}
```

### Memory Agency — Tools

The Discovery Agent has the most memory agency of any agent in the system. It is the only agent that:
- Reads existing memory at session start to personalize the discovery conversation
- Writes goal and profile as entities are confirmed
- Writes lightweight preference/context notes from conversation signals

**MCP tools available to Discovery Agent:**

| Tool | Purpose | Read/Write |
|---|---|---|
| `get_goal` | Check if learner already has a goal (resume session) | Read |
| `save_goal` | Persist confirmed goal | Write |
| `get_learning_profile` | Check existing profile | Read |
| `save_learning_profile` | Persist confirmed profile | Write |
| `retrieve_learning_memory` | Understand learner's existing mastery, error patterns, preferences | Read |
| `get_skill_mastery_state` | Quick mastery snapshot for a specific skill | Read |
| `add_memory_note` | Store preference signals or context from conversation | Write |

**Tools explicitly NOT given to Discovery Agent:**

| Tool | Why excluded |
|---|---|
| `run_planner` | Learning Director's job |
| `run_content_generator` | Learning Director's job |
| `record_coding_problem_attempt` | Code correction service's job |
| `update_memory_note` | Too broad — add is sufficient for discovery |
| `delete_memory_note` | Destructive, not needed in discovery |
| `resolve_memory_note` | Lifecycle management belongs to correction service |

**Note on write agency:** The Discovery Agent writes memory without confirmation gates. Correctness is enforced by the `memory-integrity-lifecycle` service (see `add-memory-integrity-lifecycle` openspec change) which runs before every `add_memory_note` write and prevents duplicates and conflicts.

### Async Subagent: Learning Director

When all required entities (goal, profile) are confirmed, the Discovery Agent launches the Learning Director as a non-blocking async subagent.

**Configuration:**

```python
from deepagents import AsyncSubAgent, create_deep_agent

discovery_agent = create_deep_agent(
    model="google_genai:gemini-3.1-pro-preview",
    system_prompt=DISCOVERY_SYSTEM_PROMPT,
    response_format=DiscoveryResponse,
    context_schema=DiscoveryContext,
    checkpointer=checkpointer,               # Postgres checkpointer for threads
    subagents=[
        AsyncSubAgent(
            name="learning_director",
            description="Generates a personalized learning roadmap and content once the learner's goal and profile are confirmed. Call this when all required entities have been collected and confirmed.",
            graph_id="learning_director",    # must match langgraph.json key
            # url omitted → co-deployed in same container (ASGI transport)
        )
    ],
    tools=[*mcp_tools],                      # MCP tools listed above
)
```

The middleware automatically gives the Discovery Agent five tools:
- `start_async_task("learning_director", instructions)` → returns `task_id` immediately
- `check_async_task(task_id)` → polls status
- `update_async_task(task_id, instructions)` → steer mid-flight if needed
- `cancel_async_task(task_id)` → cancel if user changes their mind
- `list_async_tasks()` → see all running tasks

The agent uses `start_async_task` when entities are confirmed, then sets `session_complete: true` and `roadmap_job_id` in its response. It can later call `check_async_task` in subsequent turns if the user asks about progress.

**Context propagation:** `user_id` flows from `DiscoveryContext` through `ToolRuntime` to all MCP tool calls and to the Learning Director subagent automatically — no explicit passing needed.

### System Prompt Guidance (key points)

```
You are a learning discovery agent. Your job is to understand the learner's
goal and learning background through friendly, focused conversation.

Session phases:
1. RESUME CHECK: Call get_goal and get_learning_profile first. If data exists,
   confirm it is still current rather than starting from scratch.

2. RETRIEVAL: Call retrieve_learning_memory to understand existing mastery and
   patterns. Use this to skip topics the learner already knows well.

3. DISCOVERY: Ask one question at a time. Use ui_hints to offer structured
   options when appropriate — do not overwhelm with open questions.

4. PERSISTENCE: Call save_goal and save_learning_profile as soon as each entity
   is confirmed. Do not wait until the end.

5. MEMORY NOTES: If the learner shares strong preferences or context
   (e.g. "I hate math-heavy content", "I only have evenings"), call
   add_memory_note with type PREFERENCE_SIGNAL or BACKGROUND.

6. HANDOFF: When goal and profile are fully confirmed, call start_async_task
   to launch learning_director. Set session_complete to true in your response.

Required entities before handoff:
- goal.title, goal.target_outcome, goal.deadline_weeks
- profile.current_level, profile.available_hours_per_week
```

---

## 3. Learning Director Memory Agency

The Learning Director **does not write memory**. Its job is orchestration: run planner, optionally review, run content generator.

Memory flows into it via injection — the planner and content generation graphs already retrieve and inject `LearningMemoryContext`. The Learning Director does not call memory tools directly.

**Exception — optional review step:** During the optional roadmap review phase, the Learning Director may call `retrieve_learning_memory` to check if the proposed roadmap aligns with existing mastery state. This is read-only.

**MCP tools for Learning Director:**

| Tool | Purpose |
|---|---|
| `get_goal` | Read confirmed goal |
| `get_learning_profile` | Read confirmed profile |
| `retrieve_learning_memory` | Read-only, for optional review step |
| `save_roadmap` / roadmap tools | Persist generated roadmap |

Does NOT have: `add_memory_note`, `update_memory_note`, `save_goal`, `save_learning_profile`.

---

## 4. Memory Agency Across All Agents

| Agent | Read memory | Write memory | Pattern |
|---|---|---|---|
| Discovery Agent | ✓ retrieve, get_mastery | ✓ save_goal, save_profile, add_note | Full agency via MCP tools |
| Learning Director | ✓ retrieve (optional review) | ✗ | Read-only via MCP |
| Planner graph | ✓ injected by content gen graph | ✗ | Injected context |
| Content Generator (ADK) | ✓ injected via prompt | ✗ | Injected context |
| Code Validator | ✗ | ✗ | None — pure reasoning |
| Code Correction service | ✓ retrieved in service | ✓ record_and_consolidate | Deterministic service lifecycle |
| Memory Rerank Advisor | ✓ candidates passed in | ✗ | Advisory — returns guidance only |
| Memory Integrity Advisor | ✓ candidates passed in | ✗ | Advisory — runs before writes |
| Hint Service | ✓ retrieved then injected | ✗ | Injected context |

**Principle:** Only the Discovery Agent and the deterministic code correction service write memory. No other agent or graph writes. The integrity lifecycle (add-memory-integrity-lifecycle change) guards all writes from the Discovery Agent before they hit the DB.

---

## 5. FastAPI Integration

### Thread Management

The agent server's thread/run management is powered by LangGraph's checkpointer. When calling agents as Python library (via FastAPI), you provide the same checkpointer and pass `thread_id` in config. FastAPI owns the `conversation_id → user_id` mapping; the checkpointer owns message history.

**Setup:**

```python
# backend/app/langgraph/discovery_agent/session.py
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import settings

async def get_checkpointer() -> AsyncPostgresSaver:
    checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL)
    await checkpointer.setup()   # creates checkpoint tables if not exist
    return checkpointer
```

**Agent construction (once at startup):**

```python
# backend/app/langgraph/discovery_agent/agent.py
from langchain_mcp_adapters.client import MultiServerMCPClient
from deepagents import AsyncSubAgent, create_deep_agent

async def create_discovery_agent():
    client = MultiServerMCPClient(
        {"anti-pilot": {"transport": "http", "url": MCP_SERVER_URL}},
        tool_interceptors=[inject_user_id],   # same interceptor as Learning Director
    )
    mcp_tools = await client.get_tools()
    # Filter to only the tools Discovery Agent should have
    allowed = {
        "get_goal", "save_goal",
        "get_learning_profile", "save_learning_profile",
        "retrieve_learning_memory", "get_skill_mastery_state",
        "add_memory_note",
    }
    filtered_tools = [t for t in mcp_tools if t.name in allowed]

    checkpointer = await get_checkpointer()

    return create_deep_agent(
        model="google_genai:gemini-3.1-pro-preview",
        system_prompt=DISCOVERY_SYSTEM_PROMPT,
        response_format=DiscoveryResponse,
        context_schema=DiscoveryContext,
        checkpointer=checkpointer,
        subagents=[
            AsyncSubAgent(
                name="learning_director",
                description="...",
                graph_id="learning_director",
            )
        ],
        tools=filtered_tools,
    )
```

### FastAPI Endpoints

```python
# backend/app/routers/discovery.py
from fastapi import APIRouter, Depends
from uuid import uuid4

router = APIRouter(prefix="/v1/discovery", tags=["discovery"])

class StartConversationResponse(BaseModel):
    conversation_id: str

class MessageRequest(BaseModel):
    message: str

@router.post("/conversations", response_model=StartConversationResponse)
async def create_conversation(user_id: str, session: AsyncSession = Depends(get_session)):
    conversation_id = str(uuid4())
    await save_discovery_conversation(user_id, conversation_id, session)
    return {"conversation_id": conversation_id}

@router.post("/conversations/{conversation_id}/messages", response_model=DiscoveryResponse)
async def send_message(
    conversation_id: str,
    body: MessageRequest,
    user_id: str,
):
    result = await _agent.ainvoke(
        {"messages": [HumanMessage(content=body.message)]},
        config={
            "configurable": {
                "thread_id": conversation_id,
                "user_id": user_id,           # flows into DiscoveryContext
            }
        },
    )
    # Extract last AI message
    last_message = result["messages"][-1]
    return DiscoveryResponse.model_validate_json(last_message.content)

@router.post("/conversations/{conversation_id}/resume", response_model=DiscoveryResponse)
async def resume_from_interrupt(
    conversation_id: str,
    body: ResumeRequest,   # { selection: str }
    user_id: str,
):
    from langgraph.types import Command
    result = await _agent.ainvoke(
        Command(resume=body.selection),
        config={"configurable": {"thread_id": conversation_id, "user_id": user_id}},
    )
    last_message = result["messages"][-1]
    return DiscoveryResponse.model_validate_json(last_message.content)

@router.get("/conversations/{conversation_id}/roadmap-status")
async def check_roadmap_status(conversation_id: str, job_id: str, user_id: str):
    # The agent can check this via check_async_task in its next turn,
    # OR FastAPI can proxy a status check. Simplest: let the frontend
    # send another message ("is my roadmap ready?") and the agent calls
    # check_async_task itself.
    pass
```

### What the Frontend Teammate Sees

The teammate's complete API surface for the discovery flow:

```
POST /v1/discovery/conversations
  body:  { user_id }
  → { conversation_id }

POST /v1/discovery/conversations/{id}/messages
  body:  { message: string }
  → {
      message: string,
      ui_hints?: { type, question, options },
      session_complete: bool,
      roadmap_job_id?: string,
      roadmap_status?: string
    }

POST /v1/discovery/conversations/{id}/resume
  body:  { selection: string }
  → same DiscoveryResponse shape

GET /v1/discovery/conversations/{id}/roadmap-status?job_id=...
  → { status: "pending" | "running" | "complete" | "failed" }
```

No LangGraph SDK, no thread_id/run_id concepts, no SSE unless you choose to add streaming later.

---

## 6. langgraph.json Update

The agent server container needs both graphs registered:

```json
{
  "dependencies": ["."],
  "graphs": {
    "planner": "app.langgraph.planner.graphs.generate_roadmap.graph:build_planner_graph",
    "quick_reviewer": "app.langgraph.planner.graphs.generate_roadmap.graph:build_planner_graph",
    "learning_director": "app.langgraph.learning_director.agent:graph",
    "discovery_agent": "app.langgraph.discovery_agent.agent:graph"
  },
  "env": "../.env"
}
```

The Learning Director needs to expose a `graph` variable (compiled graph) at module level for LangGraph to register it. Currently `create_learning_director()` is async and returns a DeepAgent. Wrap it:

```python
# backend/app/langgraph/learning_director/agent.py (add at bottom)
import asyncio

async def _build():
    return await create_learning_director()

# LangGraph registration requires a compiled graph at module level
graph = asyncio.get_event_loop().run_until_complete(_build())
```

Similarly for discovery agent:
```python
# backend/app/langgraph/discovery_agent/agent.py (add at bottom)
graph = asyncio.get_event_loop().run_until_complete(create_discovery_agent())
```

---

## 7. Docker Compose

```yaml
services:
  backend:
    build: ./backend
    environment:
      MCP_SERVER_URL: http://backend:8001/mcp
      DATABASE_URL: postgresql+asyncpg://...
    ports:
      - "8000:8000"

  agent-server:
    build:
      context: ./backend
      dockerfile: Dockerfile.agents   # or use langgraph build output
    command: langgraph up
    environment:
      MCP_SERVER_URL: http://backend:8001/mcp   # same URL — key point
      DATABASE_URL: postgresql+asyncpg://...
      GOOGLE_API_KEY: ...
    ports:
      - "8124:8124"   # internal only, not exposed to frontend
    depends_on:
      - backend
```

Both containers share `MCP_SERVER_URL` pointing to the FastAPI backend. MCP is pure HTTP — no coupling issues.

---

## 8. Implementation Steps

### Step 1 — Install checkpoint dependency

```bash
pip install langgraph-checkpoint-postgres
# add to requirements.txt
```

### Step 2 — Define schemas

Create `backend/app/langgraph/discovery_agent/schemas.py`:
- `DiscoveryContext` (TypedDict with `user_id`)
- `UIHints` (Pydantic)
- `DiscoveryResponse` (Pydantic)
- `ResumeRequest` (Pydantic)

### Step 3 — Write system prompt

Create `backend/app/langgraph/discovery_agent/prompts.py`. Key behaviors to encode:
- Resume check first (get_goal, get_learning_profile)
- Memory retrieval before discovery questions
- One question at a time
- Save entities as confirmed (don't batch at end)
- PREFERENCE_SIGNAL notes for strong learner signals
- Required entity checklist before triggering handoff

### Step 4 — Create Discovery Agent

Create `backend/app/langgraph/discovery_agent/agent.py`:
- `create_discovery_agent()` async function
- Filter MCP tools to allowed set
- Wire checkpointer, response_format, AsyncSubAgent
- Expose `graph` at module level for langgraph.json

### Step 5 — Update langgraph.json

Add `learning_director` and `discovery_agent` to graphs. Add `graph` module-level variable to `learning_director/agent.py`.

### Step 6 — FastAPI endpoints

Create `backend/app/routers/discovery.py`. Add to `main.py`.

### Step 7 — DB table for conversations

Add `DiscoveryConversationModel` to `backend/app/db/model.py`:
- `conversation_id` (PK)
- `user_id` (FK)
- `created_at`

Add alembic migration.

### Step 8 — Agent server Dockerfile

Either use `langgraph build` to produce a Docker image, or add a `Dockerfile.agents` that runs `langgraph up` from the backend directory.

### Step 9 — Update docker-compose.yml

Add `agent-server` service. Set `MCP_SERVER_URL` in both containers.

---

## 9. Things to Be Aware Of

### Checkpointer setup

Call `await checkpointer.setup()` once at startup — it creates the LangGraph checkpoint tables in Postgres. Safe to call multiple times (idempotent). Do this in FastAPI's `lifespan` event handler.

### response_format and token streaming

When `response_format` is set, the model must emit valid JSON matching the schema. Token-level streaming still works for the `message` field content, but the full JSON envelope must be valid before parsing. If you add streaming SSE later, use `stream_mode="messages"` and reconstruct the full JSON from accumulated tokens before parsing.

### Tool filtering is critical

The Discovery Agent gets MCP tools by name from the full MCP server tool list. Always filter explicitly — new MCP tools added to the server will otherwise be available to the agent. The allowed set should be an explicit allowlist in the agent construction, not a denylist.

### AsyncSubAgent requires langgraph.json registration

The `graph_id` in `AsyncSubAgent(graph_id="learning_director")` must exactly match the key in `langgraph.json`. If the Learning Director graph is not registered, `start_async_task` will fail silently or throw at runtime.

### Module-level graph variable

`langgraph.json` expects a compiled graph object at the specified import path. `create_learning_director()` and `create_discovery_agent()` are async — use `asyncio.get_event_loop().run_until_complete()` to build at import time, or use a `@asynccontextmanager` lifespan approach. Watch for event loop conflicts if FastAPI also runs async startup.

### MCP_SERVER_URL in agent server container

The agent server container must be able to reach the FastAPI backend's MCP endpoint. In Docker Compose, use the service name: `http://backend:8001/mcp`. The agents already read this from the env var — no code change needed.

### Learning Director graph_id conflict

If `learning_director` is added to `langgraph.json` and the Learning Director is also called directly as a Python library from FastAPI (for non-async flows), both paths can coexist — they both use the same compiled graph object. No conflict.

### Context injection for Learning Director subagent

The `user_id` must flow from the Discovery Agent's context into the Learning Director. AsyncSubAgentMiddleware propagates `ToolRuntime` context automatically. Verify the `inject_user_id` interceptor in the Learning Director is compatible with async subagent invocation.

### Memory integrity before add_memory_note

Once the `add-memory-integrity-lifecycle` openspec change is implemented, all `add_memory_note` calls go through the integrity service first. The Discovery Agent does not need to check for duplicates itself — the service handles it. Do not add duplicate-checking logic in the agent system prompt.

### Avoid write agency in Learning Director

Strictly enforce that the Learning Director does not call `add_memory_note`, `save_goal`, or `save_learning_profile`. If those tools are accidentally available via MCP, filter them out in the Learning Director's MCP tool construction, same as the Discovery Agent filters its allowed set.
