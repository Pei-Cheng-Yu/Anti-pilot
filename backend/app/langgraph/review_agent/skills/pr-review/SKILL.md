---
name: pr-review
description: Review pull request style code changes from a provided git diff and changed-file summary. Use when summarizing code changes, identifying likely risks, spotting missing tests, or suggesting follow-up improvements for backend, MCP, agent, workflow, database, or documentation changes.
---

# PR Review

Review the provided diff context and produce a concise code review.

## Required output

Write a review with these sections:

1. `Summary`
2. `Suggestions`
3. `Risks`
4. `Testing`

## Review rules

- Keep the review short and specific.
- Focus on high-signal issues and practical follow-up suggestions.
- If there are no obvious issues, say that clearly.
- Treat this as an advisory review, not a merge blocker.
- Do not invent missing context beyond the provided changed files and diff.

## Suggestions

- Prefer actionable suggestions over vague style comments.
- Mention missing tests when behavior, schema, workflows, or agent logic changed.
- Mention documentation gaps when architecture, workflow, or CI behavior changed.
