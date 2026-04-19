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


def _consume_reference_checks(
    reference_checks: list[dict], operation_tuples: list[dict]
) -> tuple[list[dict], list[str]]:
    """Definition 이 제공한 reference_checks 를 살펴 선행 step 필요성 / 경고 수집.

    Task 5 (minimal) —
    - status="not_found" + (operation 이 create 가 아님) → 경고 수집
      (Definition 이 hold 처리했어야 하는 케이스. 여기선 signal 만 남기고 진행)
    - 그 외 → 변경 없음

    자동 선행 create step 삽입은 차기 sprint (operation_ir 재작성과 병합 필요).

    Returns:
        (원본 operation_tuples 그대로, 경고 문자열 list)
    """
    warnings: list[str] = []
    if not reference_checks or not operation_tuples:
        return operation_tuples, warnings

    for ref in reference_checks:
        if not isinstance(ref, dict):
            continue
        status = ref.get("status")
        if status != "not_found":
            continue
        name = ref.get("name") or "(이름 없음)"
        category = ref.get("category") or "?"
        # operation_tuples 에 해당 대상에 대한 create 가 있으면 괜찮음
        has_create = any(
            isinstance(op, dict)
            and str(op.get("action", "")).lower() in {"create", "생성"}
            for op in operation_tuples
        )
        if not has_create:
            warnings.append(
                f"참조 불일치: {category}/{name} 이(가) DB 에 없는데 operation_tuples 에 create 없음"
            )

    return operation_tuples, warnings


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

    # Task 5: reference_checks 소비 — Definition 이 제공한 참조 사전 검사
    reference_checks = state.get("reference_checks") or []
    operation_tuples, ref_warnings = _consume_reference_checks(
        reference_checks, operation_tuples
    )
    for w in ref_warnings:
        logger.warning("[Planner] %s", w)

    plan, meta, deduped = build_execution_plan(operation_tuples, data_path)

    if ref_warnings:
        meta = dict(meta or {})
        meta.setdefault("reference_warnings", []).extend(ref_warnings)

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
