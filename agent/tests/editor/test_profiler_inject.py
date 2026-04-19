"""Task 19 — parsed_command.value 가 profile 결과에 강제 주입되는지 검증."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.profiler import (
    _coerce_value,
    _inject_parsed_command_value,
    _set_by_path,
    profiler,
)


class TestCoerceValue:
    def test_int(self):
        assert _coerce_value("50") == 50

    def test_float(self):
        assert _coerce_value("1.5") == 1.5

    def test_str_kept(self):
        assert _coerce_value("냥냥펀치") == "냥냥펀치"

    def test_empty(self):
        assert _coerce_value("") == ""


class TestSetByPath:
    def test_simple_key(self):
        info: dict = {}
        assert _set_by_path(info, "price", 500)
        assert info["price"] == 500

    def test_array_path(self):
        info: dict = {}
        assert _set_by_path(info, "params[2]", 50)
        assert info["params"][2] == 50

    def test_array_path_existing(self):
        info: dict = {"params": [1, 2, 3, 4, 5, 6, 7, 8]}
        _set_by_path(info, "params[2]", 50)
        assert info["params"][2] == 50
        assert info["params"][0] == 1  # 다른 슬롯 보존


class TestInjectParsedCommandValue:
    def test_weapon_attack(self):
        """'공격력 50' → params[2] = 50 강제 주입."""
        step = {
            "target_file": "Weapons.json",
            "target_info": {
                "name": "화염검",
                "params": [0, 0, 10, 0, 0, 0, 0, 0],  # profiler 가 10 으로 LLM 채움
            },
        }
        pc = {"property": "공격력", "value": "50"}
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["params"][2] == 50  # 강제 덮어쓰기

    def test_weapon_price(self):
        step = {
            "target_file": "Weapons.json",
            "target_info": {"name": "단검", "price": 100},
        }
        pc = {"property": "가격", "value": "500"}
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["price"] == 500

    def test_enemy_hp(self):
        step = {
            "target_file": "Enemies.json",
            "target_info": {"name": "슬라임", "params": [100, 0, 20, 10, 0, 0, 5, 5]},
        }
        pc = {"property": "HP", "value": "500"}
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["params"][0] == 500

    def test_actor_level(self):
        step = {
            "target_file": "Actors.json",
            "target_info": {"name": "힘멜"},
        }
        pc = {"property": "레벨", "value": "99"}
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["initialLevel"] == 99

    def test_no_property_noop(self):
        step = {"target_file": "Weapons.json", "target_info": {"name": "X"}}
        out = _inject_parsed_command_value(step, {})
        assert out == step or out["target_info"] == step["target_info"]

    def test_unknown_property_noop(self):
        step = {"target_file": "Weapons.json", "target_info": {"name": "X"}}
        pc = {"property": "알수없는속성", "value": "100"}
        out = _inject_parsed_command_value(step, pc)
        assert "알수없는속성" not in out["target_info"]

    def test_unsupported_file_noop(self):
        step = {"target_file": "UnsupportedFile.json", "target_info": {}}
        pc = {"property": "공격력", "value": "50"}
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"] == {}


@pytest.mark.asyncio
async def test_profiler_full_loop_injects_value():
    """profiler 가 profile_one 호출 후 parsed_command.value 를 덮어쓰는지."""
    state = {
        "game_id": "g",
        "execution_plan": [
            {
                "step_id": 1,
                "action_type": "create",
                "target_file": "Weapons.json",
                "_needs_profiling": True,
                "target_info": {"name": "화염검"},
            }
        ],
        "fill_slots": [],
        "parsed_command": {"property": "공격력", "value": "50"},
    }
    with patch(
        "agent.editor.nodes.profiler.profile_one",
        new=AsyncMock(
            return_value={
                "step_id": 1,
                "action_type": "create",
                "target_file": "Weapons.json",
                "target_info": {
                    "name": "화염검",
                    "price": 200,
                    "params": [0, 0, 10, 0, 0, 0, 0, 0],  # LLM 이 atk=10 으로 잘못 추측
                },
            }
        ),
    ):
        result = await profiler(state)

    step = result["execution_plan"][0]
    assert step["target_info"]["params"][2] == 50, "parsed_command.value 가 덮어쓰지 않음"
