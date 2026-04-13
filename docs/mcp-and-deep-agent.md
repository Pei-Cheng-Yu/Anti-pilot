# MCP and Deep Agent

The project leverages the Model Context Protocol (MCP) to expose internal services to AI agents, enabling a "Deep Agent" architecture where specialized agents can perform complex tasks autonomously.

## MCP Server

The MCP server (`backend/app/mcp/server.py`) acts as a bridge between the AI agents and the backend services. It exposes a set of tools that agents can use to interact with the system.

### Available Tools

- **Goal Tools**: For creating, retrieving, and updating user learning goals.
- **Learning Profile Tools**: For managing user-specific learning preferences and history.
- **Roadmap Tools**: For generating and managing learning roadmaps.

## Learning Director Agent

The `LearningDirector` is the primary agent responsible for orchestrating the learning experience. It is implemented using LangGraph and utilizes various skills to fulfill user requests.

### Responsibilities
- Understanding user goals and learning context.
- Invoking the `Planner` graph for roadmap generation.
- Coordinating between different system skills.

### Skills
One of the core skills available to the Learning Director is **Roadmap Generation**, which involves:
1. Evaluating the user's current knowledge and goal.
2. Generating a structured roadmap with specific milestones and resources.
3. Reviewing and refining the roadmap for quality and relevance.

## Planner Graph

The `Planner` is a specialized LangGraph that handles the logic of roadmap creation. It includes nodes for:
- **Evaluate**: Assessment of the learning path.
- **Generate Roadmap**: Creating the actual roadmap steps.
- **Review**: Ensuring the roadmap meets the required standards.

## Docs Agent

The `DocsAgent` is responsible for keeping the project documentation in sync with the codebase. It is triggered by GitHub Actions or can be run manually.

### Responsibilities
- Monitoring code changes in the repository.
- Identifying which documentation files are affected by those changes.
- Updating the documentation to reflect the new state of the code.
- Ensuring consistency across all documentation pages.

### Skills
The Docs Agent uses the **Docs Maintenance** skill, which provides a structured workflow for inspecting changes and applying updates to the `/docs/` directory. It uses filesystem tools to read code and edit documentation files.

### Running the Docs Agent

The agent can be run manually using the provided script:

```bash
python scripts/run_docs_agent.py
```

This will analyze the changes in the repository and update the files in the `/docs/` directory accordingly.
