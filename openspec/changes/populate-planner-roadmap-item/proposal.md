## Why

The planner state declares a `roadmap` output, but the generate-roadmap graph currently finishes without populating a `RoadmapItem`. This causes callers that trust the planner contract, such as the FastAPI `/v1/goals` route, to fail when they dereference `roadmap.title`.

## What Changes

- Populate a deterministic `RoadmapItem` as part of planner finalization.
- Keep the initial implementation narrow and based on existing planner inputs and outputs: roadmap UUID, goal, learner profile, milestones, and skillpaths.
- Add focused coverage that verifies planner output includes a non-null roadmap item.
- Do not add planner memory retrieval or an extra LLM call in this change.

## Capabilities

### New Capabilities
- `planner-roadmap-output`: The roadmap planner produces complete top-level roadmap metadata alongside milestones and skillpaths.

### Modified Capabilities

## Impact

- Affects `backend/app/langgraph/planner/graphs/generate_roadmap`.
- Affects planner output consumed by the learning director and FastAPI goal creation flow.
- No database schema changes.
- No new external dependencies.
