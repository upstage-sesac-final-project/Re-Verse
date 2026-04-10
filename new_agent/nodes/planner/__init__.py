"""Planner node — 의존성 그래프 워크 + 실측 → execution_plan 생성.

LLM 0회. 순수 Python 결정론.
"""

from __future__ import annotations

import logging

from app.backend.core.game_paths import get_game_data_path
from new_agent.nodes.planner.rule_engine import build_execution_plan

logger = logging.getLogger(__name__)


def planner(state: dict) -> dict:
    """Planner node entry point (동기 함수)."""
    operation_tuples: list[dict] = state.get("operation_tuples", [])
    game_id: str = state.get("game_id", "")

    if not operation_tuples:
        logger.warning("[planner] operation_tuples 비어 있음")
        return {"execution_plan": [], "plan_meta": {}}

    if not game_id:
        logger.error("[planner] game_id 없음")
        return {"execution_plan": [], "plan_meta": {}}

    data_path = get_game_data_path(game_id)
    plan, meta = build_execution_plan(operation_tuples, data_path)

    logger.info("[planner] steps=%d operations=%d", len(plan), len(operation_tuples))
    return {"execution_plan": plan, "plan_meta": meta}
