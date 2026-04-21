"""planner — operation_tuples → execution_plan (LLM 0회).

rule-engine 기반 planner. 의존성 그래프(WRITE_DEPENDENCIES) 와 게임 데이터
직접 접근으로 결정론적 plan 을 생성합니다.

Phase D+E 통합에서 fill_slots 생성 로직 추가. profiler 가 소비.
"""

from __future__ import annotations

import logging

from agent.constants import CATEGORY_TO_FILE as _CATEGORY_TO_FILE_LOWER
from agent.editor.nodes.planner.fill_schemas import build_fill_slots, get_fill_schema
from agent.editor.nodes.planner.rule_engine import build_execution_plan
from agent.editor.state import AgentState
from agent.utils.game_data_io import get_game_data_dir

logger = logging.getLogger(__name__)


# reference_checks entry 의 category 는 capitalized ("Actor") 로 오므로
# constants.CATEGORY_TO_FILE (lowercase keys) 을 capitalize 해 재사용.
_CATEGORY_TO_FILE: dict[str, str] = {
    cat.capitalize(): fn for cat, fn in _CATEGORY_TO_FILE_LOWER.items()
}


def _consume_reference_checks(
    reference_checks: list[dict], operation_tuples: list[dict]
) -> tuple[list[dict], list[str]]:
    """Definition 이 제공한 reference_checks 를 살펴 선행 create step 삽입 / 경고 수집.

    규칙:
    - 이미 같은 (file, name) 에 대한 create 가 ops 에 있으면 noop
    - 같은 (file, name) 에 update/delete/read op 가 있으면 → 선행 create prepend
      (Task 12, "수정 전 대상 필요" 경로)
    - 같은 **파일** 에 다른 op 만 있는 고아 참조 → 삽입 안 함 (중복/오타 가능성)
    - **다른 파일** 에 op 가 있고 이번 참조는 그 op 가 참조하는 엔티티로 보이는 경우
      → 선행 create prepend (Issue A / Task 33, "cross-file 참조" 경로)
      패턴: X.create 가 Y.json 의 엔티티 id 를 필요로 하는데 Y 가 not_found
    - 카테고리 매핑 없음 → 경고만

    Returns:
        (수정된 operation_tuples, 경고 문자열 list)
    """
    warnings: list[str] = []
    if not reference_checks or not operation_tuples:
        return operation_tuples, warnings

    result = list(operation_tuples)
    inserted_creates: set[tuple[str, str]] = set()

    for ref in reference_checks:
        if not isinstance(ref, dict):
            continue
        if ref.get("status") != "not_found":
            continue
        name = (ref.get("name") or "").strip()
        category = (ref.get("category") or "").strip()
        if not name or not category:
            continue

        target_file = _CATEGORY_TO_FILE.get(category)
        if not target_file:
            warnings.append(
                f"참조 불일치: 카테고리 '{category}' 에 대응 파일 매핑 없음 (name={name})"
            )
            continue

        # 이미 같은 (file, name) create 가 있으면 skip
        already_create = any(
            isinstance(op, dict)
            and op.get("op") == "create"
            and op.get("file") == target_file
            and ((op.get("subject") or {}).get("name") or "").strip() == name
            for op in result
        )
        if already_create:
            continue

        # 같은 (file, name) 에 대해 update/delete/read 가 있는지 — 수정 전 대상 필요
        same_target_mutation = any(
            isinstance(op, dict)
            and op.get("op") in {"update", "delete", "read"}
            and op.get("file") == target_file
            and ((op.get("subject") or {}).get("name") or "").strip() == name
            for op in result
        )

        # cross-file 참조: ref.file 과 **다른 파일** 의 op 가 존재 → 참조 대상으로 간주
        cross_file_ref = any(
            isinstance(op, dict) and op.get("file") and op.get("file") != target_file
            for op in result
        )

        # 같은 파일에 업무 대상이 없고 cross-file 참조도 아니면 고아 → skip
        if not same_target_mutation and not cross_file_ref:
            continue

        key = (target_file, name)
        if key in inserted_creates:
            continue
        inserted_creates.add(key)

        new_op = {
            "op": "create",
            "file": target_file,
            "subject": {"name": name},
            "field": None,
            "value": None,
        }
        result.insert(0, new_op)

        reason = (
            "수정/조회 전 대상 생성" if same_target_mutation else "다른 엔티티가 참조 — 선행 생성"
        )
        warnings.append(f"선행 create 자동 삽입: {target_file} '{name}' — {reason}")

    return result, warnings


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
    operation_tuples, ref_warnings = _consume_reference_checks(reference_checks, operation_tuples)
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
