## Why

The system currently has no conversational entry point for learners — goal and learning profile data must be provided up-front with no guided discovery. This change adds a Discovery Agent that collects the learner's goal and profile through multi-turn conversation, then hands off to the existing Learning Director to generate the roadmap, completing the end-to-end onboarding flow.

## What Changes

- Add a `DiscoveryAgent` DeepAgent that handles multi-turn goal and profile discovery conversation with the learner.
- Give the Discovery Agent bounded learner-state agency: it saves confirmed goal/profile entities through MCP tools, retrieves existing learner memory at session start, and writes only durable preference/background memory notes as the conversation progresses.
- Wire the Discovery Agent to call the Learning Director as an async subagent (via DeepAgents `AsyncSubAgent`) once all required entities are confirmed — so roadmap generation runs in the background while the agent continues talking to the learner.
- Add FastAPI endpoints (`/v1/discovery/*`) so the frontend can start conversations, send messages, and resume from structured option selections.
- Add conversation thread persistence via LangGraph Postgres checkpointer — so learners can resume mid-discovery across sessions.
- Add `DiscoveryResponse` structured output schema so every agent turn returns typed JSON (message + optional UI hints + session status) instead of plain text.
- Update `langgraph.json` to register `discovery_agent` and `learning_director` graphs for the agent server container.
- Add a second Docker container (`agent-server`) for the agent server; the existing FastAPI backend container is unchanged except for the new discovery routes.

## Capabilities

### New Capabilities

- `discovery-agent`: Multi-turn conversational agent that collects goal and learning profile, retrieves learner memory, writes durable preference/background memory notes when useful, and launches the Learning Director as an async background task when ready.
- `discovery-fastapi-endpoints`: REST API surface for the frontend to interact with the Discovery Agent — conversation lifecycle, message sending, and interrupt resume.
- `discovery-learning-director-wiring`: Async subagent wiring between Discovery Agent and Learning Director, including `langgraph.json` registration and agent server container setup.

### Modified Capabilities

None.

## Impact

- Adds `backend/app/langgraph/discovery_agent/` module (agent, schemas, prompts).
- Adds `backend/app/routers/discovery.py` and registers it in `main.py`.
- Adds `DiscoveryConversationModel` to `backend/app/db/model.py` and a new alembic migration.
- Updates `langgraph.json` to register `discovery_agent` and `learning_director` graphs.
- Updates `backend/app/langgraph/learning_director/agent.py` to expose a module-level `graph` variable.
- Adds `docker-compose.yml` `agent-server` service.
- New dependency: `langgraph-checkpoint-postgres`.
- No changes to existing FastAPI routes, memory services, code correction, content generation, or planner.
- Full design reference: `docs/superpowers/specs/2026-06-07-discovery-agent-design.md`
