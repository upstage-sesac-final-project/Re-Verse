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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

AGENT_ROOT = PROJECT_ROOT / "agent"
GRAPH_ROOT = AGENT_ROOT / "graph"
NODES_ROOT = GRAPH_ROOT / "nodes"

from agent.graph.nodes.validator import _ContentValidationOutput, validator


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

    backup_paths = parse_backup_paths(args.backup_path)

    state = {
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
        error_result = {
            "validation_result": {
                "passed": False,
                "errors": [{"loc": "$", "msg": str(error)}],
                "error_count": 1,
            },
            "validation_results": [
                {
                    "target": "driver",
                    "success": False,
                    "message": "test_validator.py failed to build validator state",
                    "errors": [{"loc": "$", "msg": str(error)}],
                    "error_count": 1,
                }
            ],
            "validation_summary": str(error),
            "success": False,
        }
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
        "current_game_state": current_game_state,
        "modified_game_state": modified_game_state,
        "changes_log": [
            {
                "step_id": 1,
                "target_file": "Actors.json",
                "tool_name": "structured_actors_create",
                "success": True,
                "description": "Create actor Sofia with classId 1",
            },
            {
                "step_id": 2,
                "target_file": "System.json",
                "tool_name": "structured_system_update",
                "success": True,
                "description": "Add Sofia to partyMembers",
            },
        ],
        "backup_paths": {},
        "retry_count": 0,
    }


def _content_result(
    *,
    is_consistent: bool,
    unexpected_changes: list[str] | None = None,
    missing_expected_changes: list[str] | None = None,
    actual_changes: list[str] | None = None,
) -> _ContentValidationOutput:
    return _ContentValidationOutput(
        expected_changes=[
            "Create actor Sofia with classId 1 in Actors.json",
            "Add Sofia to System.partyMembers",
        ],
        actual_changes=actual_changes
        or [
            "Actors.json gains actor Sofia (id=2, classId=1)",
            "System.json partyMembers gains actor id 2",
        ],
        unexpected_changes=unexpected_changes or [],
        missing_expected_changes=missing_expected_changes or [],
        is_consistent=is_consistent,
        reasoning="mocked content validation result",
    )


@pytest.mark.asyncio
async def test_validator_content_validation_success():
    state = _base_validator_state()

    with patch("agent.graph.nodes.validator.invoke_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _content_result(is_consistent=True)
        result = await validator(state)

    content_result = next(item for item in result["validation_results"] if item["target"] == "content_consistency")
    assert content_result["success"] is True
    assert result["success"] is True
    assert content_result["unexpected_changes"] == []
    assert content_result["missing_expected_changes"] == []


@pytest.mark.asyncio
async def test_validator_content_validation_detects_unexpected_change():
    state = _base_validator_state()
    state["modified_game_state"]["Actors.json"][1]["name"] = "Renamed Hero"

    with patch("agent.graph.nodes.validator.invoke_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _content_result(
            is_consistent=False,
            unexpected_changes=["Actors.json actor 1 name changed from Hero to Renamed Hero"],
            actual_changes=[
                "Actors.json gains actor Sofia (id=2, classId=1)",
                "System.json partyMembers gains actor id 2",
                "Actors.json actor 1 name changed from Hero to Renamed Hero",
            ],
        )
        result = await validator(state)

    content_result = next(item for item in result["validation_results"] if item["target"] == "content_consistency")
    assert content_result["success"] is False
    assert result["success"] is False
    assert content_result["unexpected_changes"] == [
        "Actors.json actor 1 name changed from Hero to Renamed Hero"
    ]


@pytest.mark.asyncio
async def test_validator_content_validation_detects_missing_expected_change():
    state = _base_validator_state()
    state["modified_game_state"] = deepcopy(state["current_game_state"])

    with patch("agent.graph.nodes.validator.invoke_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = _content_result(
            is_consistent=False,
            missing_expected_changes=[
                "Actor Sofia creation is missing from Actors.json",
                "System.partyMembers update for Sofia is missing",
            ],
            actual_changes=[],
        )
        result = await validator(state)

    content_result = next(item for item in result["validation_results"] if item["target"] == "content_consistency")
    assert content_result["success"] is False
    assert result["success"] is False
    assert content_result["missing_expected_changes"] == [
        "Actor Sofia creation is missing from Actors.json",
        "System.partyMembers update for Sofia is missing",
    ]


if __name__ == "__main__":
    main()
