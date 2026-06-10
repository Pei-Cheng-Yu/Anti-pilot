## ADDED Requirements

### Requirement: FastAPI endpoints wrap a Learning Director run on the agent-server
The system SHALL add two backend endpoints that proxy a **background `learning_director` run** on the agent-server (reusing the existing `httpx` agent-server pattern in `discovery_agent_server.py`):
- `POST /v1/roadmaps/{roadmap_id}/milestones/{milestone_id}/customize-agent` — validates ownership, starts a background run (`POST /threads/{thread_id}/runs`, `assistant_id="learning_director"`) whose input message embeds the `roadmap_id`, `milestone_id`, and instruction, with `user_id` in run context, and returns `{thread_id, run_id, status}` immediately.
- `GET /v1/roadmaps/{roadmap_id}/customize-runs/{thread_id}/{run_id}` — proxies the agent-server run status.

The run itself is the durable job (persisted by the agent-server's checkpointer) — **no backend job-status store is added**.

#### Scenario: Start returns a run handle immediately
- **WHEN** the learner POSTs `customize-agent` with an instruction
- **THEN** the endpoint validates the roadmap/milestone, starts the background run, and returns `{thread_id, run_id, status}` without waiting for completion

#### Scenario: Status proxied from the agent-server run
- **WHEN** the frontend polls the status endpoint
- **THEN** it returns the agent-server run status (e.g. `pending|running|success|error`); on `success` the frontend re-fetches the roadmap to see the changes

#### Scenario: Unknown roadmap or milestone
- **WHEN** the roadmap_id/milestone_id is unknown or not owned by the user
- **THEN** `customize-agent` returns 404 and starts no run

---

### Requirement: The run carries roadmap_id + milestone_id in its input
The `roadmap_id` and `milestone_id` SHALL be passed to the Learning Director **in the run input message** (not via Discovery, which has no such context). `user_id` SHALL be passed in the run context like the existing discovery proxy.

#### Scenario: Ids reach the agent
- **WHEN** the run is started
- **THEN** the input message contains the roadmap_id + milestone_id (e.g. "Customize milestone {milestone_id} in roadmap {roadmap_id}: {instruction}") so the LD can call `roadmap_get_roadmap_full`/`roadmap_update_skillpath`/`run_content_generator` for that roadmap

---

### Requirement: Agent interprets the instruction and revises the milestone and skillpaths
The Learning Director SHALL read the target milestone, its skillpaths, and the learner's retrieved memory, interpret `instructions`, and apply the resulting changes via the `roadmap` MCP tools (`update_milestone`, `update_skillpath`). Changed skillpaths SHALL be flagged `need_generation=True` with a `revision_reason`.

#### Scenario: Milestone fields revised from the instruction
- **WHEN** the instruction implies a milestone-level change (e.g. difficulty/scope)
- **THEN** the agent updates the milestone via `update_milestone` accordingly

#### Scenario: Skillpaths revised and flagged
- **WHEN** the instruction implies skillpath edits or additions
- **THEN** the agent edits/adds the relevant skillpaths via `update_skillpath` and sets `need_generation=True` on the changed ones

#### Scenario: Scope is limited to the target milestone
- **WHEN** the agent applies changes
- **THEN** it modifies only the target milestone and its skillpaths — never other milestones

---

### Requirement: Content regenerated for affected skillpaths only
After revising, the job SHALL run content generation via `run_content_generator`, which regenerates only the skillpaths flagged `need_generation=True` and resets the flag on success.

#### Scenario: Only affected skillpaths are regenerated
- **WHEN** content generation runs after the revision
- **THEN** only skillpaths with `need_generation=True` get new `learning_contents`, and unchanged skillpaths are left as-is

#### Scenario: Generation flag reset after success
- **WHEN** a skillpath's content is regenerated successfully
- **THEN** its `need_generation` is set back to False

---

### Requirement: No new tool — the existing Learning Director orchestrates
The customization SHALL be performed by invoking the existing Learning Director with the instruction. No new tool, agent, or graph SHALL be added — the LD already exposes `roadmap_update_milestone`, `roadmap_update_skillpath`, the memory tools, and `run_content_generator`. The only LD change permitted is a system-prompt directive describing how to handle a customize request.

#### Scenario: Agent decides the tool calls
- **WHEN** the job hands the instruction to the Learning Director
- **THEN** the agent itself decides to call `roadmap_update_milestone` / `roadmap_update_skillpath` and `run_content_generator` — there is no scripted `customize_roadmap` tool

#### Scenario: No new tool registered
- **WHEN** the change is implemented
- **THEN** the Learning Director's `tools=[...]` list is unchanged (only `_SYSTEM_PROMPT` is extended)

---

### Requirement: Optional capture of the instruction as memory
The job MAY write the learner's instruction as a `preference_signal` or `background` memory note through the Memory Integrity lifecycle so future planning reflects it. This SHALL go through `add_memory_note` (integrity-gated), never a direct DB write.

#### Scenario: Instruction recorded as preference
- **WHEN** the instruction expresses a durable preference (e.g. "I prefer more hands-on exercises")
- **THEN** a `preference_signal` note may be created via the integrity lifecycle
