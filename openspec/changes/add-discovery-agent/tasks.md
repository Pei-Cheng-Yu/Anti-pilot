## 1. Dependencies and DB Setup

- [ ] 1.1 Add `langgraph-checkpoint-postgres` to `requirements.txt`
- [ ] 1.2 Add `DiscoveryConversationModel` to `backend/app/db/model.py` with fields: `conversation_id` (PK, str), `user_id` (str), `created_at` (datetime)
- [ ] 1.3 Generate alembic migration for `discovery_conversations` table
- [ ] 1.4 Verify migration runs cleanly against local DB

## 2. Discovery Agent Schemas

- [ ] 2.1 Create `backend/app/langgraph/discovery_agent/` directory with `__init__.py`
- [ ] 2.2 Create `backend/app/langgraph/discovery_agent/schemas.py` with `UIHints`, `DiscoveryResponse`, `DiscoveryContext`, and `ResumeRequest` Pydantic models matching the design doc
- [ ] 2.3 Add JSON parse fallback logic: if model output cannot be parsed as `DiscoveryResponse`, wrap raw text in `{"message": raw_text, "ui_hints": null, "session_complete": false}`

## 3. Discovery Agent System Prompt

- [ ] 3.1 Create `backend/app/langgraph/discovery_agent/prompts.py` with `DISCOVERY_SYSTEM_PROMPT`
- [ ] 3.2 Prompt MUST encode: (a) resume check first via `goal_get_goal`/`learning_profile_get_learning_profile`, (b) `learning_memory_retrieve_learning_memory` before asking questions, (c) one question at a time, (d) save `GoalSpec`/`LearningProfile` entities as confirmed not at end, (e) write only `preference_signal`/`background` memory notes for strong durable learner signals, (f) never duplicate whole goal/profile entities into memory, (g) required entity checklist before calling `start_async_task`
- [ ] 3.3 Prompt MUST specify `ui_hints` format and when to use each type (`single_choice`, `multi_choice`, `text_input`, `confirm`)

## 4. Discovery Agent Construction

- [ ] 4.1 Create `backend/app/langgraph/discovery_agent/agent.py` with `create_discovery_agent()` async function
- [ ] 4.2 Wire `MultiServerMCPClient` with same `inject_user_id` interceptor pattern as Learning Director
- [ ] 4.3 Filter MCP tools to explicit allowlist using mounted names: `{goal_get_goal, goal_save_goal, learning_profile_get_learning_profile, learning_profile_save_learning_profile, learning_memory_retrieve_learning_memory, learning_memory_get_skill_mastery_state, learning_memory_add_memory_note}`
- [ ] 4.4 Wire `AsyncPostgresSaver` checkpointer from `DATABASE_URL` env var
- [ ] 4.5 Register `AsyncSubAgent(name="learning_director", graph_id="learning_director")` in `subagents` list — no `url` (co-deployed ASGI)
- [ ] 4.6 Set `response_format=DiscoveryResponse` and `context_schema=DiscoveryContext`
- [ ] 4.7 Expose module-level `graph` variable: `graph = asyncio.get_event_loop().run_until_complete(create_discovery_agent())`
- [ ] 4.8 Write a test asserting the tool set available to the agent exactly matches the allowlist

## 5. Learning Director Graph Registration

- [ ] 5.1 Add module-level `graph` variable to `backend/app/langgraph/learning_director/agent.py`: `graph = asyncio.get_event_loop().run_until_complete(create_learning_director())`
- [ ] 5.2 Verify that adding the `graph` variable does not break existing FastAPI usage of the Learning Director (it should be additive — same object, new name)

## 6. langgraph.json Update

- [ ] 6.1 Add `"learning_director": "app.langgraph.learning_director.agent:graph"` to `langgraph.json`
- [ ] 6.2 Add `"discovery_agent": "app.langgraph.discovery_agent.agent:graph"` to `langgraph.json`
- [ ] 6.3 Verify `langgraph dev` starts without error and both graphs are listed

## 7. FastAPI Endpoints

- [ ] 7.1 Create `backend/app/routers/discovery.py` with the following routes:
  - `POST /v1/discovery/conversations` → creates conversation, returns `conversation_id`
  - `POST /v1/discovery/conversations/{conversation_id}/messages` → invokes agent, returns `DiscoveryResponse`
  - `POST /v1/discovery/conversations/{conversation_id}/resume` → resumes from interrupt with `Command(resume=selection)`, returns `DiscoveryResponse`
- [ ] 7.2 Register `discovery_router` in `backend/app/main.py`
- [ ] 7.3 Add `async def save_discovery_conversation(user_id, conversation_id, session)` service function
- [ ] 7.4 Add `AsyncPostgresSaver.setup()` call to FastAPI `lifespan` startup handler so checkpoint tables are created before first request
- [ ] 7.5 Add HTTP 404 handling when `conversation_id` is not found in `discovery_conversations`
- [ ] 7.6 Add HTTP 400 handling for `resume` when no interrupt is pending

## 8. Agent Server Container

- [ ] 8.1 Add `agent-server` service to `docker-compose.yml` with `command: langgraph up`, `MCP_SERVER_URL: http://backend:8001/mcp`, and `DATABASE_URL` matching the backend
- [ ] 8.2 Ensure `agent-server` exposes no ports to the frontend (internal only)
- [ ] 8.3 Add `depends_on: backend` to `agent-server` so MCP server is reachable on startup
- [ ] 8.4 Verify both containers start cleanly and `agent-server` can reach the MCP server at `http://backend:8001/mcp`

## 9. Verification

- [ ] 9.1 Write an integration test: start a discovery conversation, send two messages, verify message history is persisted across requests (checkpointer works)
- [ ] 9.2 Write a test: send a message that triggers `save_goal` — verify goal is saved in DB via MCP
- [ ] 9.3 Write a test: agent returns valid `DiscoveryResponse` JSON on every turn
- [ ] 9.4 Write a test: agent response with `ui_hints` has valid `type` and non-empty `options`
- [ ] 9.5 Write a test: simulate full discovery flow — goal confirmed, profile confirmed, `start_async_task` called, `session_complete: true` returned
- [ ] 9.6 Write a test: `add_memory_note` is called when learner volunteers a strong preference signal
- [ ] 9.6a Write a test: discovery-authored memory notes are limited to `preference_signal` and `background`
- [ ] 9.6b Write a test or prompt-contract assertion: Discovery Agent saves goal/profile through their source-of-truth MCP tools and does not duplicate whole goal/profile entities into memory
- [ ] 9.7 Verify `langgraph.json` resolves both graph IDs without error in the agent server container
- [ ] 9.8 Manually test the full end-to-end flow: POST /v1/discovery/conversations → POST /messages (several turns) → confirm `session_complete: true` and `roadmap_job_id` is set
