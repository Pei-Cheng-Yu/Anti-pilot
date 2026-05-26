import asyncio
from datetime import date
from pathlib import Path
from uuid import uuid4

from app.langgraph.planner.graphs.generate_roadmap.graph import build_quick_review_logic
from app.schema.entities import GoalSpec, LearningProfile, MilestoneItem
from dotenv import load_dotenv

# need loadenv manually so langsmith can trace this run
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def main() -> None:
    graph = build_quick_review_logic()

    roadmap_uuid = str(uuid4())

    initial_state = {
        "roadmap_uuid": roadmap_uuid,
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
            prior_knowledges=["C++", "C#", "HTTP concepts", "database design"],
            weak_areas=["Basic Python", "docker"],
            pace_preference="intensive",
            confidence_level="medium",
            needs_recap=False,
            prefers_examples_first=True,
            overload_risk="medium",
        ),
        "milestone_revision_count": 0,
        "milestones": [
            MilestoneItem(
                roadmap_uuid=roadmap_uuid,
                milestone_id=str(uuid4()),
                title="Learn Docker",
                description="Understand docker basics.",
                objective="Understand docker foundations.",
                estimated_hours=12,
                order_index=1,
                dependency_titles=[],
                status="generated",
                need_modification=False,
                revision_reason=None,
            ),
            MilestoneItem(
                roadmap_uuid=roadmap_uuid,
                milestone_id=str(uuid4()),
                title="Learn HTTP Basics",
                description="Learn requests, responses, methods, and status codes.",
                objective="Understand HTTP.",
                estimated_hours=10,
                order_index=2,
                dependency_titles=[],
                status="generated",
                need_modification=False,
                revision_reason=None,
            ),
            MilestoneItem(
                roadmap_uuid=roadmap_uuid,
                milestone_id=str(uuid4()),
                title="Learn Relational Database Design",
                description="Understand tables, primary keys, foreign keys, and SQL basics.",
                objective="Understand database foundations.",
                estimated_hours=12,
                order_index=3,
                dependency_titles=["Learn HTTP Basics"],
                status="generated",
                need_modification=False,
                revision_reason=None,
            ),
        ],
    }

    result = graph.invoke(initial_state)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
