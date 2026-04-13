"""planner_v2 — operation_tuples → execution_plan (LLM 0회).

new_agent 의 rule-engine 기반 planner 를 OG 에 이식.
의존성 그래프(WRITE_DEPENDENCIES)와 게임 데이터 직접 접근으로 결정론적 plan 생성.
"""

from __future__ import annotations

import logging

from agent.graph.nodes.planner_v2.rule_engine import build_execution_plan
from agent.graph.state import AgentState
from agent.utils.game_data_io import get_game_data_dir

logger = logging.getLogger(__name__)


def planner_v2(state: AgentState) -> dict:
    """planner_v2 노드 진입점 (동기 함수)."""
    import time

    _t0 = time.perf_counter()
    logger.info("─── Planner START ──────────────────────────────────")

    operation_tuples: list[dict] = state.get("operation_tuples", []) or []
    game_id: str = state.get("game_id", "")

    if not operation_tuples:
        logger.warning("[Planner] operation_tuples 비어 있음")
        logger.info("─── Planner END (empty input) ─────────────────────")
        return {"execution_plan": [], "plan_meta": {}}

    if not game_id:
        logger.error("[Planner] game_id 없음")
        logger.info("─── Planner END (no game_id) ──────────────────────")
        return {"execution_plan": [], "plan_meta": {}}

    from pathlib import Path

    data_path = Path(get_game_data_dir(game_id))
    plan, meta, deduped = build_execution_plan(operation_tuples, data_path)

    elapsed = time.perf_counter() - _t0
    logger.info(
        "[Planner] steps=%d operations=%d→%d",
        len(plan),
        len(operation_tuples),
        len(deduped),
    )
    logger.info(
        "─── Planner END (elapsed=%.2fs, steps=%d) ─────────────",
        elapsed,
        len(plan),
    )
    return {
        "execution_plan": plan,
        "plan_meta": meta,
        "operation_tuples": deduped,
    }
