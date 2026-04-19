"""Partial retry loop — 실패한 step 재실행 + judge 실패는 feedback 만.

- exec 실패 (success=False): profiler 재호출 → execute_one 재실행
- judge 실패 (의미 불일치): 재실행 없이 feedback 만 반환 (중복 생성 방지)

중요: create step 은 retry 시 새 엔트리를 만들지 않고,
이전에 만든 엔트리를 update 하는 방식으로 수정한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# retry 에서 이미 처리한 step_id 를 추적하여 중복 실행 방지
_retried_step_ids: set[int] = set()


async def run_partial_retry(
    failures: list[dict[str, Any]],
    execution_plan: list[dict],
    game_id: str,
    retry_count: int,
    feedback_text: str | None = None,
    previous_changes_log: list[dict] | None = None,
) -> dict[str, Any]:
    """실패한 step 을 profiler → executor 로 부분 재실행.

    create step 은 이전 실행에서 만든 entity_id 가 있으면
    새로 만들지 않고 해당 엔트리를 update 한다.

    Returns {"success": bool, "changes_log": list, "summary": str}
    """
    from agent.editor.nodes.executor_v2 import execute_one
    from agent.editor.nodes.profiler import profile_one

    patched_log: list[dict] = []
    all_ok = True
    retried_any = False
    prev_log = previous_changes_log or []

    for failure in failures:
        target_steps = _find_target_steps(failure, execution_plan)

        for step in target_steps:
            sid = step.get("step_id")

            if step.get("action_type") != "create":
                continue

            # 중복 실행 방지
            if sid in _retried_step_ids:
                logger.info("[retry] step=%s 이미 재시도됨, skip", sid)
                continue
            _retried_step_ids.add(sid)

            # 이전 실행에서 이미 만든 entity_id 가 있는지 확인
            prev_entity_id = _find_prev_entity_id(sid, prev_log)

            try:
                # profiler 재호출
                enriched = await profile_one(
                    step, game_id=game_id, feedback=feedback_text
                )

                if prev_entity_id is not None:
                    # 이전에 만든 엔트리를 update 하는 방식으로 전환
                    logger.info(
                        "[retry] step=%s create→update 전환 (entity_id=%d)",
                        sid,
                        prev_entity_id,
                    )
                    enriched = dict(enriched)
                    enriched["action_type"] = "update"
                    ti = dict(enriched.get("target_info") or {})
                    ti["id"] = prev_entity_id
                    # target_info 전체를 updates 로 변환
                    updates = {k: v for k, v in ti.items() if k not in ("id", "name")}
                    ti["updates"] = updates
                    enriched["target_info"] = ti

                retried_any = True
                result = await execute_one(game_id, enriched)
                patched_log.append(result)

                if not result.get("success"):
                    all_ok = False
                    logger.warning(
                        "[retry] step=%s 재실행 실패: %s",
                        step.get("step_id"),
                        result.get("error"),
                    )
            except asyncio.CancelledError:
                # 상위 wait_for 의 timeout 으로 인한 cancel — traceback 한 번만 남기고
                # 재-raise 해서 wait_for 가 TimeoutError 로 일관되게 잡도록 함.
                logger.warning(
                    "[retry] step=%s cancelled (상위 timeout 추정) — 루프 중단",
                    sid,
                )
                raise
            except Exception as e:
                # LLM 장애 / 네트워크 등 일반 예외 — 해당 step 만 실패로 기록하고 루프 지속.
                logger.error(
                    "[retry] step=%s 재실행 예외: %s (%s) — 다른 step 계속 시도",
                    sid,
                    type(e).__name__,
                    e,
                )
                all_ok = False
                retried_any = True
                patched_log.append(
                    {
                        "step_id": sid,
                        "success": False,
                        "error": f"retry 예외: {type(e).__name__}: {e}",
                    }
                )

    # 재시도 대상이 하나도 없으면 실패로 반환 (원본 실패가 삼켜지지 않게)
    if not retried_any:
        return {
            "success": False,
            "changes_log": [],
            "summary": "재시도 대상 없음 — 실행 실패 유지",
        }

    return {
        "success": all_ok,
        "changes_log": patched_log,
        "summary": "부분 재시도 성공" if all_ok else "부분 재시도 실패",
    }


def _find_prev_entity_id(step_id: int | None, changes_log: list[dict]) -> int | None:
    """이전 changes_log 에서 해당 step 이 만든 entity_id 를 찾는다."""
    if step_id is None:
        return None
    for entry in reversed(changes_log):
        if entry.get("step_id") == step_id and entry.get("entity_id") is not None:
            return entry["entity_id"]
    return None


def _find_target_steps(failure: dict, plan: list[dict]) -> list[dict]:
    """failure 정보에서 재시도 대상 step 을 추출."""
    # step_id 직접 지정
    step_id = failure.get("step_id")
    if step_id is not None:
        return [s for s in plan if s.get("step_id") == step_id]

    # operation 기반 (judge 실패) — 해당 op 의 create step 만
    op_idx = failure.get("op_idx")
    if op_idx is not None:
        return [
            s for s in plan if s.get("action_type") == "create" and s.get("_op_action") == "create"
        ]

    return []


def reset_retry_state() -> None:
    """대화 턴 시작 시 호출하여 retry 추적 상태를 초기화."""
    _retried_step_ids.clear()
