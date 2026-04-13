# Testing

The project maintains a comprehensive test suite covering backend services, MCP tools, and agent workflows.

## Test Categories

### Service Integration Tests
Located in `backend/tests/test_services_integration.py`, these tests verify the interaction between the backend services and the database.

### MCP Tool Tests
Located in `backend/tests/test_mcp_tools.py`, these tests ensure that the MCP tools correctly wrap the underlying services and return the expected results to the agents.

### Agent Smoke Tests
Located in `backend/tests/test_learning_director_smoke.py`, these tests perform end-to-end checks of the `LearningDirector` agent's primary workflows.

### Planner Graph Tests
Several test files cover the `Planner` graph and its components:
- `backend/tests/test_planner.py`: General planner logic.
- `backend/tests/test_planner_to_evaluate.py`: Tests the transition between planning and evaluation.
- `backend/tests/test_quick_review.py`: Tests the roadmap review process.

## Running Tests

To run the backend tests, use `pytest` from the `backend` directory:

```bash
cd backend
pytest
```

To run a specific test file:

```bash
pytest tests/test_mcp_tools.py
```

## Pre-commit Hooks

The project uses `pre-commit` to ensure code quality. The configuration is defined in `.pre-commit-config.yaml`. To install the hooks:

```bash
pre-commit install
```
