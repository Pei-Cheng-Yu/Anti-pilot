from datetime import date
from pathlib import Path
from uuid import uuid4

from app.langgraph.planner.graphs.evaluate.graph import build_evaluate_graph
from app.langgraph.planner.schema.entities import (
    GoalSpec,
    LearningProfile,
    MilestoneItem,
    SkillPathItem,
)
from dotenv import load_dotenv

# need loadenv manually so langsmith can trace this run
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def main() -> None:
    graph = build_evaluate_graph()

    roadmap_uuid = "test-roadmap"
    milestone_id = str(uuid4())

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
            baseline_level="beginner",
            prior_knowledges=["C++", "C#"],
            weak_areas=["Basic Python", "HTTP concepts", "database design"],
            pace_preference="slow",
            confidence_level="medium",
            needs_recap=True,
            prefers_examples_first=True,
            overload_risk="medium",
        ),
        "milestones": [
            MilestoneItem(
                roadmap_uuid=roadmap_uuid,
                milestone_id=milestone_id,
                title="Build CRUD Backend with FastAPI",
                description="Learn enough FastAPI to build a CRUD backend.",
                objective="Build a simple CRUD backend with validation and persistence.",
                estimated_hours=30,
                order_index=1,
                dependency_titles=[],
                status="generated",
                need_modification=False,
                revision_reason=None,
            )
        ],
        "skillpaths": [
            SkillPathItem(
                skillpath_id=str(uuid4()),
                milestone_id=milestone_id,
                title="Learn backend development with FastAPI, database design, authentication, deployment, and Docker",
                description="Cover everything needed for backend development in one skill path.",
                estimated_hours=24,
                learning_objectives=[
                    "Understand FastAPI",
                    "Understand database design",
                    "Understand authentication",
                    "Deploy application",
                    "Use Docker",
                ],
                prerequisite_skillpath_ids=[],
                status="ready",
                need_generation=True,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
            ),
            SkillPathItem(
                skillpath_id=str(uuid4()),
                milestone_id=milestone_id,
                title="Install FastAPI",
                description="Install FastAPI package.",
                estimated_hours=1,
                learning_objectives=["Install FastAPI"],
                prerequisite_skillpath_ids=[],
                status="ready",
                need_generation=True,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
            ),
            SkillPathItem(
                skillpath_id=str(uuid4()),
                milestone_id=milestone_id,
                title="Write one GET endpoint",
                description="Create one GET endpoint.",
                estimated_hours=1,
                learning_objectives=["Write one GET endpoint"],
                prerequisite_skillpath_ids=[],
                status="ready",
                need_generation=True,
                need_modification=False,
                revision_reason=None,
                affected_downstream_ids=[],
            ),
        ],
        "skillpaths_review": [],
        "skillpath_revisions": [],
    }

    result = graph.invoke(initial_state)

    print("\n=== BAD SKILLPATH EVALUATION RESULT ===")
    print(result)


if __name__ == "__main__":
    main()
