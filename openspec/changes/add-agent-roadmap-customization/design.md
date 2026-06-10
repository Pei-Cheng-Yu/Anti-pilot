## Context

The current customize flow is deterministic (`roadmap_customization.customize_milestone` → `_milestone_update_fields` writes explicit fields, stores `instructions` as `revision_reason`, flags `need_generation`). It does not interpret the instruction and does not regenerate content.

The pieces needed for an agent-driven version already exist:
- **Learning Director** (`learning_director/agent.py`) is a DeepAgent with `run_planner`, `run_content_generator`, and the `roadmap` MCP tools (`update_milestone`, `update_skillpath`) plus the memory MCP tools.
- `run_content_generator(roadmap_id, goal, profile, …)` loads the roadmap, runs the content graph, persists. The content graph already **skips skillpaths where `need_generation` is False** and resets the flag after generating.
- The Discovery → Learning Director flow already runs long work as an **async task** returning a `job_id` the learner polls (the roadmap-generation path).

## Goals / Non-Goals

**Goals:**
- Interpret a free-form `instructions` with an agent and revise the milestone + its skillpaths accordingly.
- Regenerate content only for the affected skillpaths.
- Run async with clarification, since content generation is long-running and instructions can be vague — via the **existing conversational flow** (`start_async_task` / `check_async_task`).
- Reuse the Learning Director **and its existing tools** + the existing conversational async mechanism — no new agent, **no new tool, no new endpoint, no new job store**; only two prompt nudges.

**Non-Goals:**
- No change to the existing deterministic `/customize` endpoint (kept for explicit field edits).
- No cross-milestone edits — scope is the targeted milestone and its skillpaths.
- No new content-generation engine — reuse `run_content_generator` / the content graph.
- No synchronous generation inside the HTTP request.

## Decisions

### Decision 1: Just invoke the existing Learning Director — NO new tool

The Learning Director is built with `tools=[run_planner, run_content_generator, *mcp_tools]`, and `*mcp_tools` already includes the full MCP set — `roadmap_update_milestone`, `roadmap_update_skillpath`, the memory tools, etc. So the agent **already has everything** to read context, revise a milestone and its skillpaths, and regenerate content. Adding a `customize_roadmap` tool would be redundant and defeat the point of using an agent — the agent's job is to *decide which existing tools to call*.

The only code needed is therefore:
- a small **system-prompt addition** so the LD reliably handles a customization request ("revise milestone X per this instruction, then regenerate the affected skillpaths' content"), and
- an **entry point** (endpoint + async job) that hands the LD the instruction.

No new tool, no new agent, no new graph.

**Alternative considered:** add a `customize_roadmap` tool that scripts update_milestone → update_skillpath → run_content_generator. Rejected — the LD already orchestrates exactly these; scripting them in a tool removes the agent's judgement and duplicates wiring.

### Decision 2: What the agent does when handed the instruction

Given "customize milestone {id}: {instructions}", the LD (using its existing tools):
1. Load the milestone + its skillpaths (`get_roadmap_full`) and retrieve the learner's memory (`retrieve_learning_memory`) for personalization.
2. Interpret `instructions` and decide concrete changes: milestone field edits and per-skillpath edits (edit / add / reorder).
3. Apply them with `update_milestone` and `update_skillpath`, setting `need_generation=True` (and `revision_reason`) on changed skillpaths.
4. Call `run_content_generator` for the roadmap; the content graph regenerates only the `need_generation` skillpaths and resets the flag.
5. Return the affected skillpath ids + the refreshed roadmap.

### Decision 3: Invoke the Learning Director directly via a run/thread — NOT via Discovery, NO new job store

Customize targets a specific existing roadmap/milestone, and the action originates in the roadmap UI (so the frontend already has `roadmap_id` + `milestone_id`). The **Discovery Agent is the wrong host**: it is goal-onboarding-only, carries `user_id`/`goal_id` but **no `roadmap_id`/`milestone_id`**, and threading those through the Discovery→LD-subagent context is awkward and serves nothing else in Discovery. Also, the LD inherits only `CURRENT_USER_ID`/`CURRENT_GOAL_ID` from a parent — `roadmap_id` is always an **explicit argument** — so the ids must be in the LD's input regardless.

So we start a **`learning_director` run** (already served as that graph on the agent-server) with input *"customize milestone {milestone_id} in roadmap {roadmap_id}: {instruction}"* and `user_id` in context. Because a run sits on a **thread**, the LD can **ask one clarifying question** (the learner replies on the thread) and the **run status** provides "start → generating… → result". This reuses the LangGraph platform's thread/run + status — **no new job store**, no Discovery.

**Alternatives considered:**
- *Route through the Discovery Agent (`start_async_task`)* — rejected: Discovery has no roadmap/milestone context; wrong responsibility.
- *New backend endpoint + bespoke job store* — rejected: re-implements the thread/run/status the platform already provides.
- *Synchronous one-shot invoke* — rejected: long calls / timeouts, and no room for the clarification turn.

### Decision 4: Keep the deterministic `/customize` for explicit field edits

The conversational, instruction-driven path is additive; the existing `/customize` endpoint (explicit title/description/objective/hours) stays for UI form edits. The frontend picks: form edit → `/customize`; natural-language change → send a message to the conversation.

### Decision 5: Bounded, owned, idempotent-ish

- Ownership is verified (the milestone belongs to the user/roadmap) before the agent runs.
- The agent is constrained to the target milestone and its skillpaths.
- Re-running with the same instruction re-revises and regenerates (generation itself is gated by `need_generation`, so unchanged skillpaths are not redone).
- Optionally, the instruction is written as a `preference_signal`/`background` memory note through the integrity lifecycle so future planning reflects it.

## Risks / Trade-offs

**Agent makes an over-broad or wrong structural change** → Mitigation: scope the tools to the target milestone; the agent prompt forbids touching other milestones; return the diff (affected skillpath ids) for the UI to confirm/show.

**Long job / partial failure** → Mitigation: job status reports `failed` with a summary; generation is per-skillpath and gated by `need_generation`, so a retry only regenerates what's still flagged.

**LLM/loop concerns during content generation** → reuse the existing content graph path (already production-exercised); the customization agent triggers it via `run_content_generator`, which runs the graph the same way the normal flow does.

**Cost** → an extra agent reasoning pass per customize plus content generation; acceptable for an explicit user-initiated action, and it's async.

## Migration Plan

Additive and prompt-only: extend the LD `_SYSTEM_PROMPT` (done) and the conversational agent's guidance so a customize request fires the LD via `start_async_task`. No new endpoints, job store, tools, or DB schema. Existing `/customize`, `generate-content`, and the conversation endpoints are unchanged. Rollback: revert the two prompt additions.
