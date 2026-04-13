---
name: docs-maintenance
description: Maintain project documentation from repository code changes. Use when updating docs after backend, MCP, database, migration, agent, workflow, or testing changes. Read the changed files first, compare them with existing docs under `docs/`, and update only the affected documentation.
---

# Docs Maintenance

Update documentation by inspecting code changes and editing the docs folder directly.

## Required workflow

1. Read the changed-file summary provided in the user request.
2. Treat the user-provided changed-file summary and code context as the source of truth for non-doc files.
3. Read the existing relevant docs under `/docs/`.
4. Update only the documentation that is actually affected.
5. Keep docs concise and factual.

## Editing rules

- Only write under `/docs/`.
- Never modify files outside `/docs/`.
- Do not create nested paths like `/docs/docs/` or `/workspace/docs/`.
- Preserve the existing docs structure unless a structural change is clearly needed.
- Prefer updating existing pages over creating unnecessary new files.
- Do not invent architecture, commands, URLs, tools, or workflows that are not present in code.
- If no docs changes are needed, make no file edits.

## Content rules

- Explain responsibilities and flows, not implementation trivia.
- Keep testing instructions practical and copy-pasteable.
- When documenting agents, describe:
  - what they are responsible for
  - what tools or services they use
  - how they fit into the system
- When documenting MCP, describe what service capabilities it wraps and exposes.

## Good outcomes

- docs stay aligned with real code changes
- docs remain short and readable
- unchanged topics are left alone
