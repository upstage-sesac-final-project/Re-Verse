"""planner — operation_tuples → execution_plan (LLM 0회).

rule-engine 기반 planner. 의존성 그래프(WRITE_DEPENDENCIES) 와 게임 데이터
직접 접근으로 결정론적 plan 을 생성합니다.

Phase D+E 통합에서 fill_slots 생성 로직 추가. profiler 가 소비.
"""

from __future__ import annotations

import logging

from agent.editor.nodes.planner.fill_schemas import build_fill_slots, get_fill_schema
from agent.editor.nodes.planner.rule_engine import build_execution_plan
from agent.editor.state import AgentState
from agent.utils.game_data_io import get_game_data_dir

logger = logging.getLogger(__name__)


def _collect_fill_slots(plan: list[dict]) -> list[dict]:
    """execution_plan 의 profiling 대상 step 에 대해 fill_slots 생성.

    현재 범위: target_file 이 fill_schemas 레지스트리에 있고
    _needs_profiling=True 인 step (= create step). 나머지는 skip.
    """
    slots: list[dict] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        if not step.get("_needs_profiling"):
            continue
        tf = step.get("target_file") or ""
        if not get_fill_schema(tf):
            continue
        sid = step.get("step_id")
        if sid is None:
            continue
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            continue
        slots.extend(build_fill_slots(sid_int, tf))
    return slots


def planner(state: AgentState) -> dict:
    """planner 노드 진입점 (동기 함수)."""
    import time

    _t0 = time.perf_counter()
    logger.info("─── Planner START ──────────────────────────────────")

    operation_tuples: list[dict] = state.get("operation_tuples", []) or []
    game_id: str = state.get("game_id", "")

    if not operation_tuples:
        logger.warning("[Planner] operation_tuples 비어 있음")
        logger.info("─── Planner END (empty input) ─────────────────────")
        return {"execution_plan": [], "plan_meta": {}, "fill_slots": []}

    if not game_id:
        logger.error("[Planner] game_id 없음")
        logger.info("─── Planner END (no game_id) ──────────────────────")
        return {"execution_plan": [], "plan_meta": {}, "fill_slots": []}

    from pathlib import Path

    data_path = Path(get_game_data_dir(game_id))
    plan, meta, deduped = build_execution_plan(operation_tuples, data_path)

    fill_slots = _collect_fill_slots(plan)

    elapsed = time.perf_counter() - _t0
    logger.info(
        "[Planner] steps=%d operations=%d→%d fill_slots=%d",
        len(plan),
        len(operation_tuples),
        len(deduped),
        len(fill_slots),
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
        "fill_slots": fill_slots,
    }
