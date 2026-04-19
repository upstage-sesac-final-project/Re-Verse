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
    # MapNNN.json / Unknown.json 등은 fill_schemas 레지스트리에 없음 (이벤트는 별도 경로)
    plan = [_step(1, "Map003.json")]
    assert _collect_fill_slots(plan) == []
    plan2 = [_step(1, "Unknown.json")]
    assert _collect_fill_slots(plan2) == []


# ── Task 5: reference_checks 소비 ────────────────────────────────────────


class TestConsumeReferenceChecks:
    def test_empty_returns_no_warnings(self):
        ops, warnings = _consume_reference_checks([], [{"op": "update"}])
        assert warnings == []

    def test_not_found_triggers_prepended_create(self):
        """Task 12 — 선행 create 가 자동 삽입되고 경고에 기록."""
        refs = [{"category": "Enemy", "name": "슬라임", "status": "not_found"}]
        ops = [
            {
                "op": "update",
                "file": "Enemies.json",
                "subject": {"name": "슬라임"},
                "field": "hp",
            }
        ]
        out_ops, warnings = _consume_reference_checks(refs, ops)
        assert len(out_ops) == 2
        assert out_ops[0]["op"] == "create"
        assert out_ops[0]["file"] == "Enemies.json"
        assert out_ops[0]["subject"]["name"] == "슬라임"
        assert out_ops[1] is ops[0]
        assert warnings
        assert "슬라임" in warnings[0]

    def test_not_found_but_create_already_exists(self):
        refs = [{"category": "Enemy", "name": "슬라임", "status": "not_found"}]
        ops = [
            {"op": "create", "file": "Enemies.json", "subject": {"name": "슬라임"}},
        ]
        out_ops, warnings = _consume_reference_checks(refs, ops)
        assert out_ops == ops
        assert warnings == []

    def test_not_found_no_matching_ops_no_insertion(self):
        """참조 이름과 일치하는 update/delete op 이 없으면 삽입하지 않음."""
        refs = [{"category": "Enemy", "name": "슬라임", "status": "not_found"}]
        ops = [
            {"op": "update", "file": "Enemies.json", "subject": {"name": "드래곤"}},
        ]
        out_ops, warnings = _consume_reference_checks(refs, ops)
        assert out_ops == ops
        assert warnings == []

    def test_found_status_no_action(self):
        refs = [{"category": "Enemy", "name": "슬라임", "status": "found"}]
        ops = [{"op": "update", "file": "Enemies.json", "subject": {"name": "슬라임"}}]
        out_ops, warnings = _consume_reference_checks(refs, ops)
        assert out_ops == ops
        assert warnings == []

    def test_ambiguous_status_no_action(self):
        refs = [{"category": "Enemy", "name": "슬라임", "status": "ambiguous"}]
        ops = [{"op": "update", "file": "Enemies.json", "subject": {"name": "슬라임"}}]
        out_ops, warnings = _consume_reference_checks(refs, ops)
        assert out_ops == ops
        assert warnings == []

    def test_unknown_category_warns(self):
        refs = [{"category": "UnknownCategory", "name": "X", "status": "not_found"}]
        ops = [{"op": "update", "file": "Actors.json", "subject": {"name": "X"}}]
        _, warnings = _consume_reference_checks(refs, ops)
        assert warnings
        assert "매핑 없음" in warnings[0]

    def test_duplicate_not_found_inserts_only_once(self):
        refs = [
            {"category": "Enemy", "name": "슬라임", "status": "not_found"},
            {"category": "Enemy", "name": "슬라임", "status": "not_found"},
        ]
        ops = [{"op": "update", "file": "Enemies.json", "subject": {"name": "슬라임"}}]
        out_ops, _ = _consume_reference_checks(refs, ops)
        creates = [o for o in out_ops if o["op"] == "create"]
        assert len(creates) == 1


def test_multiple_steps_accumulate_correctly():
    plan = [
        _step(1, "Weapons.json"),
        _step(2, "Actors.json"),
        _step(3, "Unknown.json"),  # skip — 레지스트리에 없음
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
