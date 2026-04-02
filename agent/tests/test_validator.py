from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import types
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent.graph.nodes.validator import (
    FileValidationResult,
    StepValidationLLMResult,
    ValidationErrorItem,
    ValidatorOutput,
    validator,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

AGENT_ROOT = PROJECT_ROOT / "agent"
GRAPH_ROOT = AGENT_ROOT / "graph"
NODES_ROOT = GRAPH_ROOT / "nodes"


def load_json_file(json_path: Path) -> Any:
    try:
        with json_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except UnicodeDecodeError:
        with json_path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)


def collect_snapshot_from_paths(json_paths: list[Path]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for json_path in json_paths:
        if not json_path.exists():
            raise FileNotFoundError(f"file not found: {json_path}")
        if not json_path.is_file():
            raise ValueError(f"not a file: {json_path}")
        snapshot[json_path.name] = load_json_file(json_path)
    return snapshot


def collect_snapshot_from_dir(directory: Path | None) -> dict[str, Any]:
    if directory is None:
        return {}
    if not directory.exists():
        raise FileNotFoundError(f"directory not found: {directory}")
    if not directory.is_dir():
        raise ValueError(f"not a directory: {directory}")

    snapshot: dict[str, Any] = {}
    for json_path in sorted(directory.glob("*.json")):
        snapshot[json_path.name] = load_json_file(json_path)
    return snapshot


def merge_snapshots(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(override)
    return merged


def parse_backup_paths(entries: list[str]) -> dict[str, str]:
    backup_paths: dict[str, str] = {}
    for entry in entries:
        file_name, separator, backup_path = entry.partition("=")
        if not separator or not file_name.strip() or not backup_path.strip():
            raise ValueError(f"invalid --backup-path value: {entry}")
        backup_paths[file_name.strip()] = backup_path.strip()
    return backup_paths


def build_default_changes_log(modified_files: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "step_id": index,
            "target_file": file_name,
            "tool_name": f"manual_validate_{Path(file_name).stem.lower()}",
            "success": True,
        }
        for index, file_name in enumerate(modified_files, start=1)
    ]


def build_default_execution_plan(modified_files: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "step_id": index,
            "description": f"{file_name} 파일 수동 validator 실행",
            "action_type": "manual_validate",
            "target_file": file_name,
            "target_info": {},
            "depends_on": [],
            "condition": "",
        }
        for index, file_name in enumerate(modified_files, start=1)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build validator state from JSON file paths and run the state-based validator node."
        )
    )
    parser.add_argument(
        "--modified",
        dest="modified_paths",
        action="append",
        default=[],
        metavar="PATH",
        help="Path to a modified JSON file. Repeat for multiple files.",
    )
    parser.add_argument(
        "--current",
        dest="current_paths",
        action="append",
        default=[],
        metavar="PATH",
        help="Path to the current/original JSON file. Repeat for multiple files.",
    )
    parser.add_argument(
        "--current-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory of current/original JSON snapshots used as the validation baseline.",
    )
    parser.add_argument(
        "--changes-log",
        type=Path,
        default=None,
        metavar="PATH",
        help="Optional JSON file containing a changes_log array.",
    )
    parser.add_argument(
        "--execution-plan",
        type=Path,
        default=None,
        metavar="PATH",
        help="Optional JSON file containing an execution_plan array.",
    )
    parser.add_argument(
        "--backup-path",
        action="append",
        default=[],
        metavar="FILE=PATH",
        help="Optional backup path metadata. Repeat for multiple files.",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=0,
        help="Optional retry count forwarded to the validator state.",
    )
    return parser.parse_args()


def build_state(args: argparse.Namespace) -> dict[str, Any]:
    modified_paths = [Path(value).resolve() for value in args.modified_paths]
    current_paths = [Path(value).resolve() for value in args.current_paths]
    current_dir = args.current_dir.resolve() if args.current_dir is not None else None

    if not modified_paths:
        raise ValueError("at least one --modified path is required")

    current_game_state = collect_snapshot_from_dir(current_dir)
    current_game_state = merge_snapshots(
        current_game_state,
        collect_snapshot_from_paths(current_paths),
    )

    modified_game_state = merge_snapshots(
        current_game_state,
        collect_snapshot_from_paths(modified_paths),
    )

    if args.changes_log is not None:
        changes_log = load_json_file(args.changes_log.resolve())
        if not isinstance(changes_log, list):
            raise ValueError("--changes-log must contain a JSON array")
    else:
        changes_log = build_default_changes_log([path.name for path in modified_paths])

    if args.execution_plan is not None:
        execution_plan = load_json_file(args.execution_plan.resolve())
        if not isinstance(execution_plan, list):
            raise ValueError("--execution-plan must contain a JSON array")
    else:
        execution_plan = build_default_execution_plan([path.name for path in modified_paths])

    backup_paths = parse_backup_paths(args.backup_path)

    state = {
        "execution_plan": execution_plan,
        "current_game_state": current_game_state,
        "modified_game_state": modified_game_state,
        "changes_log": changes_log,
        "backup_paths": backup_paths,
        "retry_count": args.retry_count,
    }
    return state


def ensure_stub_package(module_name: str, package_path: Path) -> None:
    if module_name in sys.modules:
        return

    package = types.ModuleType(module_name)
    package.__file__ = str(package_path / "__init__.py")
    package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    package.__package__ = module_name
    sys.modules[module_name] = package

    parent_name, _, child_name = module_name.rpartition(".")
    if parent_name and parent_name in sys.modules:
        setattr(sys.modules[parent_name], child_name, package)


def load_module_from_path(module_name: str, module_path: Path) -> types.ModuleType:
    existing = sys.modules.get(module_name)
    if isinstance(existing, types.ModuleType):
        return existing

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to create module spec: {module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    parent_name, _, child_name = module_name.rpartition(".")
    if parent_name and parent_name in sys.modules:
        setattr(sys.modules[parent_name], child_name, module)

    return module


def load_validator_callable() -> Any:
    ensure_stub_package("agent.graph", GRAPH_ROOT)
    ensure_stub_package("agent.graph.nodes", NODES_ROOT)

    load_module_from_path("agent.graph.state", GRAPH_ROOT / "state.py")
    validator_module = load_module_from_path(
        "agent.graph.nodes.validator",
        NODES_ROOT / "validator.py",
    )

    validator_callable = getattr(validator_module, "validator", None)
    if validator_callable is None:
        raise ImportError("validator function not found in agent/graph/nodes/validator.py")
    return validator_callable


async def run() -> int:
    args = parse_args()

    try:
        validator = load_validator_callable()
        state = build_state(args)
        result = await validator(state)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, ImportError) as error:
        error_result = ValidatorOutput(
            validation_results=[
                FileValidationResult(
                    target="driver",
                    success=False,
                    errors=[ValidationErrorItem(loc="$", msg=str(error))],
                )
            ],
            validation_summary=str(error),
            success=False,
        ).model_dump(mode="json", exclude_none=True)
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


def main() -> None:
    raise SystemExit(asyncio.run(run()))


def _audio_file() -> dict[str, Any]:
    return {"name": "", "pan": 0, "pitch": 100, "volume": 90}


def _vehicle() -> dict[str, Any]:
    return {"bgm": _audio_file()}


def _actor(actor_id: int, name: str) -> dict[str, Any]:
    return {
        "id": actor_id,
        "name": name,
        "classId": 1,
        "faceName": "Actor1",
        "faceIndex": 0,
        "characterName": "Actor1",
        "characterIndex": 0,
        "battlerName": "Actor1_1",
    }


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


def _base_validator_state() -> dict[str, Any]:
    current_game_state = {
        "Actors.json": [None, _actor(1, "Hero")],
        "Classes.json": [None, {"id": 1, "name": "Warrior"}],
        "System.json": _system([1]),
    }
    modified_game_state = deepcopy(current_game_state)
    modified_game_state["Actors.json"].append(_actor(2, "Sofia"))
    modified_game_state["System.json"]["partyMembers"] = [1, 2]

    return {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "Create actor Sofia with classId 1",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": "Sofia", "class_id": 1},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": "Add Sofia to partyMembers",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"actor_name": "Sofia"},
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
                "tool_name": "structured_actors_create",
                "success": True,
                "description": "Create actor Sofia with classld 1",
            },
            {
                "step_id": 2,
                "target_file": "System.json",
                "tool_name": "structured_system_update",
                "success": True,
                "description": "Add Sofia as a member of party",
            },
        ],
        "backup_paths": {},
        "retry_count": 0,
    }


def _map_event_page(text: str) -> dict[str, Any]:
    return {
        "conditions": {
            "actorId": 1,
            "actorValid": False,
            "itemId": 1,
            "itemValid": False,
            "selfSwitchCh": "A",
            "selfSwitchValid": False,
            "switch1Id": 1,
            "switch1Valid": False,
            "switch2Id": 1,
            "switch2Valid": False,
            "variableId": 1,
            "variableValid": False,
            "variableValue": 0,
        },
        "directionFix": False,
        "image": {
            "characterIndex": 0,
            "characterName": "",
            "direction": 2,
            "pattern": 0,
            "tileId": 0,
        },
        "list": [
            {"code": 101, "indent": 0, "parameters": ["", 0, 0, 2]},
            {"code": 401, "indent": 0, "parameters": [text]},
            {"code": 0, "indent": 0, "parameters": []},
        ],
        "moveFrequency": 3,
        "moveRoute": {
            "list": [{"code": 0, "parameters": []}],
            "repeat": True,
            "skippable": False,
            "wait": False,
        },
        "moveSpeed": 3,
        "moveType": 0,
        "priorityType": 0,
        "stepAnime": False,
        "through": False,
        "trigger": 0,
        "walkAnime": True,
    }


def _map_event(event_id: int, name: str, text: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "name": name,
        "note": "",
        "pages": [_map_event_page(text)],
        "x": 1,
        "y": 1,
    }


def _map_file(event_name: str, text: str) -> dict[str, Any]:
    return {
        "autoplayBgm": False,
        "autoplayBgs": False,
        "battleback1Name": "",
        "battleback2Name": "",
        "bgm": _audio_file(),
        "bgs": _audio_file(),
        "disableDashing": False,
        "displayName": "Village",
        "encounterList": [],
        "encounterStep": 30,
        "height": 2,
        "note": "",
        "parallaxLoopX": False,
        "parallaxLoopY": False,
        "parallaxName": "",
        "parallaxShow": True,
        "parallaxSx": 0,
        "parallaxSy": 0,
        "scrollType": 0,
        "specifyBattleback": False,
        "tilesetId": 1,
        "width": 2,
        "data": [0] * 24,
        "events": [None, _map_event(1, event_name, text)],
    }


def _write_snapshot_files(snapshot: dict[str, Any], directory: Path, prefix: str) -> dict[str, str]:
    written: dict[str, str] = {}
    for file_name, payload in snapshot.items():
        path = directory / f"{prefix}_{file_name}"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        written[file_name] = str(path.resolve())
    return written


def _print_debug_block(title: str, value: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2))


@pytest.fixture(autouse=True)
def mock_step_validation_llm():
    async def _mock_invoke(_messages, structured_output=None):
        if structured_output is None:
            return "ok"
        return structured_output.model_validate(
            {
                "is_match": True,
                "reasoning": "planner step and executor log are aligned",
            }
        )

    with patch(
        "agent.graph.nodes.validator.invoke_llm",
        new=AsyncMock(side_effect=_mock_invoke),
    ):
        yield


@pytest.mark.asyncio
async def test_validator_validates_all_modified_game_state_files():
    state = _base_validator_state()
    result = await validator(state)

    assert result["success"] is True
    assert "retry_count" not in result
    assert "validation_result" not in result
    assert [item["target"] for item in result["validation_results"]] == [
        "Actors.json",
        "Classes.json",
        "System.json",
    ]
    assert result["validation_summary"] == "총 3개 파일이 모두 스키마 검증을 통과했습니다."
    assert all("message" not in item for item in result["validation_results"])
    assert all("error_count" not in item for item in result["validation_results"])


@pytest.mark.asyncio
async def test_validator_supports_snapshot_path_inputs(tmp_path: Path):
    state = _base_validator_state()
    state["current_game_state"]["Map001.json"] = _map_file("Guide", "Welcome to the village.")
    state["modified_game_state"]["Map001.json"] = _map_file(
        "Village Elder",
        "Welcome to Re:Verse.",
    )

    expected = await validator(state)
    current_game_state = _write_snapshot_files(state["current_game_state"], tmp_path, "before")
    modified_game_state = _write_snapshot_files(state["modified_game_state"], tmp_path, "after")
    assert all(Path(path).is_absolute() for path in current_game_state.values())
    assert all(Path(path).is_absolute() for path in modified_game_state.values())

    result = await validator(
        {
            **state,
            "current_game_state": current_game_state,
            "modified_game_state": modified_game_state,
        }
    )

    assert result == expected
    assert result["success"] is True
    assert "retry_count" not in result
    assert "validation_result" not in result
    assert [item["target"] for item in result["validation_results"]] == [
        "Actors.json",
        "Classes.json",
        "System.json",
        "Map001.json",
    ]
    assert result["validation_summary"] == "총 4개 파일이 모두 스키마 검증을 통과했습니다."
    assert all("message" not in item for item in result["validation_results"])
    assert all("error_count" not in item for item in result["validation_results"])


@pytest.mark.asyncio
async def test_validator_schema_failure_increments_retry_count():
    state = _base_validator_state()
    state["modified_game_state"]["Actors.json"][1]["classId"] = "invalid"
    result = await validator(state)

    assert result["success"] is False
    assert result["retry_count"] == 1
    assert result["validation_summary"] == "총 3개 파일 중 1개 파일 검증에 실패했습니다."
    assert "validation_result" not in result
    actor_result = next(
        item for item in result["validation_results"] if item["target"] == "Actors.json"
    )
    assert actor_result["success"] is False
    assert "message" not in actor_result
    assert "error_count" not in actor_result
    assert len(actor_result["errors"]) > 0
    assert sum(len(item["errors"]) for item in result["validation_results"]) > 0


@pytest.mark.asyncio
async def test_validator_validates_only_files_present_in_modified_game_state():
    state = _base_validator_state()
    state["current_game_state"]["Unknown.json"] = {"foo": "bar"}
    state["modified_game_state"] = {
        "Actors.json": deepcopy(state["modified_game_state"]["Actors.json"]),
    }

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is True
    assert contract.retry_count is None
    assert [item.target for item in contract.validation_results] == ["Actors.json"]
    assert "Unknown.json" not in [item.target for item in contract.validation_results]
    assert result["validation_summary"] == "총 1개 파일이 모두 스키마 검증을 통과했습니다."


@pytest.mark.asyncio
async def test_validator_unsupported_schema_returns_standard_shape():
    state = _base_validator_state()
    state["modified_game_state"]["Unknown.json"] = {"foo": "bar"}
    result = await validator(state)

    unknown_result = next(
        item for item in result["validation_results"] if item["target"] == "Unknown.json"
    )
    assert unknown_result["success"] is False
    assert "message" not in unknown_result
    assert "error_count" not in unknown_result
    assert unknown_result["errors"][0]["msg"] == "unsupported schema for Unknown.json"
    assert result["success"] is False
    assert result["retry_count"] == 1
    assert "validation_result" not in result
    assert result["validation_summary"] == "총 4개 파일 중 1개 파일 검증에 실패했습니다."


@pytest.mark.asyncio
async def test_validator_empty_modified_game_state_increments_retry_count():
    state = _base_validator_state()
    state["modified_game_state"] = {}
    state["retry_count"] = 2

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 3
    assert contract.validation_summary == "modified_game_state is missing or empty."
    assert len(contract.validation_results) == 1
    assert contract.validation_results[0].target == "state"
    assert (
        contract.validation_results[0].errors[0].msg == "modified_game_state is missing or empty."
    )


@pytest.mark.asyncio
async def test_validator_missing_execution_plan_returns_state_error():
    state = _base_validator_state()
    state.pop("execution_plan")

    result = await validator(state)
    contract = ValidatorOutput.model_validate(result)

    assert contract.success is False
    assert contract.retry_count == 1
    assert contract.validation_summary == "execution_plan is missing or empty."
    assert len(contract.validation_results) == 1
    assert contract.validation_results[0].target == "state"
    assert contract.validation_results[0].errors[0].msg == "execution_plan is missing or empty."


@pytest.mark.asyncio
async def test_validator_step_validation_missing_executor_log_adds_failure():
    state = _base_validator_state()
    state["changes_log"] = [state["changes_log"][0]]

    result = await validator(state)

    assert result["success"] is False
    assert result["retry_count"] == 1
    step_result = next(item for item in result["validation_results"] if item["target"] == "step:2")
    assert step_result["success"] is False
    assert "changes_log에 없습니다" in step_result["errors"][0]["msg"]


@pytest.mark.asyncio
async def test_validator_step_validation_executor_failure_adds_failure():
    state = _base_validator_state()
    state["changes_log"][1] = {
        "step_id": 2,
        "tool_name": "structured_system_update",
        "success": False,
        "error": "executor failed",
    }

    result = await validator(state)

    assert result["success"] is False
    assert result["retry_count"] == 1
    step_result = next(item for item in result["validation_results"] if item["target"] == "step:2")
    assert "executor failed" in step_result["errors"][0]["msg"]


@pytest.mark.asyncio
async def test_validator_step_validation_llm_mismatch_adds_failure():
    state = _base_validator_state()

    with patch("agent.graph.nodes.validator.invoke_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = StepValidationLLMResult(
            is_match=False,
            reasoning="planner step은 System.json update인데 executor tool_name이 다른 작업으로 판정됨",
        )
        result = await validator(state)

    assert result["success"] is False
    assert result["retry_count"] == 1
    step_result = next(item for item in result["validation_results"] if item["target"] == "step:1")
    assert "planner step은" in step_result["errors"][0]["msg"]


@pytest.mark.asyncio
async def test_validator_query_step_allows_empty_modified_files_when_llm_matches():
    state = _base_validator_state()
    state["execution_plan"] = [
        {
            "step_id": 1,
            "description": "Actors.json에서 Sofia 존재 여부 조회",
            "action_type": "query",
            "target_file": "Actors.json",
            "target_info": {"actor_name": "Sofia"},
            "depends_on": [],
            "condition": "",
        }
    ]
    state["changes_log"] = [
        {
            "step_id": 1,
            "tool_name": "structured_actors_query",
            "success": True,
            "modified_files": [],
        }
    ]

    result = await validator(state)

    assert result["success"] is True
    assert "retry_count" not in result
    assert all(item["target"] != "step:1" for item in result["validation_results"])


@pytest.mark.asyncio
async def test_validator_debug_print_execution_plan_changes_log_and_result():
    state = _base_validator_state()

    result = await validator(state)

    _print_debug_block("execution_plan", state["execution_plan"])
    _print_debug_block("changes_log", state["changes_log"])
    _print_debug_block("validator_result", result)

    assert result["success"] is True


if __name__ == "__main__":
    main()
