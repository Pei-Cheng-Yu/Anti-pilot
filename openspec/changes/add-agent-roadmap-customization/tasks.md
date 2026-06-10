## 1. Learning Director prompt nudge (NO new tool)

- [x] 1.1 Confirm the LD already exposes `roadmap_update_milestone`, `roadmap_update_skillpath`, the memory tools, and `run_content_generator` (it does — `tools=[run_planner, run_content_generator, *mcp_tools]`). No tool is added.
- [x] 1.2 Extend `_SYSTEM_PROMPT` in `learning_director/agent.py` with a customization directive: given "customize milestone {id}: {instructions}", read the milestone + its skillpaths (+ memory), apply edits ONLY to that milestone and its skillpaths via `roadmap_update_milestone`/`roadmap_update_skillpath`, set `need_generation=True` on changed skillpaths, then run `run_content_generator` for the roadmap
- [x] 1.3 Make the directive explicit that the agent must NOT modify other milestones, and should return the affected skillpath ids
- [ ] 1.4 Unit test (fake MCP/tool layer): when handed a customize instruction, the LD calls `roadmap_update_skillpath` with `need_generation=True` for the target milestone's skillpaths and then `run_content_generator` — driven by the agent, not a scripted tool
- [ ] 1.5 Unit test: the agent does not call update tools for skillpaths outside the target milestone

## 2. Agent-server run client (reuse the discovery httpx pattern)

- [x] 2.1 Add `app/services/learning_director_agent_server.py` mirroring `discovery_agent_server.py` (httpx → `settings.AGENT_SERVER_URL`), assistant id `learning_director`
- [x] 2.2 `start_customize_run(roadmap_id, milestone_id, instructions, user_id, thread_id)` → `POST /threads/{thread_id}/runs` (background) with `{assistant_id, input:{messages:[customize msg embedding roadmap_id+milestone_id]}, context:{user_id}, if_not_exists:"create"}`; return the run (incl. `run_id`, `status`)
- [x] 2.3 `get_customize_run(thread_id, run_id)` → `GET /threads/{thread_id}/runs/{run_id}` → run status
- [x] 2.4 Mirror discovery's error handling (unavailable → 5xx/RequestError; rejected → 4xx)
- [x] 2.5 Unit test (mock httpx): start posts the right payload (assistant `learning_director`, message contains roadmap_id+milestone_id, context user_id); status GETs the right path

## 3. HTTP endpoints (FastAPI wraps the run)

- [x] 3.1 Add `POST /v1/roadmaps/{roadmap_id}/milestones/{milestone_id}/customize-agent` to `app/main.py` — validate ownership (via `get_roadmap_full`), generate a `thread_id`, call `start_customize_run`, return `{thread_id, run_id, status}`
- [x] 3.2 Add `GET /v1/roadmaps/{roadmap_id}/customize-runs/{thread_id}/{run_id}` — proxy `get_customize_run` → `{status}` (frontend re-fetches the roadmap on `success`)
- [x] 3.3 Return 404 when roadmap/milestone unknown or not owned by user
- [x] 3.4 Leave the existing deterministic `/customize` endpoint unchanged
- [x] 3.5 Endpoint tests (mock the agent-server client): customize-agent validates + returns run handle; unknown milestone → 404; status endpoint proxies run status

## 4. Optional: capture instruction as memory

- [ ] 4.1 If the instruction expresses a durable preference, build an `AddMemoryNoteInput(memory_type=preference_signal|background, …)` and call `add_memory_note` (integrity-gated) — never a direct DB write
- [ ] 4.2 Unit test: a preference-style instruction creates a `preference_signal` note via the integrity lifecycle (deterministic/fake advisor)

## 5. Verification & docs

- [x] 5.1 Run all new unit tests — confirm pass (isolated; fake LLM/content generator; no live LLM required)
- [~] 5.2 Live (gated) test WRITTEN: `tests/test_live_agent_customization.py` seeds a roadmap, POSTs `/customize-agent`, polls the real run to `success`, asserts the milestone's skillpaths changed / content generated. Needs a live run (agent-server rebuilt + reachable + LLM creds).
- [~] 5.3 The live test snapshots before/after (skillpath ids/titles/content counts) for inspection; full 'only-affected' assertion confirmed on a live run.
- [x] 5.4 Update `docs/agent-architecture-operations.html` — replace the deterministic "Customize roadmap" path with the agent-driven revise + content-gen path, and re-render the PNG
- [ ] 5.5 Update `docs/five-layer-memory-access.md` / interaction docs to note the agent-driven customization flow
