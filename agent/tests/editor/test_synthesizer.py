"""Synthesizer 노드 단위 테스트.

실행 방법:
    # 단위 테스트만 (LLM 호출 없음, 빠름)
    uv run pytest agent/tests/test_synthesizer.py -v

    # 실제 LLM 호출 포함 (API 키 필요)
    uv run pytest agent/tests/test_synthesizer.py -v -m integration -s
"""

from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.synthesizer import synthesizer
from agent.editor.prompts.synthesizer_prompt import build_prompt
from agent.editor.state import AgentState

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _state(
    intent: str = "object_update",
    user_input: str = "슬라임 HP를 200으로 올려줘",
    passed: bool = True,
    errors: list | None = None,
    current: dict | None = None,
    modified: dict | None = None,
    changes: list | None = None,
) -> AgentState:
    s: AgentState = {
        "user_input": user_input,
        "game_id": "test_game",
        "intent": intent,  # type: ignore[typeddict-item]
        "success": passed,
        "validation_result": {
            "passed": passed,
            "errors": errors or [],
            "error_count": len(errors or []),
        },
        "validation_results": [{"errors": errors or [], "success": passed}] if errors else [],
    }
    if current:
        s["current_game_state"] = current
    if modified:
        s["modified_game_state"] = modified
    if changes:
        s["changes_log"] = changes
    return s


# ── 프롬프트 빌더 테스트 ───────────────────────────────────────────────────────


class TestBuildPrompt:
    def test_returns_two_messages(self):
        msgs = build_prompt(_state())
        assert len(msgs) == 2

    def test_user_input_in_human_message(self):
        msgs = build_prompt(_state(user_input="슬라임 HP를 200으로 올려줘"))
        assert "슬라임 HP를 200으로 올려줘" in msgs[1].content

    def test_intent_in_human_message(self):
        msgs = build_prompt(_state(intent="object_create"))
        assert "object_create" in msgs[1].content

    def test_success_status_in_human_message(self):
        msgs = build_prompt(_state(passed=True))
        assert "성공" in msgs[1].content

    def test_failure_status_and_errors_in_human_message(self):
        msgs = build_prompt(_state(passed=False, errors=["슬라임킹을 찾을 수 없음"]))
        assert "실패" in msgs[1].content
        assert "슬라임킹" in msgs[1].content

    def test_modified_state_included(self):
        modified = {"Enemies": [{"id": 1, "name": "슬라임", "params": {"mhp": 200}}]}
        msgs = build_prompt(_state(modified=modified))
        assert "슬라임" in msgs[1].content

    def test_changes_log_included(self):
        changes = [{"file": "Enemies.json", "field": "mhp", "before": 100, "after": 200}]
        msgs = build_prompt(_state(changes=changes))
        assert "Enemies.json" in msgs[1].content

    def test_empty_state_does_not_raise(self):
        msgs = build_prompt({"user_input": "테스트", "game_id": "g"})  # type: ignore[typeddict-item]
        assert len(msgs) == 2


# ── Synthesizer 노드 단위 테스트 (LLM mock) ───────────────────────────────────


@pytest.mark.skip(
    reason="synthesizer가 LLM 대신 결정론 템플릿을 사용하도록 변경됨 — 테스트 재작성 필요"
)
class TestSynthesizer:
    @pytest.mark.asyncio
    async def test_returns_final_response(self):
        with patch("agent.editor.nodes.synthesizer.invoke_llm", new_callable=AsyncMock) as mock:
            mock.return_value = "슬라임 HP를 200으로 올렸습니다!"
            result = await synthesizer(_state())

        assert "final_response" in result
        assert result["final_response"] == "슬라임 HP를 200으로 올렸습니다!"

    @pytest.mark.asyncio
    async def test_success_scenario_calls_llm(self):
        with patch("agent.editor.nodes.synthesizer.invoke_llm", new_callable=AsyncMock) as mock:
            mock.return_value = "성공 응답"
            await synthesizer(_state(passed=True))

        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_scenario_calls_llm(self):
        """검증 실패(retry 한계 초과)도 LLM으로 응답 생성."""
        with patch("agent.editor.nodes.synthesizer.invoke_llm", new_callable=AsyncMock) as mock:
            mock.return_value = "실패 응답"
            result = await synthesizer(_state(passed=False, errors=["오류 발생"]))

        mock.assert_called_once()
        assert result["final_response"] == "실패 응답"

    @pytest.mark.asyncio
    async def test_prompt_passed_to_llm(self):
        """build_prompt 결과가 invoke_llm에 전달되는지 확인."""
        with patch("agent.editor.nodes.synthesizer.invoke_llm", new_callable=AsyncMock) as mock:
            mock.return_value = "응답"
            await synthesizer(_state(user_input="드래곤 만들어줘"))

        messages = mock.call_args[0][0]
        assert any("드래곤 만들어줘" in str(m.content) for m in messages)

    @pytest.mark.asyncio
    async def test_query_intent(self):
        state = _state(
            intent="query",
            user_input="슬라임 HP가 얼마야?",
            current={"Enemies": [{"id": 1, "name": "슬라임", "params": {"mhp": 100}}]},
        )
        with patch("agent.editor.nodes.synthesizer.invoke_llm", new_callable=AsyncMock) as mock:
            mock.return_value = "슬라임 HP는 100입니다."
            result = await synthesizer(state)

        assert result["final_response"] == "슬라임 HP는 100입니다."


# ── 통합 테스트 (실제 LLM 호출) ───────────────────────────────────────────────
# 실행: uv run pytest agent/tests/test_synthesizer.py -v -m integration -s


@pytest.mark.integration
class TestSynthesizerIntegration:
    """실제 LLM API를 호출하는 통합 테스트. API 키가 필요합니다."""

    @pytest.mark.asyncio
    async def test_modify_success(self):
        state = _state(
            intent="object_update",
            user_input="슬라임 HP를 200으로 올려줘",
            passed=True,
            current={"Enemies": [{"id": 1, "name": "슬라임", "params": {"mhp": 100}}]},
            modified={"Enemies": [{"id": 1, "name": "슬라임", "params": {"mhp": 200}}]},
            changes=[{"file": "Enemies.json", "field": "mhp", "before": 100, "after": 200}],
        )
        result = await synthesizer(state)
        print(f"\n[수정 성공] {result['final_response']}")
        assert len(result["final_response"]) > 0

    @pytest.mark.asyncio
    async def test_create_success(self):
        state = _state(
            intent="object_create",
            user_input="드래곤 적 만들어줘",
            passed=True,
            modified={
                "Enemies": [{"id": 10, "name": "드래곤", "params": {"mhp": 9999, "atk": 500}}]
            },
            changes=[{"file": "Enemies.json", "action": "create", "name": "드래곤"}],
        )
        result = await synthesizer(state)
        print(f"\n[생성 성공] {result['final_response']}")
        assert len(result["final_response"]) > 0

    @pytest.mark.asyncio
    async def test_query_success(self):
        state = _state(
            intent="query",
            user_input="적 목록 보여줘",
            passed=True,
            current={
                "Enemies": [
                    {"id": 1, "name": "슬라임", "params": {"mhp": 100}},
                    {"id": 2, "name": "고블린", "params": {"mhp": 150}},
                ]
            },
        )
        result = await synthesizer(state)
        print(f"\n[조회 성공] {result['final_response']}")
        assert len(result["final_response"]) > 0

    @pytest.mark.asyncio
    async def test_validation_failure(self):
        state = _state(
            intent="object_update",
            user_input="슬라임킹 HP 올려줘",
            passed=False,
            errors=["Enemy '슬라임킹' not found in Enemies.json"],
        )
        result = await synthesizer(state)
        print(f"\n[검증 실패] {result['final_response']}")
        assert len(result["final_response"]) > 0
