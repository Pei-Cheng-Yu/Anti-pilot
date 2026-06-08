## Context

The current backend has one `GoalModel` per `UserModel` through a unique `goals.user_id` column and a `UserModel.goal` one-to-one relationship. `RoadmapModel` belongs to a user but does not point to the goal it was generated from. `DiscoveryConversationModel` maps a conversation to a user but not to a goal, so a resumed agent-server thread has no durable way to know which learning objective it is collecting or handing off.

The product direction is now multiple goals per learner, with one roadmap per goal. The learner's `LearningProfileModel` remains one per user because it captures durable learning preferences and baseline information that can inform all goals. Customization is a separate UI mode entered from a specific roadmap or milestone, not a general cross-goal chatbot.

## Goals / Non-Goals

**Goals:**

- Support multiple goals per user without requiring the Discovery Agent to infer which goal is active from conversation text alone.
- Ensure each goal has at most one primary roadmap in this change.
- Bind Discovery conversations to the goal being created or refined once that goal exists.
- Keep LearningProfile one per user and reuse it across all goals.
- Provide a milestone-scoped roadmap customization foundation with explicit `roadmap_id` and `milestone_id` context from FastAPI.
- Keep service-layer ownership and authorization checks for all DB writes.

**Non-Goals:**

- Do not build a general freeform cross-goal chatbot.
- Do not introduce multiple roadmaps, roadmap versions, or roadmap history per goal.
- Do not make learning profiles goal-specific in this change.
- Do not allow the Discovery Agent to customize existing roadmaps.
- Do not let agent prompts be the only guard for ownership or write validation.

## Decisions

### Goal identity becomes explicit

Add a stable public `goal_id` to `GoalModel`, remove the unique constraint from `goals.user_id`, and make `(user_id, goal_id)` the lookup boundary for goal operations. Existing single-goal users are migrated by assigning a generated `goal_id` to their current row.

Alternative considered: keep one goal row per user and store future goals as memory notes. That would keep the schema smaller, but it would make roadmap generation, progress, and UI navigation ambiguous. Goals are source-of-truth entities and need first-class identity.

### One primary roadmap per goal

Add `goal_id` to `RoadmapModel` and enforce one roadmap per goal for this change. Roadmap retrieval and persistence require both `user_id` and `goal_id` or a `roadmap_id` that resolves to a goal owned by the user.

Alternative considered: allow multiple roadmap versions per goal now. That is useful later for revision history, but it complicates the immediate Discovery handoff and frontend selection model. V1 keeps a single active roadmap per goal.

### Discovery conversations bind to goals

Add nullable `goal_id` to `DiscoveryConversationModel`. A newly created conversation may start without a goal if the learner has not confirmed enough information yet. Once Discovery saves a goal, FastAPI or the Discovery service persists the conversation-to-goal binding and subsequent turns pass the bound goal context to the agent-server.

Alternative considered: use `conversation_id` as the goal id. That couples chat-thread lifecycle to product data. A learner may restart Discovery or create a goal through a future non-chat flow, so goal identity should remain separate.

### FastAPI owns active-context selection

Frontend flows choose the context by route and UI position:

- Create-new flow starts an unbound Discovery conversation and results in a new goal and roadmap.
- Existing-goal flow uses an explicit `goal_id`.
- Customize flow uses explicit `roadmap_id` and usually `milestone_id`.

The agent may ask a clarifying question when context is ambiguous, but the backend must not rely on the agent to choose among all user goals.

Alternative considered: let the Discovery Agent list and choose goals with tools. That adds flexibility but creates accidental-update risk and makes the frontend's mental model weaker. Explicit route context is safer and easier to test.

### Roadmap customization is a separate product-facing agent boundary

Introduce a Roadmap Customizer agent or service boundary that operates on a single roadmap/milestone context. It may reason about requested changes, but roadmap services validate ownership and persist updates. The first scope is milestone-level changes and related skillpath adjustments or regeneration marks.

Alternative considered: reuse Learning Director for customization. Learning Director's role is generation orchestration after goal/profile are confirmed. Reusing it for interactive edits would blur responsibilities and make tool permissions broader than needed.

## Risks / Trade-offs

- Schema migration risk -> Use an additive migration first where possible, backfill `goal_id`, then tighten uniqueness and foreign keys after data is valid.
- Existing code assumes `get_goal(user_id)` -> Preserve a compatibility helper only where needed, but new Discovery and Learning Director paths must pass `goal_id`.
- Agent may still omit goal context in handoff -> FastAPI and MCP tools should enforce required `goal_id` for multi-goal paths and fail loudly in tests.
- One roadmap per goal limits future version history -> Keep the schema compatible with future roadmap versions by using explicit `goal_id` and unique constraints that can later be relaxed or versioned.
- Customizer could over-edit generated content -> V1 should update milestone and skillpath planning fields, and mark content as needing regeneration rather than silently rewriting all learning content.

## Migration Plan

1. Add `goal_id` to `goals`, backfill existing rows, and add uniqueness on `goals.goal_id`.
2. Remove or replace the unique `goals.user_id` constraint so a user can own multiple goals.
3. Add nullable `goal_id` to `roadmaps`, backfill existing roadmaps by linking each user's current roadmap to that user's existing goal when unambiguous, then enforce ownership/uniqueness constraints for new writes.
4. Add nullable `goal_id` to `discovery_conversations`.
5. Update services and MCP tools to support explicit goal operations while keeping compatibility shims for tests or older endpoints during the transition.
6. Update Discovery handoff and Learning Director load path to use explicit `goal_id`.
7. Add Roadmap Customizer endpoints and agent/service boundary after multi-goal persistence is stable.

Rollback for the migration should keep old columns intact until all service paths are verified. If deployment must roll back after additive columns are added, old single-goal code can continue using `user_id` while ignoring `goal_id`.

## Open Questions

- Should the create-new Discovery endpoint optionally accept a client-generated `goal_id`, or should the backend always generate it?
- Should customization v1 directly edit skillpath titles/objectives, or only mark affected skillpaths as needing regeneration after a milestone change?
- Should the frontend list goals directly from a new `/v1/goals` endpoint before roadmap list pages are updated, or should goal metadata be surfaced through roadmap list responses first?
