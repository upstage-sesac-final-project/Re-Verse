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
    operation_tuples: list[dict] = state.get("operation_tuples", []) or []
    game_id: str = state.get("game_id", "")

    if not operation_tuples:
        logger.warning("[planner_v2] operation_tuples 비어 있음")
        return {"execution_plan": [], "plan_meta": {}}

    if not game_id:
        logger.error("[planner_v2] game_id 없음")
        return {"execution_plan": [], "plan_meta": {}}

    from pathlib import Path
    data_path = Path(get_game_data_dir(game_id))
    plan, meta, deduped = build_execution_plan(operation_tuples, data_path)

    logger.info(
        "[planner_v2] steps=%d operations=%d→%d",
        len(plan), len(operation_tuples), len(deduped),
    )
    return {
        "execution_plan": plan,
        "plan_meta": meta,
        "operation_tuples": deduped,
    }
