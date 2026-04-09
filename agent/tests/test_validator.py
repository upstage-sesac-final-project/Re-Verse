from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from agent.graph.nodes.validator import ValidatorOutput, validator


def _audio_file() -> dict[str, Any]:
    return {"name": "", "pan": 0, "pitch": 100, "volume": 90}


def _vehicle() -> dict[str, Any]:
    return {"bgm": _audio_file()}


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


def _class(class_id: int, name: str) -> dict[str, Any]:
    return {"id": class_id, "name": name, "note": ""}


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
    current_game_state = {
        "Actors.json": [None, _actor(1, "Hero")],
        "Classes.json": [None, _class(1, "Warrior")],
        "System.json": _system([1]),
    }
    modified_game_state = deepcopy(current_game_state)
    modified_game_state["Actors.json"].append(_actor(2, "Sofia"))

    return {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "Query Sofia in Actors.json",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_name": "Sofia"},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": "Create Sofia when missing",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": "Sofia"},
                "depends_on": [1],
                "condition": "create when query result is not_found",
            },
        ],
        "current_game_state": current_game_state,
        "modified_game_state": modified_game_state,
        "changes_log": [
            {
                "step_id": 1,
                "target_file": "Actors.json",
                "action": "query",
                "tool_name": "structured_actors_query",
                "success": True,
                "query_result": {
                    "query_type": "query",
                    "query": {"actor_name": "Sofia"},
                    "hit_count": 0,
                    "matched_ids": [],
                    "not_found": True,
                },
                "modified_files": [],
            },
            {
                "step_id": 2,
                "target_file": "Actors.json",
                "action": "create",
                "tool_name": "structured_actors_create",
                "success": True,
                "actor_id": 2,
                "actor_name": "Sofia",
                "modified_files": ["Actors.json"],
            },
        ],
        "retry_count": 0,
    }


def _write_snapshot_files(snapshot: dict[str, Any], directory: Path, prefix: str) -> dict[str, str]:
    written: dict[str, str] = {}
    for file_name, payload in snapshot.items():
        path = directory / f"{prefix}_{file_name}"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        written[file_name] = str(path.resolve())
    return written


@pytest.mark.asyncio
async def test_validator_returns_fixed_top_level_contract_and_retry_count_on_success():
    state = _base_state()
    state["retry_count"] = 2

    result = await validator(state)

    assert set(result) == {"validation_results", "validation_summary", "success", "retry_count"}
    assert result["success"] is True
    assert result["retry_count"] == 2
    assert "validation_result" not in result
    assert result["validation_summary"] == "스키마 검증과 query 결과 기반 정합성 검증을 모두 통과했습니다."
    assert [item["target"] for item in result["validation_results"]] == [
        "Actors.json",
        "Classes.json",
        "System.json",
    ]
    assert all(item["category"] == "schema" for item in result["validation_results"])


@pytest.mark.asyncio
async def test_validator_supports_snapshot_path_inputs_without_fallback(tmp_path: Path):
    state = _base_state()
    expected = await validator(state)

    result = await validator(
        {
            **state,
            "current_game_state": _write_snapshot_files(state["current_game_state"], tmp_path, "before"),
            "modified_game_state": _write_snapshot_files(state["modified_game_state"], tmp_path, "after"),
        }
    )

    assert result == expected
    assert result["retry_count"] == 0


@pytest.mark.asyncio
async def test_validator_schema_failure_increments_retry_count_and_uses_schema_category():
    state = _base_state()
    state["modified_game_state"]["Actors.json"][1]["classId"] = "invalid"

    result = await validator(state)

    assert result["success"] is False
    assert result["retry_count"] == 1
    assert result["validation_summary"] == "스키마 실패 1건이 있습니다."
    actor_result = next(
        item for item in result["validation_results"] if item["target"] == "Actors.json"
    )
    assert actor_result["category"] == "schema"
    assert actor_result["success"] is False
    assert actor_result["errors"]


@pytest.mark.asyncio
async def test_validator_validates_only_files_present_in_modified_game_state():
    state = _base_state()
    state["current_game_state"]["Unknown.json"] = {"foo": "bar"}
    state["modified_game_state"] = {"Actors.json": deepcopy(state["modified_game_state"]["Actors.json"])}

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is True
    assert contract.retry_count == 0
    assert [item.target for item in contract.validation_results] == ["Actors.json"]


@pytest.mark.asyncio
async def test_validator_unsupported_schema_returns_standard_shape():
    state = _base_state()
    state["modified_game_state"]["Unknown.json"] = {"foo": "bar"}

    result = await validator(state)

    unknown_result = next(
        item for item in result["validation_results"] if item["target"] == "Unknown.json"
    )
    assert unknown_result["category"] == "schema"
    assert unknown_result["success"] is False
    assert unknown_result["errors"][0]["msg"] == "unsupported schema for Unknown.json"
    assert result["retry_count"] == 1


@pytest.mark.asyncio
async def test_validator_empty_modified_game_state_returns_state_error():
    state = _base_state()
    state["modified_game_state"] = {}
    state["retry_count"] = 2

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 3
    assert contract.validation_results[0].target == "state"
    assert contract.validation_results[0].category == "query_consistency"
    assert contract.validation_summary == "modified_game_state is missing or empty."


@pytest.mark.asyncio
async def test_validator_allows_missing_execution_plan_when_log_evidence_is_sufficient():
    state = _base_state()
    state.pop("execution_plan")

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is True
    assert contract.retry_count == 0
    assert contract.validation_summary == "스키마 검증과 query 결과 기반 정합성 검증을 모두 통과했습니다."


@pytest.mark.asyncio
async def test_validator_actor_update_target_mismatch_fails():
    current_game_state = {
        "Actors.json": [None, _actor(1, "Hero"), None, None, _actor(4, "Sofia")],
        "Classes.json": [None, _class(1, "Warrior"), _class(2, "Mage")],
        "System.json": _system([1, 4]),
    }
    modified_game_state = deepcopy(current_game_state)
    modified_game_state["Actors.json"][1]["classId"] = 2

    state = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "Query Sofia in Actors.json",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_name": "Sofia"},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": "Update Sofia class",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"actor_id": 1, "class_id": 2},
                "depends_on": [1],
                "condition": "",
            },
        ],
        "current_game_state": current_game_state,
        "modified_game_state": modified_game_state,
        "changes_log": [
            {
                "step_id": 1,
                "target_file": "Actors.json",
                "action": "query",
                "tool_name": "structured_actors_query",
                "success": True,
                "query_result": {
                    "query_type": "query",
                    "query": {"actor_name": "Sofia"},
                    "hit_count": 1,
                    "matched_ids": [4],
                    "not_found": False,
                },
                "modified_files": [],
            },
            {
                "step_id": 2,
                "target_file": "Actors.json",
                "action": "update",
                "tool_name": "structured_actors_update",
                "success": True,
                "actor_id": 1,
                "class_id": 2,
                "modified_files": ["Actors.json"],
            },
        ],
        "retry_count": 0,
    }

    result = await validator(state)

    failure = next(item for item in result["validation_results"] if item["category"] == "query_consistency")
    assert failure["target"] == "Actors.json"
    assert failure["errors"][0]["msg"] == "query 결과는 actor_id=4인데 후속 update는 actor_id=1를 대상으로 했습니다."
    assert result["retry_count"] == 1


@pytest.mark.asyncio
async def test_validator_existing_create_skip_succeeds():
    state = _base_state()
    state["current_game_state"]["Actors.json"].append(_actor(2, "Sofia"))
    state["modified_game_state"] = deepcopy(state["current_game_state"])
    state["changes_log"] = [
        {
            "step_id": 1,
            "target_file": "Actors.json",
            "action": "query",
            "tool_name": "structured_actors_query",
            "success": True,
            "query_result": {
                "query_type": "query",
                "query": {"actor_name": "Sofia"},
                "hit_count": 1,
                "matched_ids": [2],
                "not_found": False,
            },
            "modified_files": [],
        },
        {
            "step_id": 2,
            "target_file": "Actors.json",
            "action": "create",
            "tool_name": "structured_skip_create",
            "success": True,
            "skipped": True,
            "skip_reason": "already exists",
            "modified_files": [],
        },
    ]

    result = await validator(state)

    assert result["success"] is True
    assert result["retry_count"] == 0
    assert all(item["category"] == "schema" for item in result["validation_results"])


@pytest.mark.asyncio
async def test_validator_missing_query_evidence_fails():
    state = _base_state()
    state["changes_log"] = [
        {
            "step_id": 2,
            "target_file": "Actors.json",
            "action": "create",
            "tool_name": "structured_skip_create",
            "success": True,
            "skipped": True,
            "skip_reason": "already exists",
            "modified_files": [],
        }
    ]

    result = await validator(state)

    failure = next(item for item in result["validation_results"] if item["category"] == "query_consistency")
    assert failure["target"] == "Actors.json"
    assert failure["errors"][0]["msg"] == "query 기반 판단이 필요한 create인데 참조 가능한 query_result 근거 로그가 없습니다."
    assert result["retry_count"] == 1


@pytest.mark.asyncio
async def test_validator_unsupported_structured_step_is_executor_capability():
    state = _base_state()
    state["execution_plan"] = [
        {
            "step_id": 1,
            "description": "Delete skill",
            "action_type": "delete",
            "target_file": "Skills.json",
            "target_info": {"skill_id": 1},
            "depends_on": [],
            "condition": "",
        }
    ]
    state["changes_log"] = [
        {
            "step_id": 1,
            "target_file": "Skills.json",
            "action": "delete",
            "tool_name": "structured_skills_delete",
            "success": False,
            "stderr": "[UNSUPPORTED_STRUCTURED_STEP] target_file=Skills.json action=delete message=unsupported",
        }
    ]

    result = await validator(state)

    capability = next(item for item in result["validation_results"] if item["category"] == "executor_capability")
    assert capability["target"] == "Skills.json"
    assert result["validation_summary"] == "executor capability 실패 1건이 있습니다."
    assert result["retry_count"] == 1


@pytest.mark.asyncio
async def test_validator_uses_latest_retry_logs_only():
    state = _base_state()
    state["changes_log"] = [
        {
            "step_id": 1,
            "target_file": "Actors.json",
            "action": "query",
            "tool_name": "structured_actors_query",
            "success": True,
            "query_result": {
                "query_type": "query",
                "query": {"actor_name": "Sofia"},
                "hit_count": 1,
                "matched_ids": [2],
                "not_found": False,
            },
            "modified_files": [],
        },
        {
            "step_id": 2,
            "target_file": "Actors.json",
            "action": "create",
            "tool_name": "structured_skip_create",
            "success": True,
            "skipped": True,
            "skip_reason": "already exists",
            "modified_files": [],
        },
        {
            "step_id": 1,
            "target_file": "Actors.json",
            "action": "query",
            "tool_name": "structured_actors_query",
            "success": True,
            "query_result": {
                "query_type": "query",
                "query": {"actor_name": "Sofia"},
                "hit_count": 0,
                "matched_ids": [],
                "not_found": True,
            },
            "modified_files": [],
        },
        {
            "step_id": 2,
            "target_file": "Actors.json",
            "action": "create",
            "tool_name": "structured_actors_create",
            "success": True,
            "actor_id": 2,
            "actor_name": "Sofia",
            "modified_files": ["Actors.json"],
        },
    ]

    result = await validator(state)

    assert result["success"] is True
    assert result["retry_count"] == 0
    assert all(item["success"] for item in result["validation_results"])


@pytest.mark.asyncio
async def test_validator_limited_fallback_matches_same_actor_instead_of_latest_query():
    state = _base_state()
    state.pop("execution_plan")
    state["changes_log"] = [
        {
            "step_id": 1,
            "target_file": "Actors.json",
            "action": "query",
            "tool_name": "structured_actors_query",
            "success": True,
            "query_result": {
                "query_type": "query",
                "query": {"actor_name": "Sofia"},
                "hit_count": 0,
                "matched_ids": [],
                "not_found": True,
            },
            "modified_files": [],
        },
        {
            "step_id": 2,
            "target_file": "Actors.json",
            "action": "query",
            "tool_name": "structured_actors_query",
            "success": True,
            "query_result": {
                "query_type": "query",
                "query": {"actor_name": "Hero"},
                "hit_count": 1,
                "matched_ids": [1],
                "not_found": False,
            },
            "modified_files": [],
        },
        {
            "step_id": 3,
            "target_file": "Actors.json",
            "action": "create",
            "tool_name": "structured_actors_create",
            "success": True,
            "actor_id": 2,
            "actor_name": "Sofia",
            "modified_files": ["Actors.json"],
        },
    ]

    result = await validator(state)

    assert result["success"] is True
    assert result["retry_count"] == 0


@pytest.mark.asyncio
async def test_validator_limited_fallback_rejects_unrelated_actor_query():
    state = _base_state()
    state.pop("execution_plan")
    state["changes_log"] = [
        {
            "step_id": 1,
            "target_file": "Actors.json",
            "action": "query",
            "tool_name": "structured_actors_query",
            "success": True,
            "query_result": {
                "query_type": "query",
                "query": {"actor_name": "Hero"},
                "hit_count": 1,
                "matched_ids": [1],
                "not_found": False,
            },
            "modified_files": [],
        },
        {
            "step_id": 2,
            "target_file": "Actors.json",
            "action": "create",
            "tool_name": "structured_actors_create",
            "success": True,
            "actor_id": 2,
            "actor_name": "Sofia",
            "modified_files": ["Actors.json"],
        },
    ]

    result = await validator(state)

    failure = next(item for item in result["validation_results"] if item["category"] == "query_consistency")
    assert failure["target"] == "Actors.json"
    assert failure["errors"][0]["msg"] == "query 기반 판단이 필요한 create인데 참조 가능한 query_result 근거 로그가 없습니다."
    assert result["retry_count"] == 1
