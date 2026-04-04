from app.langgraph.planner.graphs.evaluate.node import (
    distribute_skillpath_review,
    merge_revised_skillpaths,
    skillpath_review_worker,
)
from app.langgraph.planner.schema.state import PlannerState
from langgraph.graph import END, START, StateGraph


def build_evaluate_graph():
    workflow = StateGraph(PlannerState)
    workflow.add_node("skillpath_review_worker", skillpath_review_worker)
    workflow.add_node("merge_revised_skillpaths", merge_revised_skillpaths)

    workflow.add_conditional_edges(
        START,
        distribute_skillpath_review,
        {"skillpath_review_worker": "skillpath_review_worker"},
    )
    workflow.add_edge("skillpath_review_worker", "merge_revised_skillpaths")
    workflow.add_edge("merge_revised_skillpaths", END)
    return workflow.compile()
