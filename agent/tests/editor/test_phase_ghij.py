"""Phase G/H/I 뼈대 동작 단위 테스트."""

from __future__ import annotations

import pytest

from agent.editor.nodes.validator import _collect_soundness_warnings
from agent.editor.nodes.validator.responder import (
    build_final_response,
    build_hold_response,
)

# ── Phase G: soundness_warnings 수집 ────────────────────────────


class TestSoundnessWarnings:
    def test_empty_returns_no_warnings(self):
        assert _collect_soundness_warnings([], []) == []

    def test_entity_id_missing_on_create_warns(self):
        log = [
            {
                "success": True,
                "action": "create",
                "target_file": "Weapons.json",
                "entity_id": None,
            }
        ]
        warnings = _collect_soundness_warnings(log, [])
        assert len(warnings) == 1
        assert "entity_id" in warnings[0]

    def test_skipped_entry_does_not_warn(self):
        log = [{"success": True, "skipped": True, "action": "create"}]
        assert _collect_soundness_warnings(log, []) == []

    def test_all_skipped_with_ops_warns(self):
        log = [{"success": True, "skipped": True}]
        ops = [{"op": "create"}]
        warnings = _collect_soundness_warnings(log, ops)
        assert any("전부 skip" in w for w in warnings)

    def test_failed_entry_not_counted_as_missing_id(self):
        log = [{"success": False, "action": "create", "entity_id": None}]
        assert _collect_soundness_warnings(log, []) == []


# ── Task 14: 룰 카탈로그 확장 ──────────────────────────────────────


class TestExtendedRules:
    def test_equipment_price_zero_warns(self):
        log = [
            {
                "success": True,
                "action": "create",
                "target_file": "Weapons.json",
                "entity_id": 5,
                "data": {"name": "검 A", "price": 0, "params": [0, 0, 10, 0, 0, 0, 0, 0]},
            }
        ]
        warnings = _collect_soundness_warnings(log, [])
        assert any("가격이 0" in w for w in warnings)

    def test_equipment_zero_params_warns(self):
        log = [
            {
                "success": True,
                "action": "create",
                "target_file": "Armors.json",
                "entity_id": 2,
                "data": {"name": "천 갑옷", "price": 100, "params": [0] * 8},
            }
        ]
        warnings = _collect_soundness_warnings(log, [])
        assert any("능력치" in w and "전부 0" in w for w in warnings)

    def test_enemy_zero_hp_warns(self):
        log = [
            {
                "success": True,
                "action": "create",
                "target_file": "Enemies.json",
                "entity_id": 7,
                "data": {"name": "유령", "params": [0, 0, 50, 30, 0, 0, 10, 10]},
            }
        ]
        warnings = _collect_soundness_warnings(log, [])
        assert any("최대 HP" in w for w in warnings)

    def test_event_missing_terminator_warns(self):
        log = [
            {
                "success": True,
                "action": "create_event_from_template",
                "target_file": "Map003.json",
                "entity_id": 1,
                "data": {
                    "pages": [
                        {
                            "list": [
                                {"code": 101, "indent": 0, "parameters": []},
                                {"code": 401, "indent": 0, "parameters": ["text"]},
                                # code 0 누락!
                            ]
                        }
                    ]
                },
            }
        ]
        warnings = _collect_soundness_warnings(log, [])
        assert any("code=0" in w for w in warnings)

    def test_event_with_terminator_no_warning(self):
        log = [
            {
                "success": True,
                "action": "create_common_event",
                "target_file": "CommonEvents.json",
                "entity_id": 1,
                "data": {
                    "list": [
                        {"code": 101, "indent": 0, "parameters": []},
                        {"code": 401, "indent": 0, "parameters": ["text"]},
                        {"code": 0, "indent": 0, "parameters": []},
                    ]
                },
            }
        ]
        warnings = _collect_soundness_warnings(log, [])
        # entity_id 는 있으므로 룰 1 해당 없음. code=0 종결 됐으니 룰 5 해당 없음
        assert warnings == []

    def test_equipment_healthy_create_no_warning(self):
        log = [
            {
                "success": True,
                "action": "create",
                "target_file": "Weapons.json",
                "entity_id": 5,
                "data": {"name": "검 A", "price": 500, "params": [0, 0, 10, 0, 0, 0, 0, 0]},
            }
        ]
        assert _collect_soundness_warnings(log, []) == []


# ── Phase H: responder ──────────────────────────────────────────


class TestResponder:
    def test_hold_response_returns_question(self):
        assert build_hold_response("'검 A' 를 찾을 수 없습니다.") == "'검 A' 를 찾을 수 없습니다."

    def test_hold_response_default_on_empty(self):
        resp = build_hold_response("")
        assert resp  # 빈 문자열이 아님
        assert "추가 정보" in resp or "구체" in resp

    def test_success_without_warnings_returns_clean_template(self):
        log = [
            {
                "success": True,
                "action": "create",
                "target_file": "Weapons.json",
                "data": {"name": "검 A"},
                "entity_id": 12,
            }
        ]
        resp = build_final_response(
            success=True, summary="성공", changes_log=log, soundness_warnings=[]
        )
        assert "검 A" in resp
        assert "참고" not in resp  # warnings 없으면 붙지 않음

    def test_single_warning_rendered_inline(self):
        resp = build_final_response(
            success=True,
            summary="성공",
            changes_log=[
                {
                    "success": True,
                    "action": "create",
                    "target_file": "W.json",
                    "data": {"name": "X"},
                    "entity_id": 1,
                }
            ],
            soundness_warnings=["공격력 대비 가격이 낮습니다"],
        )
        assert "⚠️" in resp
        assert "공격력 대비 가격" in resp

    def test_multiple_warnings_rendered_as_bullets(self):
        resp = build_final_response(
            success=True,
            summary="성공",
            changes_log=[
                {
                    "success": True,
                    "action": "create",
                    "target_file": "W.json",
                    "data": {"name": "X"},
                    "entity_id": 1,
                }
            ],
            soundness_warnings=["경고1", "경고2", "경고3"],
        )
        assert "(3건)" in resp
        assert "- 경고1" in resp
        assert "- 경고2" in resp
        assert "- 경고3" in resp

    def test_failure_path_ignores_warnings_for_now(self):
        resp = build_final_response(
            success=False,
            summary="Schema 검증 실패",
            changes_log=[{"success": False, "error": "bad"}],
            soundness_warnings=["ignored"],
        )
        assert "문제가 발생했습니다" in resp
        # 실패 응답은 soundness_warnings 포장을 skip — 실패 정보가 우선
        assert "⚠️" not in resp


# ── Phase H: synthesizer hold 경로 ──────────────────────────────


@pytest.mark.asyncio
async def test_synthesizer_hold_response_used_when_resolve_false():
    from agent.editor.nodes.synthesizer import synthesizer

    state = {
        "resolve": False,
        "hold_reason": "not_found",
        "hold_question": "'검 A' 를 찾을 수 없습니다. 먼저 만들까요?",
        "intent": "object_update",
    }
    result = await synthesizer(state)
    assert result["final_response"] == "'검 A' 를 찾을 수 없습니다. 먼저 만들까요?"


@pytest.mark.asyncio
async def test_synthesizer_reuses_existing_final_response():
    from agent.editor.nodes.synthesizer import synthesizer

    state = {
        "resolve": True,
        "final_response": "요청을 하나씩 입력해주세요.",  # router terminal 이 set
        "intent": "multi_intent",
    }
    result = await synthesizer(state)
    assert result["final_response"] == "요청을 하나씩 입력해주세요."


@pytest.mark.asyncio
async def test_synthesizer_soundness_warnings_propagate_to_response():
    from agent.editor.nodes.synthesizer import synthesizer

    state = {
        "intent": "object_create",
        "success": True,
        "changes_log": [
            {
                "success": True,
                "action": "create",
                "target_file": "Weapons.json",
                "data": {"name": "검 A"},
                "entity_id": 12,
            }
        ],
        "soundness_warnings": ["공격력 대비 가격이 낮습니다"],
    }
    result = await synthesizer(state)
    assert "검 A" in result["final_response"]
    assert "공격력 대비 가격" in result["final_response"]


# Phase I MCP_TOOL_MAP 엔트리 존재 확인 테스트는 제거됨:
# executor_v2/dispatch.py + handlers/events.py 가 runtime 경로를 이양해
# MCP_TOOL_MAP 의 CommonEvents/Troops 엔트리는 dead. 실제 이벤트 기능 검증은
# `test_events_handler.py` + `test_event_definition.py` 가 담당.
