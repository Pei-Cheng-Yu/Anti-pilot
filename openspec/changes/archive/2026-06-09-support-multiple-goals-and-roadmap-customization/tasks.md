## 1. Data Model And Migration

- [x] 1.1 Add `goal_id` to `GoalModel`, update relationships for one user to many goals, and remove the one-goal-per-user uniqueness assumption.
- [x] 1.2 Add `goal_id` to `RoadmapModel` and enforce one primary roadmap per goal for new writes.
- [x] 1.3 Add nullable `goal_id` to `DiscoveryConversationModel` for create-new conversations that bind after goal save.
- [x] 1.4 Create Alembic migration that backfills existing goals and unambiguous existing roadmaps while preserving rollback safety.
- [x] 1.5 Update DB model tests or integration tests to verify multiple goals for one user and one roadmap per goal.

## 2. Goal And Roadmap Service Contracts

- [x] 2.1 Update goal service APIs to create, fetch, and update goals by explicit `user_id` and `goal_id`.
- [x] 2.2 Preserve or intentionally replace any compatibility helper that still loads the user's current single goal.
- [x] 2.3 Update roadmap service APIs to persist and fetch roadmaps with explicit goal ownership.
- [x] 2.4 Add ownership checks that reject cross-user goal and roadmap access.
- [x] 2.5 Update MCP goal and roadmap tools to expose explicit goal-aware contracts needed by Discovery and Learning Director.

## 3. Discovery Multi-Goal Flow

- [x] 3.1 Update Discovery conversation creation and storage to support nullable and later-bound `goal_id`.
- [x] 3.2 Update FastAPI discovery message proxy to pass bound `goal_id` into agent-server context when present.
- [x] 3.3 Update Discovery Agent prompt, safe status tools, and save flow so a new goal can be created without overwriting existing goals.
- [x] 3.4 Bind the Discovery conversation to the saved `goal_id` immediately after goal creation.
- [x] 3.5 Update Discovery API tests for second-goal creation, bound conversation context, and missing-goal handoff prevention.

## 4. Learning Director Handoff

- [x] 4.1 Update Discovery-to-Learning-Director async handoff to include explicit `goal_id`.
- [x] 4.2 Update Learning Director prompt and tool invocation path to load goal by `user_id` and `goal_id`.
- [x] 4.3 Update planner persistence path so the generated roadmap links to the selected goal.
- [x] 4.4 Add tests proving two goals for the same user generate isolated roadmaps and do not overwrite each other.

## 5. Roadmap Customization Foundation

- [x] 5.1 Add milestone-scoped customization request and response schemas.
- [x] 5.2 Add FastAPI customization endpoint that requires `roadmap_id` and `milestone_id` context and validates user ownership.
- [x] 5.3 Add narrow Roadmap Customizer agent or service boundary with only roadmap read/update tools.
- [x] 5.4 Implement milestone update handling through roadmap service validation.
- [x] 5.5 Mark affected skillpaths for revision or regeneration when milestone changes can stale downstream content.
- [x] 5.6 Add tests for successful milestone customization, ambiguous customization follow-up, and cross-user rejection.

## 6. Verification

- [x] 6.1 Run focused backend tests for goal, roadmap, discovery, MCP, Learning Director, and customization contracts.
- [x] 6.2 Run `compileall` for backend app and tests.
- [x] 6.3 Rebuild Docker services and run gated live Discovery e2e to confirm create-new flow still works through FastAPI and agent-server.
- [x] 6.4 Add or update live/manual verification notes for multi-goal and milestone customization flows.
