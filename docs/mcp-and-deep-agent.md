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
