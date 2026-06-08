from pathlib import Path

import yaml


def test_agent_server_has_worker_capacity_for_async_subagents():
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    command = compose["services"]["agent-server"]["command"]

    assert "langgraph dev" in command
    assert "--n-jobs-per-worker 10" in command
