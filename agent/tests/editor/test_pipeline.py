"""전체 노드 파이프라인 통합 테스트.

실행 방법:
    uv run pytest agent/tests/test_pipeline.py -v -s -m integration
"""

import pytest

from agent.editor.workflow import graph

pytestmark = pytest.mark.integration

GAME_ID = "game_001"


def _base_state(user_input: str) -> dict:
    return {
        "user_input": user_input,
        "game_id": GAME_ID,
        "conversation_history": [],
        "retry_count": 0,
    }


class TestFullPipeline:
    async def test_create_enemy_full_pipeline(self):
        """적 생성 — 전체 6단계 완주."""
        result = await graph.ainvoke(_base_state("드래곤 보스 몬스터를 HP 5000으로 만들어줘"))
        assert "intent" in result
        assert "final_response" in result
        print(f"\n[생성] {result['final_response']}")

    async def test_modify_enemy_full_pipeline(self):
        """적 수정 — 전체 6단계 완주."""
        result = await graph.ainvoke(_base_state("슬라임 HP를 200으로 올려줘"))
        assert "intent" in result
        assert "final_response" in result
        print(f"\n[수정] {result['final_response']}")

    async def test_query_full_pipeline(self):
        """조회 — 전체 6단계 완주."""
        result = await graph.ainvoke(_base_state("현재 등록된 직업이 몇 개야?"))
        assert "intent" in result
        assert "final_response" in result
        print(f"\n[조회] {result['final_response']}")

    async def test_terminal_intent_ends_immediately(self):
        """지원 불가 인텐트는 definition 없이 즉시 종료."""
        result = await graph.ainvoke(_base_state("안녕 반가워"))
        assert result["intent"] in {"small_talk", "out_of_scope", "clarification_needed"}
        assert result.get("final_response") is not None
        assert "params_sufficient" not in result

    async def test_state_fields_populated_end_to_end(self):
        """수정 요청 시 모든 단계 상태 필드가 채워진다."""
        result = await graph.ainvoke(_base_state("고블린 HP를 120으로 수정해줘"))

        assert result.get("intent") in {
            "object_create",
            "object_update",
            "event_create",
            "event_update",
            "query",
            "game_overview",
        }
        assert "final_response" in result

        if result.get("params_sufficient"):
            assert result.get("execution_plan")
            assert result.get("current_game_state") is not None
            assert result.get("modified_game_state") is not None
            assert isinstance(result.get("success"), bool)
            print(f"\n  intent={result['intent']}")
            print(f"  success={result['success']}")
            print(f"  response={result['final_response']}")
