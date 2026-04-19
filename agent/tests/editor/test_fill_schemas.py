"""fill_schemas 단위 테스트."""

from __future__ import annotations

import pytest

from agent.editor.nodes.planner.fill_schemas import (
    ACTOR_FILL_SCHEMA,
    ARMOR_FILL_SCHEMA,
    CLASS_FILL_SCHEMA,
    ENEMY_FILL_SCHEMA,
    FILL_SCHEMAS,
    ITEM_FILL_SCHEMA,
    SKILL_FILL_SCHEMA,
    STATE_FILL_SCHEMA,
    SYSTEM_FILL_SCHEMA,
    TRAIT_PRESETS,
    WEAPONS_FILL_SCHEMA,
    build_fill_slots,
    get_fill_schema,
)


def test_registry_has_all_phase_e_schemas():
    # Phase E 2차 확장 이후 범위
    assert set(FILL_SCHEMAS.keys()) == {
        "Weapons.json",
        "Armors.json",
        "Actors.json",
        "Skills.json",
        "Items.json",
        "Classes.json",
        "Enemies.json",
        "States.json",
        "System.json",
    }


def test_weapons_has_fixed_etype_id():
    assert WEAPONS_FILL_SCHEMA["fixed_fields"]["etypeId"] == 1


def test_all_schemas_declare_params_length_8_when_present():
    for schema in (WEAPONS_FILL_SCHEMA, ARMOR_FILL_SCHEMA):
        slots = schema["required_slots"]
        params_slot = next((s for s in slots if s["name"] == "params"), None)
        assert params_slot is not None, schema["target_file"]
        assert params_slot.get("length") == 8


def test_actor_resource_fields_declared():
    # faceName / characterName / battlerName 은 별도 resource 검증 필요
    assert set(ACTOR_FILL_SCHEMA["resource_fields"]) == {
        "faceName",
        "characterName",
        "battlerName",
    }


def test_get_fill_schema_known_file():
    assert get_fill_schema("Weapons.json") is WEAPONS_FILL_SCHEMA
    assert get_fill_schema("Armors.json") is ARMOR_FILL_SCHEMA
    assert get_fill_schema("Actors.json") is ACTOR_FILL_SCHEMA


def test_get_fill_schema_phase_e2():
    # Phase E-2 에서 등록된 6 종
    assert get_fill_schema("Skills.json") is SKILL_FILL_SCHEMA
    assert get_fill_schema("Items.json") is ITEM_FILL_SCHEMA
    assert get_fill_schema("Classes.json") is CLASS_FILL_SCHEMA
    assert get_fill_schema("Enemies.json") is ENEMY_FILL_SCHEMA
    assert get_fill_schema("States.json") is STATE_FILL_SCHEMA
    assert get_fill_schema("System.json") is SYSTEM_FILL_SCHEMA


def test_get_fill_schema_unknown_file_returns_none():
    assert get_fill_schema("") is None
    assert get_fill_schema("Map003.json") is None
    assert get_fill_schema("Unknown.json") is None


def test_build_fill_slots_for_weapons():
    slots = build_fill_slots(step_id=7, target_file="Weapons.json")
    assert slots
    assert all(s["step_id"] == 7 for s in slots)
    names = {s["field_name"] for s in slots}
    assert {"wtypeId", "price", "animationId", "iconIndex", "params"} <= names
    # params slot 은 length=8 정보를 그대로 실어 보냄
    params = next(s for s in slots if s["field_name"] == "params")
    assert params.get("length") == 8
    assert params.get("type") == "list[int]"


def test_build_fill_slots_unknown_target_is_empty():
    assert build_fill_slots(1, "") == []
    assert build_fill_slots(1, "Unknown.json") == []


@pytest.mark.parametrize(
    "target_file,must_have",
    [
        ("Skills.json", {"stypeId", "mpCost", "scope", "damage"}),
        ("Items.json", {"itypeId", "price", "consumable", "damage"}),
        ("Classes.json", {"expParams", "params"}),
        ("Enemies.json", {"battlerName", "params", "exp", "gold"}),
        ("States.json", {"restriction", "priority", "autoRemovalTiming"}),
    ],
)
def test_phase_e2_schemas_build_fill_slots(target_file, must_have):
    slots = build_fill_slots(step_id=1, target_file=target_file)
    names = {s["field_name"] for s in slots}
    assert must_have <= names, (target_file, names)


def test_build_fill_slots_carries_bounds():
    """ge/le 같은 경계값이 fill_slot 에 보존되는지 (profiler 가 타입 검증 시 사용)."""
    slots = build_fill_slots(step_id=1, target_file="Actors.json")
    initial_level = next(s for s in slots if s["field_name"] == "initialLevel")
    assert initial_level.get("ge") == 1
    assert initial_level.get("le") == 99


def test_trait_presets_shape():
    # Trait 는 {code, dataId, value} 세 필드
    assert TRAIT_PRESETS
    for name, trait in TRAIT_PRESETS.items():
        assert isinstance(trait, dict), name
        assert "code" in trait and "dataId" in trait and "value" in trait, name
