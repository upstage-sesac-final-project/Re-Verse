"""Tests for the code-first validator node."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.graph.nodes.validator import ValidatorOutput, validator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _actor(actor_id: int, name: str, class_id: int = 1) -> dict[str, Any]:
    return {
        "id": actor_id,
        "name": name,
        "classId": class_id,
        "faceName": "Actor1",
        "faceIndex": 0,
        "characterName": "Actor1",
        "characterIndex": 0,
        "battlerName": "Actor1_1",
    }


def _audio_file() -> dict[str, Any]:
    return {"name": "", "pan": 0, "pitch": 100, "volume": 90}


def _vehicle() -> dict[str, Any]:
    return {"bgm": _audio_file()}


def _system(party_members: list[int]) -> dict[str, Any]:
    return {
        "airship": _vehicle(),
        "battleBgm": _audio_file(),
        "boat": _vehicle(),
        "defeatMe": _audio_file(),
        "gameoverMe": _audio_file(),
        "ship": _vehicle(),
        "terms": {},
        "titleBgm": _audio_file(),
        "victoryMe": _audio_file(),
        "partyMembers": party_members,
        "elements": [None, "Fire"],
        "equipTypes": [None, "Weapon", "Shield"],
        "weaponTypes": [None, "Sword"],
        "armorTypes": [None, "Light"],
        "skillTypes": [None, "Magic"],
    }


def _base_state() -> dict[str, Any]:
    """Actor 2 Sofia를 create한 직후 상태. 스키마·정합성 모두 통과해야 한다."""
    current_actors = [None, _actor(1, "Hero")]
    modified_actors = [None, _actor(1, "Hero"), _actor(2, "Sofia")]

    return {
        "current_game_state": {
            "Actors.json": current_actors,
        },
        "modified_game_state": {
            "Actors.json": modified_actors,
        },
        "changes_log": [
            {
                "step_id": 1,
                "target_file": "Actors.json",
                "action": "query",
                "success": True,
                "query_result": {"not_found": True},
                "modified_files": [],
            },
            {
                "step_id": 2,
                "target_file": "Actors.json",
                "action": "create",
                "success": True,
                "actor_id": 2,
                "actor_name": "Sofia",
                "modified_files": ["Actors.json"],
            },
        ],
        "retry_count": 0,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_all_checks_pass():
    """스키마 검증 통과 + create 정합성 통과 → success=True, retry_count 유지."""
    state = _base_state()

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is True
    assert contract.retry_count == 0
    schema_results = [r for r in contract.validation_results if r.category == "schema"]
    assert all(r.success for r in schema_results)
    assert any(r.target == "Actors.json" for r in schema_results)


@pytest.mark.asyncio
async def test_empty_modified_game_state_returns_state_error():
    """modified_game_state가 비어 있으면 즉시 state error 반환."""
    state = _base_state()
    state["modified_game_state"] = {}
    state["retry_count"] = 1

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 2  # 1 + 1
    assert contract.validation_results[0].target == "state"
    assert contract.validation_results[0].category == "query_consistency"
    assert "modified_game_state is missing or empty" in contract.validation_summary


@pytest.mark.asyncio
async def test_schema_failure_increments_retry_count():
    """스키마 위반(classId=문자열) → category=schema 실패, retry_count+1."""
    state = _base_state()
    state["modified_game_state"]["Actors.json"][1]["classId"] = "invalid"

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 1
    assert "스키마 실패" in contract.validation_summary

    actor_schema_fail = next(
        r
        for r in contract.validation_results
        if r.target == "Actors.json" and r.category == "schema"
    )
    assert not actor_schema_fail.success
    assert len(actor_schema_fail.errors) > 0


@pytest.mark.asyncio
async def test_failed_executor_step_causes_consistency_failure():
    """changes_log에 success=False 항목 → query_consistency 실패."""
    state = _base_state()
    state["changes_log"][1] = {
        "step_id": 2,
        "target_file": "Actors.json",
        "action": "create",
        "success": False,
        "error": "tool call failed",
        "modified_files": [],
    }

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 1
    consistency_fails = [
        r for r in contract.validation_results if r.category == "query_consistency"
    ]
    assert len(consistency_fails) >= 1
    assert consistency_fails[0].target == "Actors.json"


@pytest.mark.asyncio
async def test_create_consistency_failure_when_entity_absent_in_modified_state():
    """changes_log에 create 성공이라 기록됐지만 modified_game_state에 해당 엔티티가 없으면 실패."""
    state = _base_state()
    # Sofia(id=2)를 modified_game_state에서 제거 → create 정합성 실패 유발
    state["modified_game_state"]["Actors.json"] = [None, _actor(1, "Hero")]

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 1
    consistency_fails = [
        r for r in contract.validation_results if r.category == "query_consistency"
    ]
    assert any("Sofia" in (e.msg or "") for r in consistency_fails for e in r.errors)


@pytest.mark.asyncio
async def test_snapshot_path_input_gives_same_result(tmp_path: Path):
    """modified_game_state 값이 파일 경로(str)여도 payload와 동일한 결과를 반환한다."""
    state = _base_state()

    # 파일로 기록
    modified_path = tmp_path / "Actors.json"
    modified_path.write_text(
        json.dumps(state["modified_game_state"]["Actors.json"], ensure_ascii=False),
        encoding="utf-8",
    )
    current_path = tmp_path / "current_Actors.json"
    current_path.write_text(
        json.dumps(state["current_game_state"]["Actors.json"], ensure_ascii=False),
        encoding="utf-8",
    )

    path_state = {
        **state,
        "current_game_state": {"Actors.json": str(current_path)},
        "modified_game_state": {"Actors.json": str(modified_path)},
    }

    result_payload = await validator(state)
    result_path = await validator(path_state)

    assert result_payload["success"] == result_path["success"]
    schema_targets_payload = {
        r["target"] for r in result_payload["validation_results"] if r["category"] == "schema"
    }
    schema_targets_path = {
        r["target"] for r in result_path["validation_results"] if r["category"] == "schema"
    }
    assert schema_targets_payload == schema_targets_path
