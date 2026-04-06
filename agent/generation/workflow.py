"""Full Generation LangGraph 워크플로우.

Phase 2: A→B→C→H→I→J (에셋 생성 + 검증)
Phase 3+: D→E → Phase 4: F→G 추가 예정

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §1, §10
canonical: docs/The_world/workflow_implementation.md
"""

import logging
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agent.generation.nodes.asset_generator import asset_generator
from agent.generation.nodes.asset_planner import asset_planner
from agent.generation.nodes.game_designer import game_designer
from agent.generation.nodes.generation_responder import generation_responder
from agent.generation.nodes.generation_validator import generation_validator, route_after_validation
from agent.generation.nodes.integrator import integrator
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


def build_generation_graph() -> Any:
    """Phase 2 Full Generation 그래프 조립.

    흐름 (phase_limit="assets"):
        START → game_designer → asset_planner → asset_generator
            → integrator → validator → responder → END
    """
    builder: StateGraph = StateGraph(GenerationState)

    # ── 노드 등록 ──────────────────────────────────────────────────────────
    builder.add_node("game_designer", game_designer)
    builder.add_node("asset_planner", asset_planner)
    builder.add_node("asset_generator", asset_generator)
    builder.add_node("integrator", integrator)
    builder.add_node("validator", generation_validator)
    builder.add_node("responder", generation_responder)

    # ── 엣지 ───────────────────────────────────────────────────────────────
    builder.add_edge(START, "game_designer")
    builder.add_edge("game_designer", "asset_planner")
    builder.add_edge("asset_planner", "asset_generator")
    builder.add_edge("asset_generator", "integrator")
    builder.add_edge("integrator", "validator")

    # validator → respond / retry_assets
    builder.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "respond": "responder",
            "retry_assets": "asset_generator",  # C 노드부터 재시도
        },
    )

    builder.add_edge("responder", END)

    return builder.compile()


# 싱글톤 그래프 인스턴스
_graph = None


def get_generation_graph() -> Any:
    """싱글톤 컴파일 그래프 반환."""
    global _graph
    if _graph is None:
        _graph = build_generation_graph()
    return _graph


async def run_generation_workflow(
    prompt: str,
    game_id: str,
    generation_id: str | None = None,
    phase_limit: str = "assets",
) -> GenerationState:
    """Full Generation 워크플로우 실행.

    Args:
        prompt: 사용자 자연어 입력
        game_id: RPG 프로젝트 ID
        generation_id: 진행률 WebSocket 채널 ID (없으면 자동 생성)
        phase_limit: "assets" → C노드 후 integrator로 skip

    Returns:
        최종 GenerationState
    """
    gen_id = generation_id or f"gen_{uuid4().hex[:8]}"
    graph = get_generation_graph()

    initial_state: GenerationState = {
        "user_input": prompt,
        "game_id": game_id,
        "generation_id": gen_id,
        "phase_limit": phase_limit,
        "retry_count": 0,
        "completed_phases": [],
    }

    logger.info("run_generation_workflow 시작: gen_id=%s game_id=%s", gen_id, game_id)
    final_state: GenerationState = await graph.ainvoke(initial_state)
    logger.info(
        "run_generation_workflow 완료: is_success=%s phases=%s",
        final_state.get("is_success"),
        final_state.get("completed_phases"),
    )
    return final_state
