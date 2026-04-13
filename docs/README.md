# Anti-pilot Docs

Welcome to the Anti-pilot project documentation. Anti-pilot is an AI-powered learning assistant that helps users define goals and generates structured learning roadmaps using a "Deep Agent" architecture and the Model Context Protocol (MCP).

## Core Documentation

- [Architecture](./architecture.md): High-level overview of the system components, including the backend, database, and agents.
- [MCP and Deep Agent](./mcp-and-deep-agent.md): Details on the MCP server, tools, and the Learning Director agent.
- [Testing](./testing.md): Instructions on how to run tests and maintain code quality.

## Local preview

If you want to preview the Docsify site locally, serve the `docs/` folder with any static server.

Examples:

```bash
python -m http.server 3000 --directory docs
```

Then open:

```text
http://localhost:3000
```

## GitHub Actions

- `.github/workflows/docs-pages.yml`
  Deploys the `docs/` site to GitHub Pages on pushes to `main`.
- `.github/workflows/docs-agent.yml`
  Runs the docs agent manually and opens a PR if documentation files under `docs/` were updated.
