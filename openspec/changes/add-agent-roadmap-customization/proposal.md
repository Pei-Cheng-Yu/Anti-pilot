## Why

Today's milestone customization (`roadmap_customization.customize_milestone`) is a **deterministic field edit**: it writes the explicit `title/description/objective/estimated_hours` the caller passes, stores the free-form `instructions` string only as `revision_reason`, and flags the milestone's skillpaths `need_generation=True`. The instruction is **never interpreted**, the skillpath structure is not revised, and **no content is regenerated** — a separate `generate-content` call is required.

What learners actually want is to say *what to change* in natural language ("make this milestone more advanced and add a testing skillpath") and have the system **revise the milestone and its skillpaths, then regenerate the affected content** — driven by an agent, not a hand-filled field form.

## What Changes

- Add an **agent-driven customization** path: the learner sends a free-form `instructions`; we **hand it to the existing Learning Director**, which already has the tools to interpret it against the current milestone + its skillpaths + the learner's memory, then:
  1. revises the milestone fields and its skillpaths (add / edit / reorder) via its existing `roadmap_update_milestone` / `roadmap_update_skillpath` MCP tools,
  2. flags the changed skillpaths `need_generation=True`,
  3. runs **content generation** for the affected skillpaths via its existing `run_content_generator`.
- **Invoke the Learning Director directly — NOT via the Discovery Agent.** Discovery is goal-onboarding-only and carries no `roadmap_id`/`milestone_id`; the LD takes `roadmap_id` as an explicit argument anyway. So the customize starts a **`learning_director` run** (it's already served as that graph on the agent-server) with input *"customize milestone {milestone_id} in roadmap {roadmap_id}: {instruction}"* and `user_id` in context. The frontend already has the ids (the action comes from the roadmap UI).
- Because it's a **run on a thread**, the LD can **ask a clarifying question** (reply on the same thread) and the **run status** gives "start → generating… → result" — reusing the LangGraph platform's thread/run infra, so **no new job store**.
- **No new tool, no new agent, no Discovery involvement.** The only code is the **LD `_SYSTEM_PROMPT` directive** (so the run does revise+regenerate, scoped to the milestone) plus a thin **entry point** to start the run (frontend → agent-server runs API directly, or a thin backend proxy).
- The existing deterministic `/customize` endpoint stays for explicit field edits.
- Optionally capture the instruction as a `preference_signal`/`background` memory note through the normal integrity lifecycle.

## Capabilities

### New Capabilities

- `agent-roadmap-customization`: instruction-driven, agent-orchestrated revision of a milestone + its skillpaths followed by content regeneration, exposed as an async job with status polling

### Modified Capabilities

- none — additive; the existing deterministic `/customize` endpoint is unchanged

## Impact

- `backend/app/langgraph/learning_director/agent.py` — **`_SYSTEM_PROMPT` addition only** (done): how to handle "customize milestone X: …" using its existing `roadmap_update_milestone` / `roadmap_update_skillpath` / `run_content_generator`.
- **Discovery agent — unchanged** (customize does NOT go through it; it has no `roadmap_id`/`milestone_id`).
- **Entry point** — start a `learning_director` run with the customize input. Either the frontend calls the agent-server runs API directly (LangGraph SDK), or a thin backend proxy creates the run and exposes its status. **No new job store** — the LangGraph thread/run carries status and supports the clarification turn.
- Reads: `milestones`, `skillpaths`, `learner_memory_notes`, `skill_mastery_states`. Writes: `milestones`, `skillpaths` (incl. `need_generation`), `learning_contents`; optionally `learner_memory_notes` via the integrity lifecycle.
- No DB schema change.
