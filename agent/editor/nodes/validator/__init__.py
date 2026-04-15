"""Validator node — schema 검증 + semantic judge + partial retry.

검증만 수행한다. 사용자 응답 생성은 synthesizer 가 담당.
"""

from __future__ import annotations

import logging

from agent.constants import MAX_RETRY
from agent.editor.nodes.validator.feedback import build_feedback_text
from agent.editor.nodes.validator.judge import judge_operation
from agent.editor.nodes.validator.retry_loop import run_partial_retry
from agent.editor.nodes.validator.schema_check import validate_changed_files

logger = logging.getLogger(__name__)


async def validator(state: dict) -> dict:
    """Validator node entry point."""
    import time

    _t0 = time.perf_counter()
    logger.info("─── Validator START ────────────────────────────────")

    changes_log: list[dict] = state.get("changes_log", [])
    execution_plan: list[dict] = state.get("execution_plan", [])
    operation_tuples: list[dict] = state.get("operation_tuples", [])
    plan_meta: dict = state.get("plan_meta", {})
    game_id: str = state.get("game_id", "")
    user_input: str = state.get("user_input", "")
    resolved_input: str = state.get("resolved_input", "")
    retry_count: int = state.get("retry_count", 0)

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

    # 3. Semantic judge (operation 단위)
    judge_failures: list[dict] = []
    for op_idx, op in enumerate(operation_tuples):
        op_step_ids = plan_meta.get(op_idx, plan_meta.get(str(op_idx), []))
        op_results = [e for e in changes_log if e.get("step_id") in op_step_ids]

        judgment = await judge_operation(
            user_input=user_input,
            resolved_input=resolved_input,
            operation=op,
            step_results=op_results,
            game_id=game_id,
        )

        if not judgment.get("match"):
            confidence = judgment.get("confidence", 0.0)
            if confidence >= 0.5:
                judge_failures.append(
                    {
                        "op_idx": op_idx,
                        "operation": op,
                        "reason": judgment.get("reason", ""),
                        "confidence": confidence,
                    }
                )

    # judge 실패는 재실행하지 않고 feedback 만 남긴다 (중복 생성 방지).
    judge_feedback = ""
    if judge_failures:
        from agent.editor.nodes.validator.retry_loop import build_judge_feedback

        judge_feedback = build_judge_feedback(judge_failures)
        logger.info(
            "[Validator] judge 실패 %d건 — feedback만 첨부 (재실행 안 함)", len(judge_failures)
        )

    # 4. 최종 판정 — judge 실패는 warning 으로 남기되 성공 처리
    success = len(schema_failures) == 0
    summary = "성공" if not judge_failures else f"성공 (의미 검증 참고사항 {len(judge_failures)}건)"

    elapsed = time.perf_counter() - _t0
    logger.info(
        "─── Validator END (elapsed=%.2fs, result=%s, schema_fail=%d, judge_fail=%d) ──",
        elapsed,
        "OK" if success else "FAIL",
        len(schema_failures),
        len(judge_failures),
    )
    return {
        "success": success,
        "retry_count": retry_count + (0 if success else 1),
        "validation_summary": summary,
        "judge_feedback": judge_feedback,
    }
