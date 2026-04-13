"""Validator node — schema 검증 + semantic judge + partial retry + final_response.

현재의 synthesizer 역할까지 흡수한다.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.graph.nodes.validator.feedback import build_feedback_text
from agent.graph.nodes.validator.judge import judge_operation
from agent.graph.nodes.validator.responder import build_final_response
from agent.graph.nodes.validator.retry_loop import run_partial_retry
from agent.graph.nodes.validator.schema_check import validate_changed_files

logger = logging.getLogger(__name__)

MAX_RETRY = 2


async def validator(state: dict) -> dict:
    """Validator node entry point."""
    changes_log: list[dict] = state.get("changes_log", [])
    execution_plan: list[dict] = state.get("execution_plan", [])
    operation_tuples: list[dict] = state.get("operation_tuples", [])
    plan_meta: dict = state.get("plan_meta", {})
    game_id: str = state.get("game_id", "")
    user_input: str = state.get("user_input", "")
    resolved_input: str = state.get("resolved_input", "")
    retry_count: int = state.get("retry_count", 0)

    # 1. 실행 중 실패가 있었는지 확인
    exec_failures = [e for e in changes_log if not e.get("success")]
    if exec_failures:
        if retry_count < MAX_RETRY:
            retried = await run_partial_retry(
                exec_failures, execution_plan, game_id, retry_count,
                previous_changes_log=changes_log,
            )
            if retried.get("success"):
                changes_log = retried["changes_log"]
            else:
                return {
                    "success": False,
                    "retry_count": retry_count + 1,
                    "validation_summary": retried.get("summary", "실행 실패"),
                    "final_response": build_final_response(
                        success=False, summary=retried.get("summary", ""), changes_log=changes_log
                    ),
                }

    # 2. Schema 검증
    modified_files = sorted(set(
        f for entry in changes_log
        for f in entry.get("modified_files", [])
        if entry.get("success")
    ))
    schema_results = validate_changed_files(game_id, modified_files)
    schema_failures = [r for r in schema_results if not r["valid"]]

    if schema_failures and retry_count < MAX_RETRY:
        feedback = build_feedback_text(schema_failures=schema_failures)
        retried = await run_partial_retry(
            schema_failures, execution_plan, game_id, retry_count,
            feedback_text=feedback,
            previous_changes_log=changes_log,
        )
        if retried.get("success"):
            schema_results = validate_changed_files(game_id, modified_files)
            schema_failures = [r for r in schema_results if not r["valid"]]

    if schema_failures:
        summary = f"Schema 검증 실패: {len(schema_failures)} 파일"
        return {
            "success": False,
            "retry_count": retry_count + 1,
            "validation_summary": summary,
            "final_response": build_final_response(
                success=False, summary=summary, changes_log=changes_log,
                details=[f["detail"] for f in schema_failures],
            ),
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
                judge_failures.append({
                    "op_idx": op_idx,
                    "operation": op,
                    "reason": judgment.get("reason", ""),
                    "confidence": confidence,
                })

    if judge_failures and retry_count < MAX_RETRY:
        create_ops = [
            f for f in judge_failures
            if _operation_has_create(f["op_idx"], execution_plan, plan_meta)
        ]
        if create_ops:
            feedback = build_feedback_text(judge_failures=judge_failures)
            retried = await run_partial_retry(
                create_ops, execution_plan, game_id, retry_count,
                feedback_text=feedback,
                previous_changes_log=changes_log,
            )
            if retried.get("success"):
                judge_failures = []

    # 4. 최종 판정
    success = len(schema_failures) == 0 and len(judge_failures) == 0
    summary = "성공" if success else f"의미 검증 실패: {len(judge_failures)} 건"
    judge_reasons = [f["reason"] for f in judge_failures]

    return {
        "success": success,
        "retry_count": retry_count + (0 if success else 1),
        "validation_summary": summary,
        "final_response": build_final_response(
            success=success,
            summary=summary,
            changes_log=changes_log,
            details=judge_reasons,
        ),
    }


def _operation_has_create(
    op_idx: int, plan: list[dict], plan_meta: dict
) -> bool:
    step_ids = plan_meta.get(op_idx, plan_meta.get(str(op_idx), []))
    return any(
        s.get("action_type") == "create"
        for s in plan
        if s.get("step_id") in step_ids
    )
