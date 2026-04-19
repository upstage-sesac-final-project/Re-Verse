"""Task 20 — synthesizer 의 effective_success 정책 검증.

- resolve=False (hold) → success=False
- intent 가 terminal → success=False
- changes_log 비었거나 전부 skipped → success=False
- 모든 엔트리 실패 → success=False
- 정상 → validator 의 success 유지
"""

from __future__ import annotations

import pytest

from agent.editor.nodes.synthesizer import _compute_effective_success, synthesizer


class TestComputeEffectiveSuccess:
    def test_hold_returns_false(self):
        state = {"resolve": False, "success": True}
        assert _compute_effective_success(state) is False

    def test_terminal_intent_returns_false(self):
        for intent in (
            "multi_intent",
            "out_of_scope",
            "small_talk",
            "clarification_needed",
        ):
            state = {"intent": intent, "success": True, "changes_log": []}
            assert _compute_effective_success(state) is False, intent

    def test_validator_failure_returns_false(self):
        state = {
            "intent": "object_update",
            "success": False,
            "changes_log": [{"success": True, "action": "update"}],
        }
        assert _compute_effective_success(state) is False

    def test_empty_changes_log_returns_false(self):
        state = {
            "intent": "object_create",
            "success": True,
            "changes_log": [],
        }
        assert _compute_effective_success(state) is False

    def test_all_skipped_returns_false(self):
        state = {
            "intent": "object_update",
            "success": True,
            "changes_log": [
                {"skipped": True, "success": True},
                {"skipped": True, "success": True},
            ],
        }
        assert _compute_effective_success(state) is False

    def test_all_failed_returns_false(self):
        state = {
            "intent": "object_create",
            "success": True,  # validator 가 schema 통과했다 해도
            "changes_log": [
                {"success": False, "action": "create"},
                {"success": False, "action": "create"},
            ],
        }
        assert _compute_effective_success(state) is False

    def test_normal_success_preserved(self):
        state = {
            "intent": "object_update",
            "success": True,
            "changes_log": [{"success": True, "action": "update"}],
        }
        assert _compute_effective_success(state) is True

    def test_partial_success_returns_true(self):
        """일부라도 성공했으면 전체는 True 로 간주."""
        state = {
            "intent": "object_create",
            "success": True,
            "changes_log": [
                {"success": True, "action": "create"},
                {"success": False, "action": "create"},
            ],
        }
        assert _compute_effective_success(state) is True


@pytest.mark.asyncio
async def test_synthesizer_returns_false_on_hold():
    state = {
        "resolve": False,
        "hold_question": "검 A 를 찾을 수 없습니다.",
        "intent": "object_update",
        "success": True,
    }
    result = await synthesizer(state)
    assert result["success"] is False
    assert "검 A" in result["final_response"]


@pytest.mark.asyncio
async def test_synthesizer_returns_false_on_terminal():
    state = {
        "intent": "multi_intent",
        "success": True,
        "final_response": "하나씩 입력해주세요",
        "changes_log": [],
    }
    result = await synthesizer(state)
    assert result["success"] is False


@pytest.mark.asyncio
async def test_synthesizer_returns_true_on_real_create():
    state = {
        "intent": "object_create",
        "success": True,
        "changes_log": [
            {
                "success": True,
                "action": "create",
                "target_file": "Weapons.json",
                "entity_id": 5,
                "data": {"name": "검 A"},
            }
        ],
    }
    result = await synthesizer(state)
    assert result["success"] is True


# ── Router / Definition 이 직접 success=False 세팅하는지 (synthesizer 우회 경로) ──


class TestNodeLevelSuccessOverride:
    """hold / terminal 은 synthesizer 안 거치므로 원 노드에서 success=False 명시해야 함."""

    @pytest.mark.asyncio
    async def test_router_terminal_sets_success_false(self):
        """multi_intent 등 terminal 시 router 자체가 success=False return."""
        from unittest.mock import AsyncMock, patch

        from agent.editor.nodes.router import _ParsedCommand, _RouterOutput, router

        out = _RouterOutput(
            intent="multi_intent",  # type: ignore[arg-type]
            confidence=0.9,
            reasoning="test",
            response="하나씩 입력해주세요",
            parsed_command=_ParsedCommand(),
        )
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as m:
            m.return_value = out
            result = await router({"user_input": "A 하고 B 해", "game_id": "g"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_router_empty_input_sets_success_false(self):
        from agent.editor.nodes.router import router

        result = await router({"user_input": "   ", "game_id": "g"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_definition_hold_sets_success_false(self):
        """Definition wrapper 가 hold 시 success=False + final_response 세팅."""
        from unittest.mock import AsyncMock, patch

        from agent.editor.nodes.definition import definition

        mock_core_return = {
            "target_files": [],
            "modifications": [],
            "extracted_ids": {},
            "params_sufficient": False,
            "message_for_user": "슬라임을 찾을 수 없습니다",
        }
        state = {
            "user_input": "슬라임 HP 올려줘",
            "game_id": "g",
            "parsed_command": {"field": "적", "target": "슬라임", "action": "수정"},
        }
        with patch(
            "agent.editor.nodes.definition._definition_core",
            new=AsyncMock(return_value=mock_core_return),
        ):
            result = await definition(state)

        assert result["success"] is False
        assert result["final_response"]  # hold_question 이 그대로 final_response
