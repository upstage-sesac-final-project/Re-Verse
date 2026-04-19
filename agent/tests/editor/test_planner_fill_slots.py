"""Planner 의 fill_slots 생성 로직 단위 테스트."""

from __future__ import annotations

from agent.editor.nodes.planner import _collect_fill_slots, _consume_reference_checks


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


# ── Task 5: reference_checks 소비 ────────────────────────────────────────


class TestConsumeReferenceChecks:
    def test_empty_returns_no_warnings(self):
        ops, warnings = _consume_reference_checks([], [{"action": "update"}])
        assert warnings == []

    def test_not_found_without_create_produces_warning(self):
        refs = [{"category": "Enemy", "name": "슬라임", "status": "not_found"}]
        ops = [{"action": "update", "file": "Enemies.json"}]
        _, warnings = _consume_reference_checks(refs, ops)
        assert warnings
        assert "슬라임" in warnings[0]

    def test_not_found_with_create_no_warning(self):
        refs = [{"category": "Enemy", "name": "슬라임", "status": "not_found"}]
        ops = [{"action": "create", "file": "Enemies.json"}]
        _, warnings = _consume_reference_checks(refs, ops)
        assert warnings == []

    def test_found_status_no_warning(self):
        refs = [{"category": "Enemy", "name": "슬라임", "status": "found"}]
        ops = [{"action": "update", "file": "Enemies.json"}]
        _, warnings = _consume_reference_checks(refs, ops)
        assert warnings == []

    def test_ambiguous_status_no_warning(self):
        """ambiguous 는 Definition 이 hold 처리해야 할 영역 — 여기서는 noop."""
        refs = [{"category": "Enemy", "name": "슬라임", "status": "ambiguous"}]
        ops = [{"action": "update", "file": "Enemies.json"}]
        _, warnings = _consume_reference_checks(refs, ops)
        assert warnings == []

    def test_returns_operation_tuples_unchanged(self):
        refs = [{"category": "Enemy", "name": "X", "status": "not_found"}]
        ops = [{"action": "update", "file": "Enemies.json", "x": 1}]
        out_ops, _ = _consume_reference_checks(refs, ops)
        assert out_ops is ops


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
