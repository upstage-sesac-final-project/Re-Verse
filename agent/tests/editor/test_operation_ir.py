"""operation_ir subpackage 단위 테스트 — build/normalize/validate 순수 로직 검증 (LLM 호출 없음)."""

from __future__ import annotations

import pytest

from agent.editor.operation_ir import (
    build_from_extractions,
    normalize_modifications,
    validate_operation_tuples,
)

# ──────────────────────────────────────────────
# build_from_extractions (Step 5 코드 경로)
# ──────────────────────────────────────────────


class TestBuildFromExtractions:
    """extractions + classifications → operation_tuples."""

    def test_update_name_single_actor(self):
        """이름 변경 — 단일 Actor UPDATE."""
        extractions = [{"action": "UPDATE", "subject": "리드", "property": "이름", "value": "예빈"}]
        classifications = [{"name": "리드", "category": "Actor", "mapped_id": 1}]
        ops = build_from_extractions(extractions, classifications, {}, "game_001")
        assert len(ops) == 1
        op = ops[0]
        assert op["op"] == "update"
        assert op["file"] == "Actors.json"
        assert op["subject"]["id"] == 1
        assert op["field"] == "name"
        assert op["value"]["kind"] == "string"
        assert op["value"]["new_value"] == "예빈"

    def test_create_actor(self):
        """신규 Actor 생성 — id None, file 결정."""
        extractions = [{"action": "CREATE", "subject": "메리", "property": None, "value": None}]
        classifications = [{"name": "메리", "category": "Actor", "mapped_id": "NEW"}]
        ops = build_from_extractions(extractions, classifications, {}, "game_001")
        assert len(ops) == 1
        op = ops[0]
        assert op["op"] == "create"
        assert op["file"] == "Actors.json"
        assert op["subject"]["id"] is None
        assert op["value"] is None

    def test_system_field_game_title(self):
        """'게임 제목' — System.json 감지."""
        extractions = [
            {"action": "UPDATE", "subject": "게임", "property": "제목", "value": "리버스"}
        ]
        classifications = []  # subject 미매칭
        ops = build_from_extractions(extractions, classifications, {}, "game_001")
        assert len(ops) == 1
        assert ops[0]["file"] == "System.json"
        assert ops[0]["field"] == "gameTitle"

    def test_unknown_subject_fallback(self):
        """subject 가 classification 에도 system 도 아니면 빈 리스트 (fallback 신호)."""
        extractions = [
            {"action": "UPDATE", "subject": "알수없는것", "property": "뭔가", "value": "값"}
        ]
        ops = build_from_extractions(extractions, [], {}, "game_001")
        assert ops == []

    def test_no_subject_returns_empty(self):
        """subject 없으면 변환 불가."""
        extractions = [{"action": "UPDATE", "subject": "", "property": "이름", "value": "v"}]
        ops = build_from_extractions(extractions, [], {}, "game_001")
        assert ops == []


# ──────────────────────────────────────────────
# normalize_modifications (Step 6 LLM 경로)
# ──────────────────────────────────────────────


class TestNormalizeModifications:
    """LLM modifications → operation_tuples."""

    def test_create_actor(self):
        mods = [{"type": "create", "target": "actor", "params": {"name": "카엘"}}]
        ops = normalize_modifications(mods, {})
        assert len(ops) == 1
        op = ops[0]
        assert op["op"] == "create"
        assert op["file"] == "Actors.json"
        assert op["subject"]["name"] == "카엘"

    def test_update_with_selector(self):
        mods = [
            {
                "type": "update",
                "target": "actor",
                "params": {
                    "selector": {"name": "리드", "id": 1},
                    "updates": {"name": "예빈"},
                },
            }
        ]
        ops = normalize_modifications(mods, {})
        assert len(ops) == 1
        op = ops[0]
        assert op["op"] == "update"
        assert op["subject"]["id"] == 1
        assert op["value"]["raw_updates"] == {"name": "예빈"}

    def test_update_empty_updates_dropped(self):
        """updates 비면 op 생성 안 함 (빈 리스트)."""
        mods = [
            {
                "type": "update",
                "target": "actor",
                "params": {"selector": {"name": "리드"}, "updates": {}},
            }
        ]
        assert normalize_modifications(mods, {}) == []

    def test_profiler_fields_filtered(self):
        """traits/effects/params 등 profiler 담당 필드는 버린다."""
        mods = [
            {
                "type": "update",
                "target": "enemy",
                "params": {
                    "selector": {"name": "고블린"},
                    "updates": {"name": "강화 고블린", "traits": [{"code": 1}], "params": [10]},
                },
            }
        ]
        ops = normalize_modifications(mods, {})
        assert len(ops) == 1
        assert ops[0]["value"]["raw_updates"] == {"name": "강화 고블린"}

    def test_read_op(self):
        mods = [{"type": "query", "target": "actor", "params": {"searchTerm": "리드"}}]
        ops = normalize_modifications(mods, {})
        assert len(ops) == 1
        assert ops[0]["op"] == "read"
        assert ops[0]["subject"]["name"] == "리드"

    def test_unknown_target_skipped(self):
        mods = [{"type": "update", "target": "unknown_thing", "params": {}}]
        assert normalize_modifications(mods, {}) == []


# ──────────────────────────────────────────────
# validate_operation_tuples (Step 10 degenerate)
# ──────────────────────────────────────────────


class TestValidateOperationTuples:
    def test_empty_ops_ok(self):
        ok, msg = validate_operation_tuples([], [])
        assert ok is True and msg == ""

    def test_create_ignored(self):
        """create 는 degenerate 검사 대상 아님."""
        ops = [
            {"op": "create", "file": "Actors.json", "subject": None, "field": None, "value": None}
        ]
        ok, _ = validate_operation_tuples(ops, [])
        assert ok is True

    def test_update_missing_subject(self):
        """update 인데 subject id·name 모두 없음 → degenerate."""
        ops = [
            {
                "op": "update",
                "file": "Actors.json",
                "subject": {"name": None, "id": None, "scope": "single"},
                "field": "name",
                "value": {"kind": "string", "new_value": "v"},
            }
        ]
        extractions = [{"action": "UPDATE", "subject": "리드"}]
        ok, msg = validate_operation_tuples(ops, extractions)
        assert ok is False
        assert "리드" in msg

    def test_update_empty_value_degenerate(self):
        """update 인데 field/value 없고 raw_updates 도 비어있음 → degenerate."""
        ops = [
            {
                "op": "update",
                "file": "Actors.json",
                "subject": {"name": "리드", "id": 1, "scope": "single"},
                "field": None,
                "value": None,
            }
        ]
        ok, msg = validate_operation_tuples(ops, [])
        assert ok is False
        assert "리드" in msg

    def test_step5_direct_structure_valid(self):
        """Step 5 경로 op[field]+op[value] 구조도 유효 — 이전 버그 회귀 방지."""
        ops = [
            {
                "op": "update",
                "file": "Actors.json",
                "subject": {"name": "솔라", "id": 1, "scope": "single"},
                "field": "name",
                "value": {"kind": "string", "new_value": "예빈"},
            }
        ]
        ok, msg = validate_operation_tuples(ops, [])
        assert ok is True and msg == ""

    def test_step6_raw_updates_valid(self):
        """Step 6 경로 value.raw_updates 구조도 유효."""
        ops = [
            {
                "op": "update",
                "file": "Actors.json",
                "subject": {"name": "리드", "id": 1, "scope": "single"},
                "field": None,
                "value": {"raw_updates": {"name": "예빈"}},
            }
        ]
        ok, _ = validate_operation_tuples(ops, [])
        assert ok is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
