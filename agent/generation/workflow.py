import logging

from langgraph.graph import END, StateGraph

from agent.generation.nodes.asset_generator import asset_generator_node
from agent.generation.nodes.asset_planner import asset_planner_node
from agent.generation.nodes.event_compiler_node import event_compiler_node
from agent.generation.nodes.event_planner import event_planner_node
from agent.generation.nodes.game_designer import game_designer_node
from agent.generation.nodes.generation_responder import generation_responder_node
from agent.generation.nodes.generation_validator import generation_validator_node
from agent.generation.nodes.integrator import integrator_node
from agent.generation.nodes.map_designer import map_designer_node
from agent.generation.nodes.tile_generator import tile_generator_node
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


def _route_after_assets(state: GenerationState) -> str:
    """에셋 생성 후 맵 단계로 갈지 결정."""
    if state.get("phase_limit") == "assets":
        return "skip_to_integrate"
    return "map_phase"


def _route_after_validation(state: GenerationState) -> str:
    """검증 결과에 따라 재시도 여부 결정."""
    passed = state.get("validation_passed", False)
    retry_count = state.get("retry_count", 0)

    if passed or retry_count >= 2:
        return "respond"

    # 단순화된 재시도 로직 (나중에 에러 태그별 분기 가능)
    return "retry_events"


def build_generation_graph() -> StateGraph:
    graph = StateGraph(GenerationState)

    # 노드 추가
    graph.add_node("game_designer", game_designer_node)
    graph.add_node("asset_planner", asset_planner_node)
    graph.add_node("asset_generator", asset_generator_node)
    graph.add_node("map_designer", map_designer_node)
    graph.add_node("tile_generator", tile_generator_node)
    graph.add_node("event_planner", event_planner_node)
    graph.add_node("event_compiler", event_compiler_node)
    graph.add_node("integrator", integrator_node)
    graph.add_node("validator", generation_validator_node)
    graph.add_node("responder", generation_responder_node)

    # 시작점
    graph.set_entry_point("game_designer")

    # 순차 연결
    graph.add_edge("game_designer", "asset_planner")
    graph.add_edge("asset_planner", "asset_generator")

    # 조건부 분기: 에셋만 생성할지 맵까지 생성할지
    graph.add_conditional_edges(
        "asset_generator",
        _route_after_assets,
        {"map_phase": "map_designer", "skip_to_integrate": "integrator"},
    )

    graph.add_edge("map_designer", "tile_generator")
    graph.add_edge("tile_generator", "event_planner")
    graph.add_edge("event_planner", "event_compiler")
    graph.add_edge("event_compiler", "integrator")
    graph.add_edge("integrator", "validator")

    # 조건부 분기: 재시도 여부
    graph.add_conditional_edges(
        "validator",
        _route_after_validation,
        {"respond": "responder", "retry_events": "event_planner"},
    )

    graph.add_edge("responder", END)

    return graph


# 컴파일 (체크포인터 없음 — 단발성 생성 워크플로우)
generation_workflow = build_generation_graph().compile()
