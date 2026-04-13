# Architecture

The Anti-pilot project is a learning assistant platform built with a modular backend, AI agents, and a Model Context Protocol (MCP) interface.

## System Overview

The system consists of the following components:

- **Backend Service**: A Python-based application that handles business logic, database interactions, and service orchestration.
- **Database**: A relational database managed with SQLAlchemy and Alembic for migrations. It stores user profiles, learning goals, and generated roadmaps.
- **AI Agents**: Powered by LangGraph, these agents handle complex tasks:
    - **Learning Director**: Oversees the learning process and coordinates between different skills.
    - **Planner**: A graph-based agent responsible for evaluating learning needs and generating structured roadmaps.
    - **Docs Agent**: Maintains project documentation by analyzing code changes and updating relevant docs.
- **MCP Server**: Provides a standardized interface for agents to interact with the system's tools and services.
- **Infrastructure**: Containerized using Docker and managed with Docker Compose.

## Key Components

### Database Models
- **User**: Represents a user of the system.
- **Goal**: Defines a specific learning objective.
- **LearningRoadmap**: A structured path to achieve a goal.

### Services
The backend is organized into services that handle specific domains:
- **Goal Service**: Manages user goals.
- **Learning Profile Service**: Handles user learning preferences and history.
- **Roadmap Service**: Manages the creation and retrieval of learning roadmaps.

### Agent Workflow
The system uses LangGraph to define stateful, multi-turn agent workflows. The `LearningDirector` acts as the main entry point, while specialized graphs like the `Planner` handle sub-tasks like roadmap evaluation and generation.
