"""Full Generation LangGraph 워크플로우.

Phase 2: A→B→C→(skip)→H→I→J (에셋 생성, phase_limit="assets")
Phase 3: A→B→C→D→E→H→I→J (맵 생성 포함, phase_limit="maps")
Phase 4: A→B→C→D→E→F→G→H→I→J (이벤트 포함, phase_limit=None)

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §1, §10
canonical: docs/The_world/workflow_implementation.md
"""

import logging
from typing import Any
from uuid import uuid4

from langchain_community.callbacks.manager import get_openai_callback
from langgraph.graph import END, START, StateGraph

from agent.generation.nodes.asset_generator import asset_generator
from agent.generation.nodes.asset_planner import asset_planner
from agent.generation.nodes.event_compiler_node import event_compiler_node
from agent.generation.nodes.event_planner import event_planner
from agent.generation.nodes.game_designer import game_designer
from agent.generation.nodes.generation_responder import generation_responder
from agent.generation.nodes.generation_validator import generation_validator, route_after_validation
from agent.generation.nodes.integrator import integrator
from agent.generation.nodes.map_designer import map_designer
from agent.generation.nodes.sample_map_selector import sample_map_selector
from agent.generation.nodes.story_planner import story_planner
from agent.generation.nodes.tile_generator import tile_generator
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


def _route_after_asset_generator(state: GenerationState) -> str:
    """C 노드 이후 라우팅: map_source / phase_limit에 따라 분기."""
    phase_limit = state.get("phase_limit")
    if phase_limit == "assets":
        return "skip_to_integrate"
    if state.get("map_source") == "samples":
        return "sample_maps"
    return "map_phase"


def _route_after_tile_generator(state: GenerationState) -> str:
    """E 노드 이후 라우팅: phase_limit에 따라 분기."""
    phase_limit = state.get("phase_limit")
    if phase_limit == "maps":
        return "skip_to_integrate"
    return "story_phase"


def _route_after_sample_map_selector(state: GenerationState) -> str:
    """sample_map_selector 이후 라우팅: phase_limit에 따라 분기.

    phase_limit=None (Phase 4) 에서는 tile_generator 경로와 동일하게
    story_planner → event_planner → event_compiler → integrator 를 거친다.
    phase_limit="assets"/"maps" 에서는 이벤트 생성을 건너뛰고 바로 integrator.
    """
    phase_limit = state.get("phase_limit")
    if phase_limit in ("assets", "maps"):
        return "skip_to_integrate"
    return "story_phase"


def build_generation_graph() -> Any:
    """Full Generation 그래프 조립.

    phase_limit="assets"  → A→B→C→H→I→J
    phase_limit="maps"    → A→B→C→D→E→H→I→J  (샘플 경로: A→B→C→[samples]→H→I→J)
    phase_limit=None      → A→B→C→D→E→F→G→H→I→J  (샘플 경로: A→B→C→[samples]→F→G→H→I→J)
    """
    builder: StateGraph = StateGraph(GenerationState)

    # ── 노드 등록 ──────────────────────────────────────────────────────────
    builder.add_node("game_designer", game_designer)
    builder.add_node("asset_planner", asset_planner)
    builder.add_node("asset_generator", asset_generator)
    builder.add_node("map_designer", map_designer)
    builder.add_node("tile_generator", tile_generator)
    builder.add_node("sample_map_selector", sample_map_selector)
    builder.add_node("story_planner", story_planner)
    builder.add_node("event_planner", event_planner)
    builder.add_node("event_compiler", event_compiler_node)
    builder.add_node("integrator", integrator)
    builder.add_node("validator", generation_validator)
    builder.add_node("responder", generation_responder)

    # ── 엣지 ───────────────────────────────────────────────────────────────
    builder.add_edge(START, "game_designer")
    builder.add_edge("game_designer", "asset_planner")
    builder.add_edge("asset_planner", "asset_generator")

    # C → (assets → H) or (maps/events → D)
    builder.add_conditional_edges(
        "asset_generator",
        _route_after_asset_generator,
        {
            "skip_to_integrate": "integrator",
            "map_phase": "map_designer",
            "sample_maps": "sample_map_selector",
        },
    )

    builder.add_edge("map_designer", "tile_generator")
    # 샘플맵 경로: Phase 4(phase_limit=None)는 event_planner까지 실행, 그 외는 integrator로 skip
    builder.add_conditional_edges(
        "sample_map_selector",
        _route_after_sample_map_selector,
        {
            "skip_to_integrate": "integrator",
            "story_phase": "story_planner",
        },
    )

    # E → (maps → H) or (story → F → G)
    builder.add_conditional_edges(
        "tile_generator",
        _route_after_tile_generator,
        {
            "skip_to_integrate": "integrator",
            "story_phase": "story_planner",
        },
    )

    builder.add_edge("story_planner", "event_planner")
    builder.add_edge("event_planner", "event_compiler")
    builder.add_edge("event_compiler", "integrator")
    builder.add_edge("integrator", "validator")

    # validator → respond / retry_assets / retry_events
    builder.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "respond": "responder",
            "retry_assets": "asset_generator",
            "retry_events": "event_planner",
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
    phase_limit: str | None = None,
    map_source: str | None = "samples",
    options: dict[str, Any] | None = None,
) -> GenerationState:
    """Full Generation 워크플로우 실행.

    Args:
        prompt: 사용자 자연어 입력
        game_id: RPG 프로젝트 ID
        generation_id: 진행률 WebSocket 채널 ID (없으면 자동 생성)
        phase_limit: "assets" → C노드 후 integrator로 skip
        map_source: "samples" 또는 "algorithmic"
        options: 기타 설정 (playtime_minutes 등)

    Returns:
        최종 GenerationState
    """
    gen_id = generation_id or f"gen_{uuid4().hex[:8]}"
    graph = get_generation_graph()

    opts = options or {}
    # 인자로 받은 값을 options에 병합 (우선순위: 인자 < options)
    if phase_limit and "phase_limit" not in opts:
        opts["phase_limit"] = phase_limit
    if map_source and "map_source" not in opts:
        opts["map_source"] = map_source

    initial_state: GenerationState = {
        "user_input": prompt,
        "game_id": game_id,
        "generation_id": gen_id,
        "options": opts,
        "phase_limit": opts.get("phase_limit"),
        "map_source": opts.get("map_source"),
        "retry_count": 0,
        "completed_phases": [],
    }

    logger.info("run_generation_workflow 시작: gen_id=%s game_id=%s", gen_id, game_id)
    with get_openai_callback() as cb:
        final_state: GenerationState = await graph.ainvoke(initial_state)

    # app 레이어 의존 — agent 단독 스크립트·테스트에서는 ImportError 로 건너뜀
    try:
        from app.backend.utils.discord_alerts import send_discord_token_alert
    except ImportError:
        pass
    else:
        await send_discord_token_alert(
            session_id=f"{game_id} (gen={gen_id})",
            prompt_tokens=cb.prompt_tokens,
            completion_tokens=cb.completion_tokens,
            total_cost=cb.total_cost,
            agent_node="Generation Workflow (map/assets)",
        )

    logger.info(
        "run_generation_workflow 완료: is_success=%s phases=%s",
        final_state.get("is_success"),
        final_state.get("completed_phases"),
    )
    return final_state
