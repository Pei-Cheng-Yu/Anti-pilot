from app.langgraph.planner.graphs.evaluate.node import (
    distribute_revised_review,
    distribute_skillpath_review,
    distribute_skillpath_revise,
    merge_revised_skillpaths,
    reviewed_fan_in,
    revised_fan_in,
    skillpath_review_worker,
    skillpath_revise_worker,
)
from app.langgraph.planner.schema.state import PlannerState
from langgraph.graph import END, START, StateGraph


def build_evaluate_graph():
    workflow = StateGraph(PlannerState)
    workflow.add_node("skillpath_review_worker", skillpath_review_worker)
    workflow.add_node("reviewed_fan_in", reviewed_fan_in)
    workflow.add_node("skillpath_revise_worker", skillpath_revise_worker)
    workflow.add_node("revised_fan_in", revised_fan_in)
    workflow.add_node("merge_revised_skillpaths", merge_revised_skillpaths)

    workflow.add_conditional_edges(
        START,
        distribute_skillpath_review,
        {"skillpath_review_worker": "skillpath_review_worker"},
    )
    workflow.add_edge("skillpath_review_worker", "reviewed_fan_in")
    workflow.add_conditional_edges(
        "reviewed_fan_in",
        distribute_skillpath_revise,
        {
            "skillpath_revise_worker": "skillpath_revise_worker",
            "__end__": END,
            "merge_revised_skillpaths": "merge_revised_skillpaths",
        },
    )
    workflow.add_edge("skillpath_revise_worker", "revised_fan_in")
    workflow.add_conditional_edges(
        "revised_fan_in",
        distribute_revised_review,
        {"skillpath_review_worker": "skillpath_review_worker", "__end__": END},
    )
    workflow.add_edge("merge_revised_skillpaths", END)
    return workflow.compile()
