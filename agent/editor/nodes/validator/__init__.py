"""Validator node — schema 검증 + 룰 기반 soundness 경고 + partial retry.

Phase G 재설계:
- 유저 쿼리와의 비교(`judge_operation` LLM 호출) 제거. 판단 정확도가 낮고
  retry 를 유발해 LLM 낭비. 대신 `soundness_warnings` (룰 기반 경고 리스트)
  를 반환하고 synthesizer 가 포장.
- `success` 는 이제 schema 검증 결과에만 좌우된다.
- `judge_feedback` 은 호환을 위해 빈 문자열로 유지 (synthesizer 가 여전히 읽음).

검증만 수행한다. 사용자 응답 생성은 synthesizer 가 담당.
"""

from __future__ import annotations

import logging

from agent.constants import MAX_RETRY
from agent.editor.nodes.validator.feedback import build_feedback_text
from agent.editor.nodes.validator.retry_loop import run_partial_retry
from agent.editor.nodes.validator.schema_check import validate_changed_files

logger = logging.getLogger(__name__)


def _collect_soundness_warnings(
    changes_log: list[dict],
    operation_tuples: list[dict],
) -> list[str]:
    """룰 기반 경고 수집. Phase G 1차 범위는 최소 룰만.

    차기 sprint 에 추가 예정 (YB.md 7-3):
    - 가격 vs 공격력 단조성 (Weapons/Armors)
    - 이벤트 code=0 종결 검증
    - 참조 무결성 (126 커맨드 itemId 존재 여부)
    """
    warnings: list[str] = []

    # 룰 1: 성공 엔트리에 entity_id 가 누락되면 executor 가 결과를 제대로
    # 보고 안 했을 가능성. 경고 표시.
    for entry in changes_log:
        if not entry.get("success"):
            continue
        if entry.get("skipped"):
            continue
        action = (entry.get("action") or "").lower()
        if action in ("create", "update", "update_actor") and entry.get("entity_id") is None:
            tf = entry.get("target_file", "?")
            warnings.append(
                f"{tf} {action}: entity_id 가 비어 있습니다 — 실행은 보고됐으나 id 추적이 안 됩니다."
            )

    # 룰 2: execution_plan 은 있었는데 changes_log 가 전부 skipped 면 아무것도 안 한 상태
    if operation_tuples and changes_log and all(e.get("skipped") for e in changes_log):
        warnings.append("실행 계획이 있었지만 전부 skip 되었습니다 — 의도와 다를 수 있습니다.")

    return warnings


async def validator(state: dict) -> dict:
    """Validator node entry point."""
    import time

    _t0 = time.perf_counter()
    logger.info("─── Validator START ────────────────────────────────")

    changes_log: list[dict] = state.get("changes_log", [])
    execution_plan: list[dict] = state.get("execution_plan", [])
    operation_tuples: list[dict] = state.get("operation_tuples", [])
    game_id: str = state.get("game_id", "")
    retry_count: int = state.get("retry_count", 0)
    # Phase G: user_input / resolved_input / plan_meta 는 judge_operation 에만
    # 쓰던 변수. judge 제거와 함께 이 함수에서는 더 이상 참조 안 함.

    logger.info(
        "[Validator] entries=%d retry=%d ops=%d",
        len(changes_log),
        retry_count,
        len(operation_tuples),
    )

    # 1. 실행 중 실패가 있었는지 확인
    exec_failures = [e for e in changes_log if not e.get("success")]
    if exec_failures:
        if retry_count < MAX_RETRY:
            retried = await run_partial_retry(
                exec_failures,
                execution_plan,
                game_id,
                retry_count,
                previous_changes_log=changes_log,
            )
            if retried.get("success"):
                changes_log = retried["changes_log"]
            else:
                elapsed = time.perf_counter() - _t0
                logger.info(
                    "─── Validator END (elapsed=%.2fs, result=FAIL, reason=exec_retry_failed) ──",
                    elapsed,
                )
                return {
                    "success": False,
                    "retry_count": retry_count + 1,
                    "validation_summary": retried.get("summary", "실행 실패"),
                }

    # 2. Schema 검증
    modified_files = sorted(
        set(
            f
            for entry in changes_log
            for f in entry.get("modified_files", [])
            if entry.get("success")
        )
    )
    schema_results = validate_changed_files(game_id, modified_files)
    schema_failures = [r for r in schema_results if not r["valid"]]

    if schema_failures and retry_count < MAX_RETRY:
        feedback = build_feedback_text(schema_failures=schema_failures)
        retried = await run_partial_retry(
            schema_failures,
            execution_plan,
            game_id,
            retry_count,
            feedback_text=feedback,
            previous_changes_log=changes_log,
        )
        if retried.get("success"):
            schema_results = validate_changed_files(game_id, modified_files)
            schema_failures = [r for r in schema_results if not r["valid"]]

    if schema_failures:
        summary = f"Schema 검증 실패: {len(schema_failures)} 파일"
        elapsed = time.perf_counter() - _t0
        logger.info(
            "─── Validator END (elapsed=%.2fs, result=FAIL, reason=schema) ─────",
            elapsed,
        )
        return {
            "success": False,
            "retry_count": retry_count + 1,
            "validation_summary": summary,
            "validation_details": [f["detail"] for f in schema_failures],
        }

    # 3. Phase G: judge_operation LLM 호출 제거. 대신 룰 기반 soundness 경고.
    soundness_warnings = _collect_soundness_warnings(changes_log, operation_tuples)
    if soundness_warnings:
        logger.info(
            "[Validator] soundness_warnings %d건 — synthesizer 가 포장", len(soundness_warnings)
        )

    # 4. 최종 판정 — schema 만 성공 기준. 경고는 차단 아님.
    success = len(schema_failures) == 0
    summary = (
        "성공"
        if not soundness_warnings
        else f"성공 (참고사항 {len(soundness_warnings)}건)"
    )

    elapsed = time.perf_counter() - _t0
    logger.info(
        "─── Validator END (elapsed=%.2fs, result=%s, schema_fail=%d, warnings=%d) ──",
        elapsed,
        "OK" if success else "FAIL",
        len(schema_failures),
        len(soundness_warnings),
    )
    # judge_feedback 은 호환 유지를 위해 빈 문자열로 반환 (consumer 가 존재 여부만 체크)
    return {
        "success": success,
        "retry_count": retry_count + (0 if success else 1),
        "validation_summary": summary,
        "judge_feedback": "",
        "soundness_warnings": soundness_warnings,
    }
