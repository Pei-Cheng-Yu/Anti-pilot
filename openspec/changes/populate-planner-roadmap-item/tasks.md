## 1. Planner Finalization

- [x] 1.1 Add roadmap metadata construction to planner finalization, either inside `finalize_skillpath` or in a dedicated `finalize_roadmap` node after skillpath finalization.
- [x] 1.2 Build `RoadmapItem` deterministically from `roadmap_uuid`, `goal_spec`, `learning_profile`, milestones, and skillpaths.
- [x] 1.3 Keep assumptions conservative and avoid blindly copying all prior knowledge into assumptions.

## 2. Caller Compatibility

- [x] 2.1 Verify learning director `run_planner` still persists roadmap metadata correctly when `result["roadmap"]` is present.
- [x] 2.2 Verify FastAPI goal creation no longer fails from `NoneType` roadmap access on successful planner output.

## 3. Tests

- [x] 3.1 Add or update a planner-focused test that asserts final planner output includes a non-null `RoadmapItem`.
- [x] 3.2 Add or update route/service coverage if available to assert roadmap metadata survives persistence and readback.
- [x] 3.3 Run the focused planner/API tests relevant to the changed path.
