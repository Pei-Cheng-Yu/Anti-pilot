## 1. Discovery Agent Skill Guidance

- [x] 1.1 Create a Discovery Agent skill/runbook under `backend/app/langgraph/discovery_agent/skills/`
- [x] 1.2 Document the Discovery Agent mission, session phases, one-question-at-a-time rule, and response format
- [x] 1.3 Document exact allowed MCP tool names and prohibited tools
- [x] 1.4 Document `GoalSpec` and `LearningProfile` source-of-truth fields
- [x] 1.5 Document memory write policy, allowed memory types, and examples
- [x] 1.6 Document Learning Director handoff checklist and expected post-handoff `DiscoveryResponse`
- [x] 1.7 Wire the skill directory into `create_discovery_agent()` if compatible with current DeepAgents skill loading

## 2. Deterministic Contract Tests

- [x] 2.1 Add tests that assert the Discovery Agent skill/runbook contains required tool names
- [x] 2.2 Add tests that assert the skill/runbook documents prohibited memory lifecycle writes
- [x] 2.3 Add tests that assert the skill/runbook documents required goal/profile fields
- [x] 2.4 Add tests that assert Discovery Agent construction includes the skill directory when skill loading is enabled
- [x] 2.5 Add tests that assert Discovery Agent MCP allowlist still contains only discovery-safe tools

## 3. Live Workflow Smoke Test

- [x] 3.1 Add a gated live test or script behind `RUN_LIVE_DISCOVERY_E2E_TESTS=1`
- [x] 3.2 The live workflow SHALL create a unique test user and discovery conversation through FastAPI
- [x] 3.3 The live workflow SHALL send enough learner messages to let Discovery Agent collect goal and profile details
- [x] 3.4 The live workflow SHALL include at least one durable preference or background signal for memory note creation
- [x] 3.5 The live workflow SHALL wait for or poll handoff completion until roadmap/content persistence is observable
- [x] 3.6 The live workflow SHALL clean up the unique test user data when possible

## 4. Live Workflow Assertions

- [x] 4.1 Assert `GoalSpec` is persisted with required fields
- [x] 4.2 Assert `LearningProfile` is persisted with required fields
- [x] 4.3 Assert any discovery-authored memory notes are only `preference_signal` or `background`
- [x] 4.4 Assert a roadmap is persisted for the test user
- [x] 4.5 Assert at least one milestone and one skillpath are persisted
- [x] 4.6 Assert at least one generated learning content item is persisted
- [x] 4.7 Assert the final Discovery Agent response includes `session_complete: true` and a non-empty roadmap job id when handoff occurs

## 5. Observation Documentation

- [x] 5.1 Document exact commands to run the live workflow smoke test
- [x] 5.2 Document expected API response fields at each major phase
- [x] 5.3 Document expected DB rows to inspect after the run
- [x] 5.4 Document expected LangSmith trace/tool calls to inspect
- [x] 5.5 Document common failure modes and which logs to check

## 6. Verification

- [x] 6.1 Run deterministic discovery tests
- [x] 6.2 Run existing API tests
- [x] 6.3 Run the gated live workflow smoke test manually with Docker services running
- [x] 6.4 Verify OpenSpec change with `openspec validate add-discovery-e2e-workflow-and-skills --strict`
