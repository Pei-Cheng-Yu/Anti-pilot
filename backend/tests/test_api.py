import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app

client = TestClient(app)

def test_read_root():
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "online", "message": "AntiCopilot API is running"}

def test_get_roadmap_fallback():
    """Test the fallback logic for a known mock roadmap ID."""
    response = client.get("/v1/roadmaps/full-stack-dev")
    assert response.status_code == 200
    data = response.json()
    assert data["roadmap"]["title"] == "Full-Stack Dev"
    assert len(data["milestones"]) > 0
    assert len(data["skillpaths"]) > 0

def test_get_roadmap_not_found():
    """Test roadmap retrieval for a non-existent ID."""
    response = client.get("/v1/roadmaps/non-existent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Roadmap not found"

@patch("app.main.build_planner_graph")
def test_create_goal(mock_build_planner):
    """Test the create goal endpoint with a mocked planner."""
    # Mock the planner graph and its invoke method
    mock_planner = MagicMock()
    mock_build_planner.return_value = mock_planner
    
    mock_planner.invoke.return_value = {
        "roadmap": {"title": "Test Roadmap", "summary": "A test roadmap"},
        "milestones": [{"milestone_id": "m1", "title": "Milestone 1"}],
        "skillpaths": [{"skillpath_id": "s1", "title": "Skillpath 1"}]
    }

    request_body = {
        "goal_spec": {
            "title": "Learn Testing",
            "description": "Learn how to write tests",
            "target_outcome": "Write good tests",
            "deadline": "2026-12-31",
            "criteria": ["Write 10 tests"],
            "constraints": ["1 hour/day"]
        },
        "learning_profile": {
            "baseline_level": "beginner",
            "prior_knowledges": [],
            "weak_areas": [],
            "pace_preference": "balanced",
            "confidence_level": "medium",
            "needs_recap": False,
            "prefers_examples_first": True,
            "overload_risk": "low"
        }
    }

    response = client.post("/v1/goals", json=request_body)
    assert response.status_code == 200
    data = response.json()
    assert "roadmap_id" in data
    assert data["roadmap"]["title"] == "Test Roadmap"
    assert len(data["milestones"]) == 1

def test_report_struggle():
    """Test the struggle reporting endpoint."""
    signal = {
        "roadmap_id": "test-roadmap",
        "milestone_id": "m1",
        "skillpath_id": "s1",
        "code_context": "def foo(): pass",
        "diagnostic_message": "Error at line 1"
    }
    response = client.post("/v1/signals/struggle", json=signal)
    assert response.status_code == 200
    data = response.json()
    assert "hint" in data
    assert data["action_required"] is True
