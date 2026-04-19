"""sprint α — run_partial_retry 의 CancelledError / 일반 Exception 처리 검증.

이전엔 profile_one / execute_one 의 예외가 상위로 그대로 전파되어 LangSmith trace
에 CancelledError traceback 이 그대로 남았다. 이제:
- CancelledError: 루프 중단하고 상위로 re-raise (wait_for 가 TimeoutError 로 일관 처리)
- 일반 Exception: 해당 step 만 실패로 기록하고 다음 step 은 계속 시도
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.validator.retry_loop import (
    reset_retry_state,
    run_partial_retry,
)


def _plan(sid: int = 1) -> list[dict]:
    return [
        {
            "step_id": sid,
            "action_type": "create",
            "target_file": "Weapons.json",
            "target_info": {"name": "검 A"},
            "_op_action": "create",
        }
    ]


@pytest.mark.asyncio
async def test_cancelled_error_is_re_raised(monkeypatch):
    """상위 wait_for timeout 시 CancelledError 가 재전파되어야 한다."""
    reset_retry_state()

    async def _cancel(*a, **k):
        raise asyncio.CancelledError()

    with patch("agent.editor.nodes.profiler.profile_one", new=_cancel):
        with pytest.raises(asyncio.CancelledError):
            await run_partial_retry(
                failures=[{"step_id": 1}],
                execution_plan=_plan(1),
                game_id="g",
                retry_count=0,
            )


@pytest.mark.asyncio
async def test_general_exception_graceful_continue(monkeypatch):
    """일반 Exception 은 step 실패로 기록하고 다음 step 계속."""
    reset_retry_state()

    plan = [
        {"step_id": 1, "action_type": "create", "target_file": "Weapons.json",
         "target_info": {"name": "검 A"}, "_op_action": "create"},
        {"step_id": 2, "action_type": "create", "target_file": "Armors.json",
         "target_info": {"name": "갑옷 B"}, "_op_action": "create"},
    ]

    call_count = {"n": 0}

    async def _profile(step, game_id="", feedback=None):
        call_count["n"] += 1
        if step["step_id"] == 1:
            raise RuntimeError("LLM API 500")
        # step 2 는 정상
        return {**step, "target_info": {"name": "갑옷 B"}}

    async def _exec(game_id, step):
        return {
            "step_id": step["step_id"],
            "success": True,
            "action": "create",
            "entity_id": 99,
        }

    with (
        patch("agent.editor.nodes.profiler.profile_one", new=_profile),
        patch("agent.editor.nodes.executor_v2.execute_one", new=_exec),
    ):
        result = await run_partial_retry(
            failures=[{"step_id": 1}, {"step_id": 2}],
            execution_plan=plan,
            game_id="g",
            retry_count=0,
        )

    # step 1 은 예외로 실패, step 2 는 성공
    assert call_count["n"] == 2
    assert result["success"] is False
    assert len(result["changes_log"]) == 2
    # 실패 엔트리가 있는지
    errors = [e for e in result["changes_log"] if not e.get("success")]
    assert errors
    assert "retry 예외" in errors[0].get("error", "")


@pytest.mark.asyncio
async def test_no_retry_targets_returns_failure():
    reset_retry_state()
    result = await run_partial_retry(
        failures=[],
        execution_plan=[],
        game_id="g",
        retry_count=0,
    )
    assert result["success"] is False
    assert result["summary"]


@pytest.mark.asyncio
async def test_all_success_ok_path():
    reset_retry_state()
    plan = _plan(1)

    async def _profile(step, game_id="", feedback=None):
        return {**step, "target_info": {"name": "검 A"}}

    async def _exec(game_id, step):
        return {
            "step_id": step["step_id"],
            "success": True,
            "action": "create",
            "entity_id": 5,
        }

    with (
        patch("agent.editor.nodes.profiler.profile_one", new=_profile),
        patch("agent.editor.nodes.executor_v2.execute_one", new=_exec),
    ):
        result = await run_partial_retry(
            failures=[{"step_id": 1}],
            execution_plan=plan,
            game_id="g",
            retry_count=0,
        )
    assert result["success"] is True
    assert result["changes_log"][0]["entity_id"] == 5
