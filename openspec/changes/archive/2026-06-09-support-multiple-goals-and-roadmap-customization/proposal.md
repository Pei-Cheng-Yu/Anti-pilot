## Why

The current learning model effectively treats a user as having one goal, which makes Discovery and roadmap generation ambiguous once a learner wants to start a second learning objective. The product direction is clearer if each new Discovery flow creates a distinct goal with its own roadmap, while the learner's profile remains user-level.

## What Changes

- Allow one user to own multiple learning goals instead of replacing a single user-level goal.
- Link each roadmap to the goal it was generated for, with one primary roadmap per goal for this change.
- Link each Discovery conversation to the goal it is creating or refining so the agent-server thread has explicit goal context after the goal exists.
- Keep `LearningProfile` one per user; it continues to represent durable learning preferences, baseline, weak areas, and pacing.
- Add a milestone-scoped roadmap customization foundation where the UI supplies the roadmap and milestone context instead of relying on a freeform agent to infer it.
- Introduce a narrow Roadmap Customizer agent/tool boundary for revising an existing milestone and related skillpaths.
- Defer a general cross-goal freeform chatbot; all v1 goal and customization flows are entered from explicit UI context.

## Capabilities

### New Capabilities

- `multi-goal-roadmaps`: Users can create and access multiple goals, each with its own generated roadmap and explicit Discovery conversation binding.
- `roadmap-customization`: Users can request milestone-scoped roadmap changes through explicit roadmap/milestone context.

### Modified Capabilities

- None.

## Impact

- Database models and migrations for goal identity, user-to-goal cardinality, roadmap-to-goal ownership, and discovery conversation goal binding.
- Goal, roadmap, Discovery, MCP, and Learning Director service contracts that currently assume a single goal per user.
- FastAPI discovery and roadmap endpoints where the frontend creates new goals or customizes an existing roadmap/milestone.
- LangGraph Discovery Agent and future Roadmap Customizer agent tool allowlists and prompts.
- Tests for multi-goal isolation, one-roadmap-per-goal behavior, explicit goal handoff, and milestone-scoped customization ownership checks.
