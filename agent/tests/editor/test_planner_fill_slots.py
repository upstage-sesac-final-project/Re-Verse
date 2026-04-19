"""Planner 의 fill_slots 생성 로직 단위 테스트."""

from __future__ import annotations

from agent.editor.nodes.planner import _collect_fill_slots


def _step(step_id: int, target_file: str, *, needs_profiling: bool = True) -> dict:
    return {
        "step_id": step_id,
        "action_type": "create",
        "target_file": target_file,
        "target_info": {"name": "검 A"},
        "depends_on": [],
        "description": "",
        **({"_needs_profiling": True} if needs_profiling else {}),
    }


def test_collect_empty_plan_returns_empty():
    assert _collect_fill_slots([]) == []


def test_create_weapon_step_produces_fill_slots():
    plan = [_step(1, "Weapons.json")]
    slots = _collect_fill_slots(plan)
    assert slots
    assert all(s["step_id"] == 1 for s in slots)
    assert {s["field_name"] for s in slots} >= {"wtypeId", "price", "params"}


def test_step_without_profiling_skipped():
    plan = [_step(1, "Weapons.json", needs_profiling=False)]
    assert _collect_fill_slots(plan) == []


def test_target_file_not_in_registry_skipped():
    # Skills.json 은 Phase E 1차 대상 아님
    plan = [_step(1, "Skills.json")]
    assert _collect_fill_slots(plan) == []


def test_multiple_steps_accumulate_correctly():
    plan = [
        _step(1, "Weapons.json"),
        _step(2, "Actors.json"),
        _step(3, "Skills.json"),  # skip
    ]
    slots = _collect_fill_slots(plan)
    sids = {s["step_id"] for s in slots}
    assert sids == {1, 2}


def test_invalid_step_id_skipped():
    plan = [{"step_id": "abc", "target_file": "Weapons.json", "_needs_profiling": True}]
    assert _collect_fill_slots(plan) == []


def test_non_dict_entry_skipped():
    plan = ["not a dict", {"step_id": 1, "target_file": "Weapons.json", "_needs_profiling": True}]  # type: ignore[list-item]
    slots = _collect_fill_slots(plan)
    assert all(s["step_id"] == 1 for s in slots)
