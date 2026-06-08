## Why

The Discovery Agent is becoming the entry point for learner onboarding, but the current verification only covers small contract and API slices. We need a repeatable way to prove the full learner flow works: conversation, entity persistence, memory note creation, Learning Director handoff, roadmap generation, and content creation.

## What Changes

- Add an end-to-end discovery workflow smoke test or script that exercises the real product path from FastAPI discovery endpoints through the internal agent-server and MCP tools.
- Verify that Discovery Agent can fill and persist `GoalSpec` and `LearningProfile` through MCP.
- Verify that Discovery Agent can write only allowed durable memory notes (`preference_signal`, `background`) through MCP.
- Verify that Discovery Agent launches Learning Director after required entities are confirmed.
- Verify that Learning Director generates and persists a roadmap and learning content.
- Add Discovery Agent skill/runbook instructions describing its job, allowed tools, entity checklist, memory write rules, handoff behavior, and expected response shape.
- Add clear live-test observation guidance for LangSmith traces, DB rows, and API responses.

## Capabilities

### New Capabilities

- `discovery-e2e-workflow-verification`: Full workflow verification for Discovery Agent onboarding through roadmap/content generation.
- `discovery-agent-skill-guidance`: Agent-facing skill/runbook guidance that defines Discovery Agent behavior, allowed MCP tools, memory policy, and handoff flow.

### Modified Capabilities

- None. The active discovery capabilities are still in OpenSpec changes and have not been archived into base specs.

## Impact

- Affected code and docs:
  - `backend/tests/`
  - `backend/app/langgraph/discovery_agent/`
  - `backend/app/langgraph/discovery_agent/skills/` or equivalent skill docs
  - `docs/` or OpenSpec verification docs
- Affected runtime systems:
  - FastAPI backend
  - internal agent-server
  - MCP server
  - Postgres
  - LangSmith live traces
- Requires live credentials and running Docker services for the full live smoke path.
