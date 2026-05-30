## Context

The generate-roadmap planner graph declares `roadmap: RoadmapItem` in `PlannerState`, but its nodes currently produce only roadmap UUID, milestones, skillpath drafts, and final skillpaths. The learning director persistence path works around the missing roadmap by using fallback metadata, while the FastAPI goal route can fail when it assumes the roadmap object exists.

This change keeps the fix local to planner finalization. It does not introduce planner memory retrieval, new LLM calls, or database changes.

## Goals / Non-Goals

**Goals:**
- Make the planner graph fulfill its declared `roadmap` output contract.
- Provide deterministic roadmap metadata that is good enough for persistence and API responses.
- Keep caller fallback logic optional rather than required for normal planner success.
- Add focused verification that planner output contains a populated `RoadmapItem`.

**Non-Goals:**
- Do not add memory-aware planner personalization.
- Do not add an LLM call only to generate roadmap metadata.
- Do not change the database schema.
- Do not redesign roadmap, milestone, or skillpath entity shapes.

## Decisions

Create the `RoadmapItem` during final planner finalization, after skillpaths are available. This lets the roadmap summary include generated structure counts while preserving a simple deterministic implementation.

The initial roadmap metadata will be derived from existing state:
- `roadmap_id` from `roadmap_uuid`
- `title` from `goal_spec.title`
- `version` as `1`
- `target_outcome` from `goal_spec.target_outcome`
- `summary` from goal title plus milestone and skillpath counts
- `assumptions` from conservative goal/profile context such as constraints, baseline level, weak areas, and pace preference

This avoids a separate LLM call for metadata. If future planner memory support is added, the same finalization point can incorporate retrieved memory into summary and assumptions.

## Risks / Trade-offs

- Deterministic assumptions may be less polished than LLM-written assumptions. Mitigation: keep wording conservative and avoid claiming every prior knowledge item is directly relevant.
- Placing roadmap creation in `finalize_skillpath` keeps the change small but gives that function two responsibilities. Mitigation: implementation may either extend `finalize_skillpath` for the temporary fix or add a dedicated `finalize_roadmap` node immediately after it if the branch owner prefers a cleaner graph.
- API callers should still handle incomplete planner output gracefully. Mitigation: this change fixes the normal planner contract; defensive API errors can be handled separately if needed.
