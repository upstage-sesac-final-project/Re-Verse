"""Task 9 — Definition 의 이벤트 early-path + rule_engine event branch.

router parsed_command.field="이벤트" + action="생성" 이 operation_tuples 로,
그리고 planner 에서 execution_plan 으로 정상 변환되는지 검증.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.definition import (
    _detect_event_template,
    _extract_event_config,
    _extract_event_position,
    _extract_map_id,
    _try_build_event_operation_tuples,
    definition,
)
from agent.editor.nodes.planner.rule_engine import (
    _is_event_operation,
    _plan_event_operation,
    build_execution_plan,
)


class TestTemplateDetection:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("상점을 만들어줘", "shop"),
            ("NPC 가 말해줘", "npc_talk"),
            ("대사 이벤트 만들어줘", "npc_talk"),
            ("장소 이동 이벤트", "teleport"),
            ("텔레포트 이벤트 추가", "teleport"),
            ("스위치 토글 이벤트", "switch_trigger"),
            ("전투 시작 이벤트", "battle"),
            ("아무 말도 없는 문장", None),
        ],
    )
    def test_detect(self, text, expected):
        assert _detect_event_template(text) == expected


class TestConfigExtraction:
    def test_npc_talk_quoted(self):
        cfg = _extract_event_config("npc_talk", '마을 사람이 "안녕하세요" 라고 말해')
        assert cfg["text"] == "안녕하세요"

    def test_teleport_map_id(self):
        cfg = _extract_event_config("teleport", "Map003 으로 이동시키는 이벤트")
        assert cfg["map_id"] == 3

    def test_teleport_korean_map(self):
        cfg = _extract_event_config("teleport", "5번 맵으로 이동")
        assert cfg["map_id"] == 5

    def test_switch_id(self):
        cfg = _extract_event_config("switch_trigger", "스위치 7 번 켜는 이벤트")
        assert cfg["switch_id"] == 7

    def test_battle_troop(self):
        cfg = _extract_event_config("battle", "troop 4 와 전투")
        assert cfg["troop_id"] == 4


class TestPositionExtraction:
    def test_paren_tuple(self):
        assert _extract_event_position("(3, 5) 에 이벤트") == (3, 5)

    def test_xy_form(self):
        assert _extract_event_position("x=10 y=20 위치") == (10, 20)

    def test_missing(self):
        assert _extract_event_position("어디 좀") == (None, None)


class TestMapId:
    def test_basic(self):
        assert _extract_map_id("Map003 에") == 3
        assert _extract_map_id("5번 맵에") == 5
        assert _extract_map_id("아무것도 없음") is None


class TestBuildEventOperationTuples:
    def test_full_sufficient(self):
        pc = {"field": "이벤트", "action": "생성", "target": "마을 NPC"}
        ops, hold = _try_build_event_operation_tuples(
            pc, "Map003 의 (3,5) 위치에 NPC 가 \"안녕하세요\" 말하는 이벤트"
        )
        assert hold is None
        assert ops
        assert ops[0]["file"] == "Map003.json"
        assert ops[0]["raw_updates"]["template"] == "npc_talk"
        assert ops[0]["raw_updates"]["x"] == 3
        assert ops[0]["raw_updates"]["y"] == 5

    def test_hold_unknown_template(self):
        pc = {"field": "이벤트", "action": "생성", "target": ""}
        ops, hold = _try_build_event_operation_tuples(pc, "뭔가 이벤트")
        assert ops == []
        assert hold == "ambiguous_ref"

    def test_hold_no_map_id(self):
        pc = {"field": "이벤트", "action": "생성", "target": ""}
        ops, hold = _try_build_event_operation_tuples(pc, "NPC 대사 이벤트")
        assert ops == []
        assert hold == "page_condition_unclear"

    def test_hold_no_position(self):
        pc = {"field": "이벤트", "action": "생성", "target": ""}
        ops, hold = _try_build_event_operation_tuples(pc, "Map001 에 NPC 대사")
        assert ops == []
        assert hold == "ambiguous_position"

    def test_common_event(self):
        pc = {"field": "공용이벤트", "action": "생성", "target": "공용상점"}
        ops, hold = _try_build_event_operation_tuples(pc, "상점 공용 이벤트 만들어줘")
        assert hold is None
        assert ops[0]["file"] == "CommonEvents.json"
        assert ops[0]["raw_updates"]["template"] == "shop"

    def test_troop(self):
        pc = {"field": "트룹", "action": "생성", "target": "보스전"}
        ops, hold = _try_build_event_operation_tuples(pc, "전투 트룹 만들어줘")
        assert hold is None
        assert ops[0]["file"] == "Troops.json"
        assert ops[0]["raw_updates"]["template"] == "battle"

    def test_non_event_intent_noop(self):
        pc = {"field": "무기", "action": "생성", "target": "검 A"}
        ops, hold = _try_build_event_operation_tuples(pc, "검 A 만들어줘")
        assert ops == []
        assert hold is None


class TestPlannerEventBranch:
    def test_is_event_operation(self):
        op = {
            "op": "create",
            "file": "Map003.json",
            "subject": None,
            "raw_updates": {"template": "npc_talk", "config": {}, "x": 0, "y": 0},
        }
        assert _is_event_operation(op) is True

    def test_non_event_operation(self):
        op = {
            "op": "create",
            "file": "Weapons.json",
            "subject": {"name": "검 A"},
        }
        assert _is_event_operation(op) is False

    def test_plan_event_operation_shape(self, tmp_path: Path):
        op = {
            "op": "create",
            "file": "Map005.json",
            "subject": None,
            "raw_updates": {
                "template": "teleport",
                "config": {"map_id": 2, "x": 0, "y": 0},
                "name": "2층으로",
                "x": 1,
                "y": 1,
            },
        }
        plan, meta, _ = build_execution_plan([op], tmp_path)
        assert len(plan) == 1
        assert plan[0]["action_type"] == "create_event_from_template"
        assert plan[0]["target_file"] == "Map005.json"
        assert plan[0]["target_info"]["template"] == "teleport"
        assert plan[0]["target_info"]["x"] == 1


@pytest.mark.asyncio
async def test_definition_wrapper_event_early_path(tmp_path: Path):
    """Definition wrapper 가 이벤트 의도를 early-path 로 처리 — _definition_core 호출 안 됨."""
    state = {
        "user_input": 'Map003 의 (3,5) 위치에 NPC 가 "안녕하세요" 말해줘',
        "game_id": "test_game",
        "parsed_command": {
            "field": "이벤트",
            "target": "마을 NPC",
            "action": "생성",
            "property": "",
            "value": "",
            "bulk_scope": "",
        },
    }
    with patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(side_effect=AssertionError("core 는 호출되면 안 됨")),
    ):
        result = await definition(state)

    assert result["params_sufficient"] is True
    assert result["resolve"] is True
    assert result["operation_tuples"]
    assert result["operation_tuples"][0]["file"] == "Map003.json"
    assert result["operation_tuples"][0]["raw_updates"]["template"] == "npc_talk"


@pytest.mark.asyncio
async def test_definition_wrapper_event_hold_on_missing_position(tmp_path: Path):
    state = {
        "user_input": "Map003 에 NPC 대사",
        "game_id": "g",
        "parsed_command": {"field": "이벤트", "target": "", "action": "생성"},
    }
    with patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(side_effect=AssertionError("core 는 호출되면 안 됨")),
    ):
        result = await definition(state)

    assert result["resolve"] is False
    assert result["hold_reason"] == "ambiguous_position"
    assert "좌표" in result["hold_question"]
