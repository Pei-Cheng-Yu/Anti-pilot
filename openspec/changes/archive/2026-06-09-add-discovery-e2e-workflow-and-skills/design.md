## Context

Discovery Agent onboarding crosses multiple boundaries: FastAPI, internal agent-server, MCP tools, Postgres persistence, Discovery Agent instructions, async Learning Director handoff, roadmap planning, and content generation. Unit tests currently prove only pieces of that system. A real product check needs to prove that the learner can talk to the Discovery Agent and eventually receive a generated roadmap with learning content.

The Discovery Agent also needs stable behavioral guidance beyond a single prompt string. A skill/runbook should document its role, allowed tools, memory policy, entity checklist, and handoff behavior so future prompt changes stay aligned with product architecture.

## Goals / Non-Goals

**Goals:**

- Add a repeatable workflow test or smoke script for the full Discovery Agent path.
- Verify MCP tool availability and allowed tool names for Discovery Agent.
- Verify `GoalSpec` and `LearningProfile` are persisted from discovery.
- Verify discovery-authored memory notes are limited to `preference_signal` and `background`.
- Verify Learning Director handoff occurs after required entities are confirmed.
- Verify roadmap and learning content persistence after handoff.
- Provide clear LangSmith, API, and DB observation guidance.
- Add Discovery Agent skill/runbook guidance that can be loaded by the agent or used as implementation documentation.

**Non-Goals:**

- Do not make the live smoke test run by default in normal CI.
- Do not require deterministic exact wording from the LLM.
- Do not expose agent-server directly to the frontend.
- Do not let Discovery Agent write memory lifecycle types owned by code correction.
- Do not change planner/content generator semantics beyond verifying they are called and persist output.

## Decisions

### Decision 1: Use layered verification

The change will include two verification layers:

1. Deterministic tests with mocked agent-server/MCP boundaries to check payload shape, tool allowlist, response parsing, and persistence expectations.
2. Gated live smoke test or script that requires Docker services, LLM credentials, and LangSmith tracing to validate the true runtime path.

This avoids making normal test runs slow/flaky while still giving the team a real proof path.

### Decision 2: Keep live assertions behavioral, not wording-based

The live smoke test should assert durable outcomes:

- saved goal exists
- saved learning profile exists
- allowed memory note type appears when learner gives a durable preference/background signal
- roadmap exists
- at least one milestone and skillpath exist
- generated learning content exists
- LangSmith trace shows expected tool calls

It should not require exact agent phrasing.

### Decision 3: Add a Discovery Agent skill/runbook

The Discovery Agent should have a dedicated instruction artifact under the discovery agent package, such as:

```text
backend/app/langgraph/discovery_agent/skills/discovery-agent/SKILL.md
```

The skill should define:

- agent mission
- session phases
- exact allowed MCP tool names
- source-of-truth entity rules
- memory note rules
- response format
- handoff checklist
- prohibited actions
- observation/debugging guidance

If DeepAgents skill loading is used, the agent construction should include that skills directory. If skill loading is deferred, the file still serves as an implementation and prompt-maintenance runbook.

### Decision 4: Keep the full workflow test gated

The live smoke should be behind an explicit environment flag, for example:

```text
RUN_LIVE_DISCOVERY_E2E_TESTS=1
```

This mirrors the existing live memory/agent test pattern and prevents accidental paid LLM calls.

## Risks / Trade-offs

- [Risk] The live smoke can be slow or flaky due to LLM/tool/network behavior.
  - Mitigation: keep it gated and use broad behavioral assertions.

- [Risk] Async Learning Director may not finish content generation within a short timeout.
  - Mitigation: allow configurable polling timeout and print the task id for manual follow-up.

- [Risk] Discovery Agent may ask additional questions before saving entities.
  - Mitigation: the live script can drive a known sequence of answers and stop with useful trace output if not complete.

- [Risk] LangSmith traces may not be available if env vars are missing.
  - Mitigation: treat trace observation as manual verification guidance, while DB/API assertions remain the automated proof.

## Migration Plan

1. Add skill/runbook file and wire it into Discovery Agent construction if compatible.
2. Add deterministic tests for skill content, MCP allowlist, and response/persistence contracts.
3. Add gated live smoke script/test.
4. Document exact commands and expected observations.
5. Run focused tests, then run live smoke manually with Docker services up.
