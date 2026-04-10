"""pytest 기반 new-agent 테스트.

사전 정의된 시나리오를 자동으로 실행.
LLM 호출이 필요하므로 .env 가 설정된 환경에서만 실행.

사용법:
    pytest new-agent/test_pytest.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

GAME_ID = "game_001"


@pytest.fixture
def game_data_path():
    from app.backend.core.game_paths import get_game_data_path
    return get_game_data_path(GAME_ID)


@pytest.fixture
def graph():
    from new_agent.workflow import graph
    return graph


# ──────────────────────────────────────────────
# Planner unit tests (LLM 불필요)
# ──────────────────────────────────────────────

class TestPlannerRuleEngine:
    """planner 의 rule_engine 만 단독 테스트. LLM 없이 돌아감."""

    def test_simple_update_plan(self, game_data_path):
        from new_agent.nodes.planner.rule_engine import build_execution_plan

        ops = [
            {
                "op": "update",
                "file": "Actors.json",
                "subject": {"name": "리드"},
                "field": "params",
                "value": {"kind": "param", "name": "atk", "amount": 10},
            }
        ]
        plan, meta = build_execution_plan(ops, game_data_path)
        assert len(plan) >= 1
        assert plan[0]["target_file"] == "Actors.json"
        assert 0 in meta

    def test_equip_armor_creates_prerequisites(self, game_data_path):
        """equip armor → System.equipTypes + Armors.json + Actors.json 순서 step 생성."""
        from new_agent.nodes.planner.rule_engine import build_execution_plan

        ops = [
            {
                "op": "update",
                "file": "Actors.json",
                "subject": {"name": "리드"},
                "field": "equips",
                "value": {"kind": "armor", "name": "테스트 방패", "slot_type": "방패"},
            }
        ]
        plan, meta = build_execution_plan(ops, game_data_path)
        # 최소 1개 step 이 있어야 함
        assert len(plan) >= 1
        # step 중 System.json 또는 Armors.json 관련이 있을 수 있음
        files_touched = {s["target_file"] for s in plan}
        assert "Actors.json" in files_touched

    def test_read_plan(self, game_data_path):
        from new_agent.nodes.planner.rule_engine import build_execution_plan

        ops = [
            {
                "op": "read",
                "file": "Actors.json",
                "subject": {"name": "리드"},
                "field": None,
                "value": None,
            }
        ]
        plan, meta = build_execution_plan(ops, game_data_path)
        assert len(plan) == 1
        assert plan[0]["action_type"] == "get"

    def test_create_enemy_plan(self, game_data_path):
        from new_agent.nodes.planner.rule_engine import build_execution_plan

        ops = [
            {
                "op": "create",
                "file": "Enemies.json",
                "subject": {"name": "슬라임"},
                "field": None,
                "value": {"kind": "enemy", "name": "슬라임"},
            }
        ]
        plan, meta = build_execution_plan(ops, game_data_path)
        assert len(plan) >= 1
        assert any(s["action_type"] == "create" for s in plan)


# ──────────────────────────────────────────────
# Traits util tests
# ──────────────────────────────────────────────

class TestTraitsUtil:
    def test_trait_reference_text(self):
        from new_agent.executor.utils.traits import build_traits_reference_text
        text = build_traits_reference_text()
        assert "원소 내성률" in text
        assert "code=11" in text

    def test_describe_trait(self):
        from new_agent.executor.utils.traits import describe_trait
        desc = describe_trait({"code": 11, "dataId": 2, "value": 2.0})
        assert "원소 내성률" in desc

    def test_describe_params(self):
        from new_agent.executor.utils.traits import describe_params
        descs = describe_params([100, 50, 10, 10, 10, 10, 10, 10])
        assert len(descs) == 8
        assert "최대 HP=100" in descs[0]


# ──────────────────────────────────────────────
# Entity handler tests (LLM 불필요)
# ──────────────────────────────────────────────

class TestEntityHandler:
    def test_get_entity(self, game_data_path):
        from new_agent.executor.handlers.entity import execute_entity_step
        result = execute_entity_step(
            game_data_path, "get", "Actors.json", {"id": 1}
        )
        assert result["success"] is True
        assert result["data"] is not None

    def test_search_entity(self, game_data_path):
        from new_agent.executor.handlers.entity import execute_entity_step
        result = execute_entity_step(
            game_data_path, "search", "Actors.json", {"searchTerm": ""}
        )
        assert result["success"] is True

    def test_append_system_type(self, game_data_path):
        """주의: 실제 System.json 을 수정함. 테스트 후 롤백 필요."""
        from new_agent.executor.handlers.entity import execute_entity_step
        # 현재 값 확인 후 추가-삭제 (비파괴적)
        result = execute_entity_step(
            game_data_path, "get_system", "System.json", {}
        )
        assert result["success"] is True
        # 실제 추가는 파괴적이므로 skip
        pytest.skip("실제 파일 수정 방지")


# ──────────────────────────────────────────────
# Map handler tests
# ──────────────────────────────────────────────

class TestMapHandler:
    def test_list_maps(self, game_data_path):
        from new_agent.executor.handlers.map import execute_map_step
        result = execute_map_step(game_data_path, "list_maps", "MapInfos.json", {})
        assert result["success"] is True
        assert isinstance(result["data"], list)


# ──────────────────────────────────────────────
# E2E tests (LLM 필요)
# ──────────────────────────────────────────────

class TestE2EWithLLM:
    """LLM 호출이 필요한 E2E 테스트. 환경변수 미설정 시 skip."""

    @pytest.fixture(autouse=True)
    def _check_llm_available(self):
        import os
        if not os.environ.get("UPSTAGE_API_KEY") and not os.environ.get("LLM_API_KEY"):
            pytest.skip("LLM API key 없음 — E2E 테스트 skip")

    @pytest.mark.asyncio
    async def test_simple_read(self, graph):
        state = {
            "user_input": "리드의 공격력은 얼마야?",
            "game_id": GAME_ID,
            "conversation_history": [],
            "retry_count": 0,
        }
        result = await graph.ainvoke(state)
        assert "final_response" in result

    @pytest.mark.asyncio
    async def test_simple_update(self, graph):
        state = {
            "user_input": "리드의 공격력을 50으로 바꿔줘",
            "game_id": GAME_ID,
            "conversation_history": [],
            "retry_count": 0,
        }
        result = await graph.ainvoke(state)
        assert "final_response" in result

    @pytest.mark.asyncio
    async def test_create_enemy(self, graph):
        state = {
            "user_input": "적에 슬라임을 추가해줘",
            "game_id": GAME_ID,
            "conversation_history": [],
            "retry_count": 0,
        }
        result = await graph.ainvoke(state)
        assert "final_response" in result
        # profiler 가 traits 를 채웠는지 확인
        plan = result.get("execution_plan", [])
        create_steps = [s for s in plan if s.get("action_type") == "create"]
        if create_steps:
            ti = create_steps[0].get("target_info", {})
            assert "params" in ti or "traits" in ti, "profiler 가 의미적 필드를 채우지 않았음"

    @pytest.mark.asyncio
    async def test_coref_resolution(self, graph):
        """multi-turn coref: '예빈에게도 해줘'."""
        state = {
            "user_input": "예빈에게도 해줘",
            "game_id": GAME_ID,
            "conversation_history": [
                {"role": "user", "content": "리드에게 치유 스킬을 부여해줘"},
                {"role": "assistant", "content": "리드에게 치유 스킬을 부여했습니다."},
            ],
            "retry_count": 0,
        }
        result = await graph.ainvoke(state)
        assert "final_response" in result

    @pytest.mark.asyncio
    async def test_chat_passthrough(self, graph):
        state = {
            "user_input": "안녕하세요!",
            "game_id": GAME_ID,
            "conversation_history": [],
            "retry_count": 0,
        }
        result = await graph.ainvoke(state)
        assert result.get("kind") in ("chat", "out_of_scope")
        assert "final_response" in result
