---
name: roadmap-generation
description: Generate and review personalized learning roadmaps using saved user data. Use when the user asks to create, generate, review, revise, finalize a learning roadmap or study plan, or generate learning content for a roadmap. Fetch the saved goal and learning profile using MCP tools first, then run the planner, review the roadmap, fix real issues directly with MCP update tools, optionally generate learning content when requested, and report the final roadmap summary.
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
8. After roadmap review, mark skillpath content-planning guidance using roadmap MCP update tools.
9. Fix only genuine issues using roadmap MCP update tools.
10. If the user also asks for generated learning content, call `run_content_generator` with the saved `roadmap_id`, fetched `goal`, and fetched `profile`.
11. If content generation was requested, fetch the full roadmap again and confirm generated contents are present before replying.
12. Report that the roadmap is ready.

## Tool usage rules

- Use MCP tools for saved goal, saved profile, roadmap fetch, and roadmap updates.
- Use `run_planner` only after goal and profile have been loaded successfully.
- Use `run_content_generator` only after the roadmap has been saved, reviewed, and any direct roadmap updates are complete.
- Do not ask the user to restate their goal or profile until the MCP tools say the data is missing.
- Do not invent values for goal, profile, milestone ids, skillpath ids, or roadmap ids.
- Pass the fetched `goal` and fetched `profile` objects directly into `run_planner`.
- Pass the same fetched `goal` and fetched `profile` objects directly into `run_content_generator`.

## Review checklist

Review the fetched roadmap for:

- milestone objectives that are vague, generic, or not outcome-focused
- titles that do not match the actual content
- estimated hours that are too heavy or too light for the learner's pace and overload risk
- obvious sequencing or dependency problems
- clear gaps between milestones and skillpaths

Also review skillpaths for post-plan content guidance:

- every skillpath should later receive an article
- mark `practice_mode` only when there is a clear reason:
  - use `coding_problem` for implementation-heavy or hands-on skillpaths
  - use `multiple_choice` for concept-check-heavy skillpaths
  - use `either` only when the best assessment type is not obvious
- do not overwrite `practice_mode` unless the roadmap context gives a clear reason

## Editing rules

- Prefer small direct fixes with MCP update tools.
- Do not rerun the planner for minor wording or hour adjustments.
- Do not make cosmetic edits that do not improve clarity or learning quality.
- If nothing is wrong, make no updates.
- Treat `practice_mode` as an optional post-planning annotation on skillpaths.
- It is acceptable to leave `practice_mode` unset if the best choice is unclear, but prefer setting it when the roadmap context makes the choice obvious.

## Content generation rules

- Generate learning content only when the user asks for content, lessons, articles, exercises, quizzes, or generated learning materials.
- Do not call `run_content_generator` before reviewing and updating the saved roadmap.
- After content generation, fetch the roadmap again and verify that skillpaths have `learning_contents`.
- If no content was generated, tell the user plainly instead of implying that content is saved.

## Final response

In the final user-facing response:

- say the roadmap is ready
- include the number of milestones
- include the number of skillpaths
- include total estimated hours
- mention any fixes you made during review
- if learning content was requested, include how many skillpaths received generated content

If no fixes were needed, say that the roadmap passed review unchanged.
