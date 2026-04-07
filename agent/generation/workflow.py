"""The World 생성 파이프라인 StateGraph."""

from langgraph.graph import END, START, StateGraph

from agent.generation.nodes.architect import architect
from agent.generation.nodes.asset_planner import asset_planner
from agent.generation.nodes.builder import builder_node
from agent.generation.nodes.game_designer import game_designer
from agent.generation.nodes.generation_validator import generation_validator
from agent.generation.routing import route_after_validator
from agent.generation.state import GenerationState


def build_generation_graph() -> StateGraph:
    builder = StateGraph(GenerationState)

    builder.add_node("game_designer", game_designer)
    builder.add_node("asset_planner", asset_planner)
    builder.add_node("architect", architect)
    builder.add_node("builder", builder_node)
    builder.add_node("validator", generation_validator)

    builder.add_edge(START, "game_designer")
    builder.add_edge("game_designer", "asset_planner")
    builder.add_edge("asset_planner", "architect")
    builder.add_edge("architect", "builder")
    builder.add_edge("builder", "validator")

    builder.add_conditional_edges(
        "validator",
        route_after_validator,
        {"__end__": END, "architect": "architect"},
    )

    return builder.compile()


generation_graph = build_generation_graph()
