"""Task 19 — parsed_command.value 가 profile 결과에 강제 주입되는지 검증."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.profiler import (
    _coerce_value,
    _enforce_name_lock,
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


# ── sprint β: multi-property + name lock ────────────────────────────


class TestMultiPropertyInjection:
    def test_weapon_three_stats_at_once(self):
        """'체력 400, MP 30, 공격력 15' → params[0]/[1]/[2] 모두 세팅."""
        step = {
            "target_file": "Weapons.json",
            "target_info": {"name": "경찰봉"},
        }
        pc = {
            "property": "체력",
            "value": "400",
            "additional_properties": [
                {"property": "MP", "value": "30"},
                {"property": "공격력", "value": "15"},
            ],
        }
        out = _inject_parsed_command_value(step, pc)
        params = out["target_info"]["params"]
        assert params[0] == 400  # 체력
        assert params[1] == 30   # MP
        assert params[2] == 15   # 공격력

    def test_enemy_hp_and_exp(self):
        step = {
            "target_file": "Enemies.json",
            "target_info": {"name": "드래곤"},
        }
        pc = {
            "property": "HP",
            "value": "9999",
            "additional_properties": [{"property": "경험치", "value": "500"}],
        }
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["params"][0] == 9999
        assert out["target_info"]["exp"] == 500

    def test_empty_additional_properties_noop(self):
        """기존 단일 property/value 경로는 그대로 작동 (하위호환)."""
        step = {
            "target_file": "Weapons.json",
            "target_info": {"name": "검"},
        }
        pc = {
            "property": "공격력",
            "value": "50",
            "additional_properties": [],
        }
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["params"][2] == 50

    def test_additional_properties_non_list_ignored(self):
        """오염된 타입이 와도 크래시 없이 단일 경로만 작동."""
        step = {
            "target_file": "Weapons.json",
            "target_info": {"name": "검"},
        }
        pc = {"property": "공격력", "value": "50", "additional_properties": "not a list"}
        out = _inject_parsed_command_value(step, pc)
        assert out["target_info"]["params"][2] == 50

    def test_unknown_extra_property_silently_skipped(self):
        step = {
            "target_file": "Weapons.json",
            "target_info": {"name": "검"},
        }
        pc = {
            "property": "공격력",
            "value": "50",
            "additional_properties": [{"property": "외계속성", "value": "999"}],
        }
        out = _inject_parsed_command_value(step, pc)
        # 알려진 속성은 반영
        assert out["target_info"]["params"][2] == 50
        # 모르는 속성은 무시 (추가 키 없음)
        assert "외계속성" not in out["target_info"]


class TestNameLock:
    def test_llm_overwrites_name_gets_reverted(self):
        """LLM 이 '경찰' 을 '리드' 로 바꿨을 때 원본 복원."""
        original = {
            "target_file": "Actors.json",
            "target_info": {"name": "경찰"},
        }
        enriched = {
            "target_file": "Actors.json",
            "target_info": {"name": "리드", "initialLevel": 10, "classId": 1},
        }
        out = _enforce_name_lock(original, enriched)
        assert out["target_info"]["name"] == "경찰"
        # 다른 필드는 유지
        assert out["target_info"]["initialLevel"] == 10
        assert out["target_info"]["classId"] == 1

    def test_name_preserved_when_same(self):
        original = {"target_info": {"name": "검"}}
        enriched = {"target_info": {"name": "검", "price": 100}}
        out = _enforce_name_lock(original, enriched)
        assert out["target_info"]["name"] == "검"
        assert out["target_info"]["price"] == 100

    def test_no_original_name_noop(self):
        """planner 가 name 을 안 넣었으면 LLM 의 값을 허용."""
        original = {"target_info": {}}
        enriched = {"target_info": {"name": "자동생성", "price": 50}}
        out = _enforce_name_lock(original, enriched)
        assert out["target_info"]["name"] == "자동생성"


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
