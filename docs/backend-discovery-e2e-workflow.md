# Backend Discovery E2E Workflow

This smoke verifies the full learner onboarding path:

```text
FastAPI /v1/discovery/*
-> internal agent-server
-> discovery_agent graph
-> MCP tools
-> goal/profile/memory services
-> Learning Director handoff
-> roadmap and content persistence
```

## Prerequisites

- Docker services running for `backend`, `mcp`, `agent-server`, and `db`.
- Google/Gemini credentials in `.env`.
- Optional LangSmith tracing variables in `.env`.

Start the services from the worktree:

```bash
docker compose up --build backend mcp agent-server
```

## Run The Live Smoke

From WSL:

```bash
cd /mnt/c/Users/seans/anti-pilot/Anti-pilot/.worktrees/discovery-agent/backend

RUN_LIVE_DISCOVERY_E2E_TESTS=1 \
DISCOVERY_E2E_BASE_URL=http://localhost:8000 \
PYTHONPATH=. \
/mnt/c/Users/seans/anti-pilot/Anti-pilot/venv/bin/python \
-m pytest -m live_llm tests/test_live_discovery_e2e_workflow.py -q -s
```

The test creates a unique test user, creates a discovery conversation through
FastAPI, sends a short sequence of learner messages, waits for persisted
roadmap/content state, and cleans up the test user unless
`DISCOVERY_E2E_KEEP_DATA=1` is set.

## Expected API Response Fields

At each discovery message turn, FastAPI returns `DiscoveryResponse`:

- `message`: learner-facing text.
- `ui_hints`: optional structured choice/input hints.
- `session_complete`: `false` until Learning Director handoff starts.
- `roadmap_job_id`: non-empty after handoff.
- `roadmap_status`: usually `running`, `pending`, `complete`, or `failed`.

The final handoff response should include:

```json
{
  "session_complete": true,
  "roadmap_job_id": "non-empty task id"
}
```

## Expected DB Rows

For the generated live test user, inspect:

- `goals`: one row with non-empty `title`, `description`, `target_outcome`,
  `deadline`, `criteria`, and `constraints`.
- `learning_profiles`: one row with non-empty level, knowledge or weak-area
  signals, pace, confidence, recap/examples preferences, and overload risk.
- `learner_memory_notes`: any discovery-authored rows use only
  `preference_signal` or `background`.
- `roadmaps`: one persisted roadmap.
- `milestones`: at least one milestone for the roadmap.
- `skillpaths`: at least one skillpath under the milestone.
- `learning_contents`: at least one generated content row for a skillpath.

## LangSmith Trace Checks

When tracing is enabled, check that traces show:

- Discovery Agent message handling.
- MCP calls for `goal_save_goal` and `learning_profile_save_learning_profile`.
- Optional `learning_memory_add_memory_note` calls using only allowed memory
  types.
- Async task handoff to `learning_director`.
- Learning Director roadmap/content generation activity.

## Common Failures

- `503` from `/v1/discovery/.../messages`: backend cannot reach
  `AGENT_SERVER_URL`; inspect backend env and `agent-server` logs.
- No MCP tool calls: inspect `MCP_SERVER_URL` inside the `agent-server`
  container.
- No roadmap/content after timeout: inspect `agent-server` logs, Learning
  Director trace, and backend DB logs.
- JSON parse/fallback response only: inspect Discovery Agent prompt and
  `response_format` behavior.
