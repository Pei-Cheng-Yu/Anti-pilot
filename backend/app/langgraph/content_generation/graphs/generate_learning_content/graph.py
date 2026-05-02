from app.langgraph.content_generation.graphs.generate_learning_content.nodes import (
    build_content_plan,
    content_worker,
    finalize_generated_content,
    route_content_workers,
)
from app.langgraph.content_generation.schema.state import ContentGenerationState
from langgraph.graph import END, START, StateGraph


def build_learning_content_graph():
    workflow = StateGraph(ContentGenerationState)

    workflow.add_node("build_content_plan", build_content_plan)
    workflow.add_node("content_worker", content_worker)
    workflow.add_node("finalize_generated_content", finalize_generated_content)

    workflow.add_edge(START, "build_content_plan")
    workflow.add_conditional_edges(
        "build_content_plan", route_content_workers, ["content_worker", END]
    )
    workflow.add_edge("content_worker", "finalize_generated_content")
    workflow.add_edge("finalize_generated_content", END)

    return workflow.compile()
