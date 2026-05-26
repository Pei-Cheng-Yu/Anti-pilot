from datetime import date
from pathlib import Path

from app.langgraph.planner.graphs.evaluate.graph import build_evaluate_graph
from app.langgraph.planner.graphs.generate_roadmap.graph import build_planner_graph
from app.langgraph.planner.schema.entities import GoalSpec, LearningProfile
from dotenv import load_dotenv

# need loadenv manually so langsmith can trace this run
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def main() -> None:
    planner_graph = build_planner_graph()
    evaluate_graph = build_evaluate_graph()

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

    print("\n=== RUN PLANNER GRAPH ===")
    planner_result = planner_graph.invoke(initial_state)

    print("\n=== RUN EVALUATE GRAPH ===")
    evaluate_result = evaluate_graph.invoke(planner_result)

    print("\n=== FINAL RESULT ===")
    print(evaluate_result)


if __name__ == "__main__":
    main()
