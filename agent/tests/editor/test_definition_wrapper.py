"""Definition wrapper 단위 테스트 — Phase D+E-1.

본체 `_definition_core` 를 mock 으로 치환해 wrapper 가:
- 새 contract 필드 (field/target/description/reference_checks/resolve) 를 보강
- hold 감지 시 pending_store.set 호출
- pending_resumed + resumed_snapshot 복원
를 제대로 하는지만 검증한다. 본체 로직은 건드리지 않는다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.definition import (
    _build_reference_checks,
    _infer_field_label,
    _infer_hold_reason,
    _infer_target_label,
    _try_rule_base_step12,
    definition,
)
from agent.editor.pending_store import PendingStore


# ── 헬퍼 함수 단위 ───────────────────────────────────────────────


class TestInferFieldLabel:
    def test_parsed_command_field_wins(self):
        assert _infer_field_label(["Weapons.json"], {"field": "스킬"}) == "스킬"

    def test_fallback_to_target_files(self):
        assert _infer_field_label(["Weapons.json"], None) == "무기"
        assert _infer_field_label(["Armors.json"], {}) == "방어구"
        assert _infer_field_label(["Enemies.json"], None) == "적"
        assert _infer_field_label(["System.json"], None) == "시스템"

    def test_map_file_maps_to_event(self):
        assert _infer_field_label(["Map003.json"], None) == "이벤트"

    def test_unknown_returns_empty(self):
        assert _infer_field_label([], None) == ""
        assert _infer_field_label(["Unknown.json"], None) == ""


class TestInferTargetLabel:
    def test_parsed_command_target_wins(self):
        result = _infer_target_label([], {}, {"target": "검 A"})
        assert result == "검 A"

    def test_fallback_to_modifications_name(self):
        mods = [{"params": {"name": "슬라임"}}]
        assert _infer_target_label(mods, {}, None) == "슬라임"

    def test_fallback_to_extracted_ids(self):
        ids = {"고블린": 12}
        assert _infer_target_label([], ids, None) == "고블린"

    def test_empty_returns_empty(self):
        assert _infer_target_label([], {}, None) == ""


class TestTryRuleBaseStep12:
    """Task 3 — parsed_command 로부터 Step 1/2 출력을 직접 만드는 rule-base 경로."""

    def test_sufficient_fields_create(self):
        pc = {"field": "무기", "target": "검 A", "action": "생성"}
        ok, exts, cls = _try_rule_base_step12(pc, user_input="검 A 만들어줘")
        assert ok is True
        assert exts[0]["subject"] == "검 A"
        assert exts[0]["action"] == "CREATE"
        assert cls[0]["category"] == "Weapon"

    def test_sufficient_fields_update_with_property_value(self):
        pc = {
            "field": "적",
            "target": "슬라임",
            "action": "수정",
            "property": "HP",
            "value": "200",
        }
        ok, exts, cls = _try_rule_base_step12(pc, user_input="슬라임 HP 를 200 으로")
        assert ok is True
        assert exts[0]["property"] == "HP"
        assert exts[0]["value"] == "200"
        assert cls[0]["category"] == "Enemy"

    def test_bulk_scope_all_skips_rule_base(self):
        pc = {"field": "적", "target": "", "action": "수정", "bulk_scope": "all"}
        ok, _, _ = _try_rule_base_step12(pc, user_input="모든 적 HP 두 배")
        assert ok is False

    def test_unknown_field_label_skips(self):
        pc = {"field": "외계어", "target": "X", "action": "생성"}
        ok, _, _ = _try_rule_base_step12(pc, user_input="X 만들어")
        assert ok is False

    def test_missing_required_skips(self):
        assert _try_rule_base_step12({"field": "무기", "target": "", "action": "생성"}, "x")[0] is False
        assert _try_rule_base_step12({"field": "", "target": "A", "action": "생성"}, "x")[0] is False
        assert _try_rule_base_step12({"field": "무기", "target": "A", "action": ""}, "x")[0] is False

    def test_target_not_in_user_input_skips(self):
        """router target 이 history 오염일 가능성 차단."""
        pc = {"field": "무기", "target": "검 A", "action": "생성"}
        ok, _, _ = _try_rule_base_step12(pc, user_input="슬라임 만들어")
        assert ok is False

    def test_multi_entity_parsed_extractions(self):
        """Task 13 — parsed_extractions 에 2+ 개면 list 전체 변환."""
        pc = {"field": "적", "target": "슬라임", "action": "생성"}
        pe = [
            {"field": "적", "target": "슬라임", "action": "생성"},
            {"field": "적", "target": "드래곤", "action": "생성"},
        ]
        ok, exts, cls = _try_rule_base_step12(
            pc, user_input="슬라임이랑 드래곤 만들어줘", parsed_extractions=pe
        )
        assert ok is True
        assert len(exts) == 2
        assert exts[0]["subject"] == "슬라임"
        assert exts[1]["subject"] == "드래곤"
        assert cls[0]["category"] == "Enemy"
        assert cls[1]["category"] == "Enemy"

    def test_multi_entity_one_missing_falls_back(self):
        """extractions 중 하나라도 부족하면 전체 LLM 경로로 위임."""
        pc = {"field": "적", "target": "슬라임", "action": "생성"}
        pe = [
            {"field": "적", "target": "슬라임", "action": "생성"},
            {"field": "", "target": "X", "action": ""},  # 필드 부족
        ]
        ok, _, _ = _try_rule_base_step12(
            pc, user_input="슬라임이랑 X 만들어", parsed_extractions=pe
        )
        assert ok is False

    def test_single_entity_empty_extractions_noop(self):
        """parsed_extractions 가 빈 list 면 단일 경로로 진행."""
        pc = {"field": "무기", "target": "검 A", "action": "생성"}
        ok, exts, _ = _try_rule_base_step12(pc, "검 A 만들어줘", parsed_extractions=[])
        assert ok is True
        assert len(exts) == 1


class TestBuildReferenceChecks:
    """Task 4 — db_lookup 기반 reference_checks 실제 생성."""

    def _mock_lookup(self, status, **extras):
        import_path = "agent.editor.nodes.definition.lookup_by_name"
        from unittest.mock import patch

        payload = {"status": status, "candidates": [], "suggestions": [], **extras}
        return patch(
            "agent.editor.db_lookup.lookup_by_name", return_value=payload
        ), import_path

    def test_empty_when_no_parsed_command(self):
        assert _build_reference_checks(None, "g", {}) == []
        assert _build_reference_checks({}, "g", {}) == []

    def test_empty_when_no_game_id(self):
        pc = {"field": "무기", "target": "X"}
        assert _build_reference_checks(pc, "", {}) == []

    def test_empty_when_unknown_field(self):
        pc = {"field": "외계어", "target": "X"}
        assert _build_reference_checks(pc, "g", {}) == []

    def test_found_entry(self):
        from unittest.mock import patch

        with patch(
            "agent.editor.db_lookup.lookup_by_name",
            return_value={
                "status": "found",
                "candidates": [],
                "suggestions": [],
                "exact_match": {"id": 3, "name": "슬라임"},
            },
        ):
            out = _build_reference_checks(
                {"field": "적", "target": "슬라임"}, "g", {}
            )
        assert out == [{"category": "Enemy", "name": "슬라임", "status": "found"}]

    def test_not_found_with_suggestions(self):
        from unittest.mock import patch

        with patch(
            "agent.editor.db_lookup.lookup_by_name",
            return_value={
                "status": "not_found",
                "candidates": [],
                "suggestions": [{"id": 1, "name": "슬라임"}],
            },
        ):
            out = _build_reference_checks(
                {"field": "적", "target": "슬라임킹"}, "g", {}
            )
        assert out[0]["status"] == "not_found"
        assert out[0]["suggestions"] == [{"id": 1, "name": "슬라임"}]

    def test_ambiguous_carries_candidates(self):
        from unittest.mock import patch

        cands = [{"id": 1, "name": "A"}, {"id": 2, "name": "A"}]
        with patch(
            "agent.editor.db_lookup.lookup_by_name",
            return_value={
                "status": "ambiguous",
                "candidates": cands,
                "suggestions": [],
            },
        ):
            out = _build_reference_checks({"field": "무기", "target": "A"}, "g", {})
        assert out[0]["status"] == "ambiguous"
        assert out[0]["candidates"] == cands


class TestInferHoldReason:
    def test_not_found_keywords(self):
        assert _infer_hold_reason("슬라임킹을 찾을 수 없습니다") == "not_found"
        assert _infer_hold_reason("해당 항목이 존재하지 않습니다") == "not_found"
        assert _infer_hold_reason("없습니다") == "not_found"

    def test_already_exists_keywords(self):
        assert _infer_hold_reason("이미 있는 이름입니다") == "already_exists"
        assert _infer_hold_reason("이미 존재합니다") == "already_exists"

    def test_default_is_ambiguous_ref(self):
        assert _infer_hold_reason("추가 정보가 필요합니다") == "ambiguous_ref"
        assert _infer_hold_reason("") == "ambiguous_ref"


# ── wrapper 동작 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wrapper_adds_new_contract_fields_on_success():
    mock_core_return = {
        "target_files": ["Weapons.json"],
        "modifications": [{"params": {"name": "검 A"}}],
        "extracted_ids": {},
        "params_sufficient": True,
        "operation_tuples": [{"op": "create", "file": "Weapons.json"}],
    }
    state = {
        "user_input": "검 A 만들어줘",
        "game_id": "test_game",
        "parsed_command": {"field": "무기", "target": "검 A", "action": "생성"},
    }
    with patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(return_value=mock_core_return),
    ):
        result = await definition(state)

    assert result["field"] == "무기"
    assert result["target"] == "검 A"
    assert result["description"] == "검 A 만들어줘"
    # Task 4: reference_checks 는 이제 db_lookup 결과 기반 (여기선 파일 없음 → not_found)
    assert isinstance(result["reference_checks"], list)
    if result["reference_checks"]:
        assert result["reference_checks"][0]["category"] == "Weapon"
        assert result["reference_checks"][0]["name"] == "검 A"
    assert result["resolve"] is True
    assert "hold_reason" not in result
    assert "hold_question" not in result


@pytest.mark.asyncio
async def test_wrapper_sets_hold_on_insufficient_params():
    mock_core_return = {
        "target_files": [],
        "modifications": [],
        "extracted_ids": {},
        "params_sufficient": False,
        "message_for_user": "슬라임킹을 찾을 수 없습니다",
    }
    state = {
        "user_input": "슬라임킹 HP 올려줘",
        "game_id": "test_game",
        "parsed_command": {"field": "적", "target": "슬라임킹", "action": "수정"},
    }
    with patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(return_value=mock_core_return),
    ):
        result = await definition(state)

    assert result["resolve"] is False
    assert result["hold_reason"] == "not_found"
    assert result["hold_question"] == "슬라임킹을 찾을 수 없습니다"
    assert result["field"] == "적"
    assert result["target"] == "슬라임킹"


@pytest.mark.asyncio
async def test_wrapper_writes_to_pending_store_when_conversation_id_present():
    mock_core_return = {
        "target_files": [],
        "modifications": [],
        "extracted_ids": {},
        "params_sufficient": False,
        "message_for_user": "'검 A' 를 찾을 수 없습니다",
    }
    state = {
        "user_input": "검 A 가격 올려줘",
        "game_id": "g",
        "conversation_id": "conv-D1",
        "parsed_command": {"field": "무기", "target": "검 A", "action": "수정"},
    }
    # pending_store 싱글톤을 격리된 인스턴스로 잠시 교체
    fake_store = PendingStore()
    with patch(
        "agent.editor.pending_store._default_store", fake_store
    ), patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(return_value=mock_core_return),
    ):
        await definition(state)

    entry = fake_store.get("conv-D1")
    assert entry is not None
    assert entry.hold_reason == "not_found"
    assert entry.snapshot["field"] == "무기"
    assert entry.snapshot["target"] == "검 A"


@pytest.mark.asyncio
async def test_wrapper_skips_pending_store_when_no_conversation_id():
    mock_core_return = {
        "target_files": [],
        "modifications": [],
        "extracted_ids": {},
        "params_sufficient": False,
        "message_for_user": "찾을 수 없습니다",
    }
    state = {"user_input": "검 A", "game_id": "g"}  # conversation_id 없음
    fake_store = PendingStore()
    with patch(
        "agent.editor.pending_store._default_store", fake_store
    ), patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(return_value=mock_core_return),
    ):
        result = await definition(state)

    assert result["resolve"] is False
    # store 에는 아무것도 저장 안 됨
    assert fake_store._size() == 0


@pytest.mark.asyncio
async def test_wrapper_restores_resumed_snapshot():
    mock_core_return = {
        "target_files": ["Weapons.json"],
        "modifications": [],
        "extracted_ids": {},
        "params_sufficient": True,
    }
    state = {
        "user_input": "어 그래",  # 유저 답
        "game_id": "g",
        "pending_resumed": True,
        "resumed_snapshot": {
            "field": "무기",
            "target": "검 A",
            "user_input_prev": "검 A 만들어줘",
        },
        "parsed_command": {"field": "", "target": "", "action": ""},
    }
    with patch(
        "agent.editor.nodes.definition._definition_core",
        new=AsyncMock(return_value=mock_core_return),
    ) as mock_core:
        await definition(state)

    # 복원된 키들이 state 에 merge 되어 core 가 호출됨
    call_state = mock_core.await_args[0][0]
    # 기존 키는 그대로, 없던 키는 snapshot 에서 복원
    assert call_state["user_input_prev"] == "검 A 만들어줘"
    # 이미 state 에 있던 키는 덮어쓰지 않음
    assert call_state["user_input"] == "어 그래"
