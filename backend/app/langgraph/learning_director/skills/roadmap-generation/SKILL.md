---
name: roadmap-generation
description: Generate and review personalized learning roadmaps using saved user data. Use when the user asks to create, generate, review, revise, or finalize a learning roadmap or study plan. Fetch the saved goal and learning profile using MCP tools first, then run the planner, review the roadmap, fix real issues directly with MCP update tools, and report the final roadmap summary.
---

# Roadmap Generation

Follow this workflow exactly when the user asks for roadmap creation or roadmap review.

## Required flow

1. Fetch the saved goal using the goal MCP tool.
2. Fetch the saved learning profile using the learning profile MCP tool.
3. If either is missing, stop and tell the user exactly what is missing.
4. Call `run_planner` with the fetched `goal` and `profile`.
5. Keep the returned `roadmap_id`.
6. Fetch the full roadmap using the roadmap MCP read tool.
7. Review the roadmap before replying.
8. Fix only genuine issues using roadmap MCP update tools.
9. Report that the roadmap is ready.

## Tool usage rules

- Use MCP tools for saved goal, saved profile, roadmap fetch, and roadmap updates.
- Use `run_planner` only after goal and profile have been loaded successfully.
- Do not ask the user to restate their goal or profile until the MCP tools say the data is missing.
- Do not invent values for goal, profile, milestone ids, skillpath ids, or roadmap ids.
- Pass the fetched `goal` and fetched `profile` objects directly into `run_planner`.

## Review checklist

Review the fetched roadmap for:

- milestone objectives that are vague, generic, or not outcome-focused
- titles that do not match the actual content
- estimated hours that are too heavy or too light for the learner's pace and overload risk
- obvious sequencing or dependency problems
- clear gaps between milestones and skillpaths

## Editing rules

- Prefer small direct fixes with MCP update tools.
- Do not rerun the planner for minor wording or hour adjustments.
- Do not make cosmetic edits that do not improve clarity or learning quality.
- If nothing is wrong, make no updates.

## Final response

In the final user-facing response:

- say the roadmap is ready
- include the number of milestones
- include the number of skillpaths
- include total estimated hours
- mention any fixes you made during review

If no fixes were needed, say that the roadmap passed review unchanged.
