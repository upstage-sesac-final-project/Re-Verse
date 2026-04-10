"""Partial retry loop — 실패한 step 만 profiler 재호출 후 재실행."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run_partial_retry(
    failures: list[dict[str, Any]],
    execution_plan: list[dict],
    game_id: str,
    retry_count: int,
    feedback_text: str | None = None,
) -> dict[str, Any]:
    """실패한 step 을 profiler → executor 로 부분 재실행.

    Returns {"success": bool, "changes_log": list, "summary": str}
    """
    from new_agent.executor import execute_one
    from new_agent.nodes.profiler import profile_one

    patched_log: list[dict] = []
    all_ok = True

    for failure in failures:
        # step_id 또는 operation 기반으로 대상 step 추출
        target_steps = _find_target_steps(failure, execution_plan)

        for step in target_steps:
            if step.get("action_type") != "create":
                continue  # create 만 profiler 재호출 의미 있음

            # profiler 재호출
            enriched = await profile_one(
                step, game_id=game_id, feedback=feedback_text
            )

            # executor 재실행
            result = await execute_one(game_id, enriched)
            patched_log.append(result)

            if not result.get("success"):
                all_ok = False
                logger.warning(
                    "[retry] step=%s 재실행 실패: %s",
                    step.get("step_id"), result.get("error"),
                )

    return {
        "success": all_ok,
        "changes_log": patched_log,
        "summary": "부분 재시도 성공" if all_ok else "부분 재시도 실패",
    }


def _find_target_steps(
    failure: dict, plan: list[dict]
) -> list[dict]:
    """failure 정보에서 재시도 대상 step 을 추출."""
    # step_id 직접 지정
    step_id = failure.get("step_id")
    if step_id is not None:
        return [s for s in plan if s.get("step_id") == step_id]

    # operation 기반 (judge 실패)
    op_idx = failure.get("op_idx")
    if op_idx is not None:
        # plan_meta 없이 fallback: plan 에서 _op_action 으로 매칭
        return [
            s for s in plan
            if s.get("action_type") == "create"
        ]

    return []
