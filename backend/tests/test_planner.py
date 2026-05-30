import asyncio
from datetime import date
from pathlib import Path

from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.langgraph.planner.graphs.generate_roadmap.nodes import finalize_skillpath
from app.schema.entities import GoalSpec, LearningProfile, MilestoneItem
from dotenv import load_dotenv

# need loadenv manually so langsmith can trace this run
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def test_finalize_skillpath_populates_deterministic_roadmap_item():
    goal = GoalSpec(
        title="Learn FastAPI Backend Development",
        description="Learn FastAPI from beginner to building a CRUD backend.",
        target_outcome="Build a small production-style FastAPI project.",
        deadline=date(2026, 6, 30),
        criteria=[
            "Understand HTTP basics",
            "Build CRUD APIs",
            "Use validation and persistence",
        ],
        constraints=[
            "6 hours per week",
            "Prefer hands-on learning",
        ],
    )
    profile = LearningProfile(
        baseline_level="intermediate",
        prior_knowledges=["C++", "C#", "unrelated hobby context"],
        weak_areas=["Basic Python", "HTTP concepts", "database design"],
        pace_preference="intensive",
        confidence_level="medium",
        needs_recap=False,
        prefers_examples_first=True,
        overload_risk="medium",
    )
    milestone = MilestoneItem(
        roadmap_uuid="roadmap-123",
        milestone_id="milestone-1",
        title="Build APIs",
        description="Learn API fundamentals.",
        objective="Understand FastAPI route structure.",
        estimated_hours=8,
        order_index=1,
    )

    result = finalize_skillpath(
        {
            "roadmap_uuid": "roadmap-123",
            "goal_spec": goal,
            "learning_profile": profile,
            "milestones": [milestone],
            "skillpath_drafts": [
                {
                    "milestone_id": "milestone-1",
                    "title": "HTTP routing basics",
                    "description": "Learn request routing.",
                    "estimated_hours": 3,
                    "learning_objectives": ["Explain routes"],
                    "depends_on_titles": [],
                }
            ],
        }
    )

    roadmap = result["roadmap"]

    assert roadmap.roadmap_id == "roadmap-123"
    assert roadmap.title == goal.title
    assert roadmap.version == 1
    assert roadmap.target_outcome == goal.target_outcome
    assert "1 milestones and 1 skill paths" in roadmap.summary
    assert result["skillpaths"][0].title == "HTTP routing basics"
    assert any("6 hours per week" in item for item in roadmap.assumptions)
    assert any("intermediate" in item for item in roadmap.assumptions)
    assert not any("unrelated hobby context" in item for item in roadmap.assumptions)


async def main() -> None:
    graph = build_planner_graph()

    initial_state = {
        "goal_spec": GoalSpec(
            title="Learn FastAPI Backend Development",
            description="Learn FastAPI from beginner to building a CRUD backend.",
            target_outcome="Build a small production-style FastAPI project.",
            deadline=str(date(2026, 6, 30)),
            criteria=[
                "Understand HTTP basics",
                "Build CRUD APIs",
                "Use validation and persistence",
            ],
            constraints=[
                "6 hours per week",
                "Prefer hands-on learning",
            ],
        ),
        "learning_profile": LearningProfile(
            baseline_level="intermediate",
            prior_knowledges=["C++", "C#"],
            weak_areas=["Basic Python", "HTTP concepts", "database design"],
            pace_preference="intensive",
            confidence_level="medium",
            needs_recap=False,
            prefers_examples_first=True,
            overload_risk="medium",
        ),
    }

    result = graph.invoke(initial_state)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
