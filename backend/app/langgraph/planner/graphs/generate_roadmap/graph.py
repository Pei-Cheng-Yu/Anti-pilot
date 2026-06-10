from app.langgraph.planner.graphs.generate_roadmap.nodes import (
    finalize_skillpath,
    generate_milestone,
    init_roadmap_context,
    milestone_quick_review,
    retrieve_and_rerank_milestones,
    retrieve_goal_memory,
    revise_milestones,
    route_after_milestone_quick_review,
    route_to_skillpath_workers,
    skillpath_worker,
)
from app.langgraph.planner.schema.state import PlannerState
from langgraph.graph import END, START, StateGraph


def build_planner_graph():
    workflow = StateGraph(PlannerState)
    workflow.add_node("init_roadmap_context", init_roadmap_context)
    workflow.add_node("retrieve_goal_memory", retrieve_goal_memory)
    workflow.add_node("generate_milestone", generate_milestone)
    workflow.add_node("milestone_quick_review", milestone_quick_review)
    workflow.add_node("revise_milestones", revise_milestones)
    workflow.add_node("retrieve_and_rerank_milestones", retrieve_and_rerank_milestones)
    workflow.add_node("skillpath_worker", skillpath_worker)
    workflow.add_node("finalize_skillpath", finalize_skillpath)

    workflow.add_edge(START, "init_roadmap_context")
    workflow.add_edge("init_roadmap_context", "retrieve_goal_memory")
    workflow.add_edge("retrieve_goal_memory", "generate_milestone")
    workflow.add_edge("generate_milestone", "milestone_quick_review")
    workflow.add_conditional_edges(
        "milestone_quick_review",
        route_after_milestone_quick_review,
        {
            "retrieve_and_rerank_milestones": "retrieve_and_rerank_milestones",
            "revise_milestones": "revise_milestones",
        },
    )
    workflow.add_edge("revise_milestones", "milestone_quick_review")
    # Pre-fan-out node fans out (Send) to one worker per milestone.
    workflow.add_conditional_edges(
        "retrieve_and_rerank_milestones",
        route_to_skillpath_workers,
        ["skillpath_worker"],
    )
    workflow.add_edge("skillpath_worker", "finalize_skillpath")
    workflow.add_edge("finalize_skillpath", END)
    return workflow.compile()


def build_quick_review_logic():
    workflow = StateGraph(PlannerState)
    workflow.add_node("milestone_quick_review", milestone_quick_review)
    workflow.add_node("revise_milestones", revise_milestones)
    workflow.add_node("skillpath_worker", skillpath_worker)
    workflow.add_node("finalize_skillpath", finalize_skillpath)

    workflow.add_edge(START, "milestone_quick_review")
    workflow.add_conditional_edges(
        "milestone_quick_review",
        route_after_milestone_quick_review,
        {
            "skillpath_worker": "skillpath_worker",
            "revise_milestones": "revise_milestones",
        },
    )
    workflow.add_edge("revise_milestones", "milestone_quick_review")
    workflow.add_edge("skillpath_worker", "finalize_skillpath")
    workflow.add_edge("finalize_skillpath", END)
    return workflow.compile()
