"""Code-first validator node.

Executor가 전달한 ``modified_game_state``를 순회하며 파일별 Pydantic schema
validation만 수행한다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent.graph.state import AgentState
from agent.schemas.actors import ActorsFile
from agent.schemas.animations import AnimationsFile
from agent.schemas.armors import ArmorsFile
from agent.schemas.classes import ClassesFile
from agent.schemas.enemies import EnemiesFile
from agent.schemas.items import ItemsFile
from agent.schemas.skills import SkillsFile
from agent.schemas.states import StatesFile
from agent.schemas.system import System
from agent.schemas.weapons import WeaponsFile
from agent.graph.utils.game_state_json import load_snapshot_payload
from agent.prompts.validator_prompt import build_prompt as build_validator_prompt

logger = logging.getLogger(__name__)

# input 받는 부분이 날라감... 확인

SCHEMA_MAP: dict[str, type[Any]] = {
    "Actors.json": ActorsFile,
    "Animations.json": AnimationsFile,
    "Armors.json": ArmorsFile,
    "Classes.json": ClassesFile,
    "Enemies.json": EnemiesFile,
    "Items.json": ItemsFile,
    "Skills.json": SkillsFile,
    "States.json": StatesFile,
    "System.json": System,
    "Weapons.json": WeaponsFile,
}

_SCHEMA_MAP_NORMALIZED = {name.lower(): model for name, model in SCHEMA_MAP.items()}


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def resolve_schema(file_name: str) -> type[Any] | None:
    return _SCHEMA_MAP_NORMALIZED.get(Path(file_name).name.strip().lower())


def build_file_result(
    target: str,
    success: bool,
    message: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_errors = errors or []
    return {
        "target": target,
        "success": success,
        "message": message,
        "errors": normalized_errors,
        "error_count": len(normalized_errors),
    }


def build_output(
    validation_results: list[dict[str, Any]],
    validation_summary: str,
    success: bool,
) -> dict[str, Any]:
    errors = [error for item in validation_results for error in item.get("errors", [])]
    return {
        "validation_result": {
            "passed": success,
            "errors": errors,
            "error_count": sum(int(item.get("error_count", 0)) for item in validation_results),
        },
        "validation_results": validation_results,
        "validation_summary": validation_summary,
        "success": success,
    }


def build_validation_summary(validation_results: list[dict[str, Any]]) -> str:
    if not validation_results:
        return "검증할 파일이 없어 validator를 종료했습니다."

    failed_count = sum(1 for item in validation_results if not item.get("success"))
    if failed_count == 0:
        return f"총 {len(validation_results)}개 파일이 모두 스키마 검증을 통과했습니다."
    return f"총 {len(validation_results)}개 파일 중 {failed_count}개 파일 검증에 실패했습니다."


def build_state_error(message: str) -> dict[str, Any]:
    validation_results = [
        build_file_result(
            target="state",
            success=False,
            message="Validator state is invalid",
            errors=[{"loc": "$", "msg": message}],
        )
    ]
    return build_output(
        validation_results=validation_results,
        validation_summary=message,
        success=False,
    )


def validate_single_file(file_name: str, data: Any) -> dict[str, Any]:
    model = resolve_schema(file_name)
    if model is None:
        return build_file_result(
            target=file_name,
            success=False,
            message=f"{file_name} validation failed",
            errors=[{"loc": "$", "msg": f"unsupported schema for {file_name}"}],
        )

    try:
        model.model_validate(data)
    except ValidationError as error:
        return False, to_jsonable(error.errors())

    normalized = validated.model_dump(mode="json", exclude_unset=True)
    mismatch = find_first_difference(normalized, original_data)
    if mismatch is not None:
        location, raw_value, schema_value = mismatch
        return False, [
            {
                "loc": location,
                "msg": "input does not strictly match schema",
                "raw": to_jsonable(raw_value),
                "schema": to_jsonable(schema_value),
                "target": target_name,
            }
        ]

    return True, []


def extract_validation_inputs(
    state: AgentState,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, str], int]:
    current_game_state = state.get("current_game_state", {})
    modified_game_state = state.get("modified_game_state", {})
    changes_log = state.get("changes_log", [])
    backup_paths = state.get("backup_paths", {})
    retry_count = state.get("retry_count", 0)

    if not isinstance(current_game_state, dict):
        current_game_state = {}
    if not isinstance(modified_game_state, dict):
        modified_game_state = {}
    if not isinstance(changes_log, list):
        changes_log = []
    if not isinstance(backup_paths, dict):
        backup_paths = {}
    try:
        retry_count = int(retry_count)
    except (TypeError, ValueError):
        retry_count = 0

    return current_game_state, modified_game_state, changes_log, backup_paths, retry_count


def detect_modified_files(
    current_game_state: dict[str, Any],
    modified_game_state: dict[str, Any],
) -> list[str]:
    modified_files: list[str] = []
    for file_name, modified_value in modified_game_state.items():
        if file_name not in current_game_state:
            modified_files.append(file_name)
            continue
        current_value = current_game_state[file_name]
        if load_snapshot_payload(current_value) != load_snapshot_payload(modified_value):
            modified_files.append(file_name)
    return sorted(modified_files)


def merge_reference_snapshots(
    current_game_state: dict[str, Any],
    modified_game_state: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for k, v in current_game_state.items():
        merged[k] = load_snapshot_payload(v)
    for k, v in modified_game_state.items():
        merged[k] = load_snapshot_payload(v)
    return merged


def collect_ids(snapshot: Any) -> set[int]:
    ids: set[int] = set()
    if not isinstance(snapshot, list):
        return ids

    for entry in snapshot:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if isinstance(entry_id, int):
            ids.add(entry_id)
    return ids


def format_object_loc(base_loc: str, key: str) -> str:
    if base_loc == "$":
        return f"$.{key}"
    return f"{base_loc}.{key}"


def parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if stripped == "":
        return ""
    if stripped.lstrip("-").isdigit():
        return int(stripped)
    return stripped


def parse_path_segment(segment: str) -> tuple[str, str | None]:
    bracket_start = segment.find("[")
    if bracket_start < 0:
        return segment, None

    bracket_end = segment.rfind("]")
    if bracket_end < bracket_start:
        return segment, None

    name = segment[:bracket_start]
    selector = segment[bracket_start + 1 : bracket_end]
    return name, selector


def extract_path_values(data: Any, source_path: str) -> list[tuple[str, Any]]:
    segments = [segment for segment in source_path.split(".") if segment]
    return _extract_path_values(data, segments, "$")


def _extract_path_values(node: Any, segments: list[str], loc: str) -> list[tuple[str, Any]]:
    if not segments:
        return [(loc, node)]

    if isinstance(node, list):
        values: list[tuple[str, Any]] = []
        for index, item in enumerate(node):
            if item is None:
                continue
            values.extend(_extract_path_values(item, segments, f"{loc}[{index}]"))
        return values

    if not isinstance(node, dict):
        return []

    name, selector = parse_path_segment(segments[0])
    if name not in node:
        return []

    child = node[name]
    child_loc = format_object_loc(loc, name)
    rest = segments[1:]

    if selector is None:
        return _extract_path_values(child, rest, child_loc)

    if not isinstance(child, list):
        return []

    values: list[tuple[str, Any]] = []
    if selector == "":
        for index, item in enumerate(child):
            values.extend(_extract_path_values(item, rest, f"{child_loc}[{index}]"))
        return values

    if "=" not in selector:
        return []

    field_name, raw_expected = selector.split("=", 1)
    expected_value = parse_scalar(raw_expected)

    for index, item in enumerate(child):
        if not isinstance(item, dict):
            continue
        if item.get(field_name) != expected_value:
            continue
        values.extend(_extract_path_values(item, rest, f"{child_loc}[{index}]"))
    return values


def build_reference_error(loc: str, msg: str, input_value: Any, expected: str) -> dict[str, Any]:
    return {
        "loc": loc,
        "msg": msg,
        "input": to_jsonable(input_value),
        "expected": expected,
    }


def validate_reference_value(
    *,
    loc: str,
    value: Any,
    target_kind: str,
    target_name: str,
    reference_snapshots: dict[str, Any],
    allow_values: frozenset[Any],
) -> list[dict[str, Any]]:
    if value in allow_values or value is None:
        return []

    if target_kind == "db":
        target_snapshot = reference_snapshots.get(target_name)
        if target_snapshot is None:
            return []

        target_ids = collect_ids(target_snapshot)
        if value in target_ids:
            return []

        return [
            build_reference_error(
                loc,
                f"Referenced value {value} does not exist in {target_name}",
                value,
                f"existing {target_name} id",
            )
        ]

    if target_kind == "system_index":
        system_snapshot = reference_snapshots.get("System.json")
        if not isinstance(system_snapshot, dict):
            return []

        target_array = system_snapshot.get(target_name)
        if not isinstance(target_array, list):
            return []

        if not isinstance(value, int):
            return [
                build_reference_error(
                    loc,
                    f"Referenced value {value} is not a valid System.{target_name} index",
                    value,
                    f"valid System.{target_name} index",
                )
            ]

        if 0 <= value < len(target_array) and target_array[value] not in (None, ""):
            return []

        return [
            build_reference_error(
                loc,
                f"Referenced value {value} is not a valid System.{target_name} index",
                value,
                f"valid System.{target_name} index",
            )
        ]

    return []


def validate_reference_rule(
    rule: ReferenceRule,
    data: Any,
    reference_snapshots: dict[str, Any],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for loc, value in extract_path_values(data, rule.source_path):
        errors.extend(
            validate_reference_value(
                loc=loc,
                value=value,
                target_kind=rule.target_kind,
                target_name=rule.target_name,
                reference_snapshots=reference_snapshots,
                allow_values=rule.allow_values,
            )
        )
    return errors


def validate_trait_references(
    file_name: str,
    data: Any,
    reference_snapshots: dict[str, Any],
) -> list[dict[str, Any]]:
    if file_name not in TRAIT_REFERENCE_FILES:
        return []

    errors: list[dict[str, Any]] = []
    for loc, trait in extract_path_values(data, "traits[]"):
        if not isinstance(trait, dict):
            continue
        code = trait.get("code")
        data_id = trait.get("dataId")
        target = TRAIT_REFERENCE_TARGETS.get(code) if isinstance(code, int) else None
        if target is None:
            continue

        errors.extend(
            validate_reference_value(
                loc=format_object_loc(loc, "dataId"),
                value=data_id,
                target_kind=target[0],
                target_name=target[1],
                reference_snapshots=reference_snapshots,
                allow_values=frozenset(),
            )
        )
    return errors


def validate_references(
    file_name: str,
    data: Any,
    reference_snapshots: dict[str, Any],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    for rule in DB_REFERENCE_RULES:
        if rule.source_file == file_name:
            errors.extend(validate_reference_rule(rule, data, reference_snapshots))

    for rule in SYSTEM_INDEX_RULES:
        if rule.source_file == file_name:
            errors.extend(validate_reference_rule(rule, data, reference_snapshots))

    errors.extend(validate_trait_references(file_name, data, reference_snapshots))
    return errors


def collect_related_steps(file_name: str, changes_log: list[dict[str, Any]]) -> list[int]:
    related_steps: list[int] = []
    spec = resolve_schema(file_name)
    canonical_token = spec.canonical_name if spec is not None else Path(file_name).stem.lower()

    for entry in changes_log:
        if not isinstance(entry, dict):
            continue

        matched = False
        target_file = entry.get("target_file")
        if isinstance(target_file, str) and Path(target_file).name == file_name:
            matched = True

        tool_name = str(entry.get("tool_name", "")).lower()
        if not matched and canonical_token in tool_name:
            matched = True

        if not matched:
            continue

        step_value = entry.get("step_id", entry.get("step"))
        try:
            step_id = int(step_value)
        except (TypeError, ValueError):
            continue

        if step_id not in related_steps:
            related_steps.append(step_id)

    return related_steps


def validate_single_file(
    file_name: str,
    data: Any,
    reference_snapshots: dict[str, Any],
    backup_paths: dict[str, str],
    changes_log: list[dict[str, Any]],
) -> dict[str, Any]:
    backup_path = backup_paths.get(file_name)
    related_steps = collect_related_steps(file_name, changes_log)
    spec = resolve_schema(file_name)

    if spec is None:
        return build_file_result(
            target=file_name,
            success=False,
            message=f"{file_name} validation failed",
            errors=[
                {
                    "loc": "$",
                    "msg": f"unsupported schema for {file_name}",
                    "available": available_schemas(),
                }
            ],
            backup_path=backup_path,
            related_steps=related_steps,
        )

    try:
        model = load_model(spec)
    except Exception as error:
        logger.exception("Validator schema load failed for %s", file_name)
        return build_file_result(
            target=file_name,
            success=False,
            message=f"{file_name} validation failed",
            errors=[{"loc": "$", "msg": f"failed to load schema: {error}"}],
            backup_path=backup_path,
            related_steps=related_steps,
        )

    schema_ok, schema_errors = validate_with_model(model, data, file_name)
    if not schema_ok:
        return build_file_result(
            target=file_name,
            success=False,
            message=f"{file_name} schema validation failed",
            errors=to_jsonable(error.errors()),
        )

    return build_file_result(
        target=file_name,
        success=True,
        message=f"{file_name} validation passed",
        errors=[],
    )


async def validator(state: AgentState) -> dict[str, Any]:
    modified_game_state = state.get("modified_game_state", {})
    retry_count = state.get("retry_count", 0)

    try:
        retry_count = int(retry_count)
    except (TypeError, ValueError):
        retry_count = 0

    if not isinstance(modified_game_state, dict) or not modified_game_state:
        result = build_state_error("modified_game_state is missing or empty.")
        result["retry_count"] = retry_count + 1
        return result

    validation_results = [
        validate_single_file(file_name, data) for file_name, data in modified_game_state.items()
        validate_single_file(
            file_name=file_name,
            data=load_snapshot_payload(modified_game_state[file_name]),
            reference_snapshots=reference_snapshots,
            backup_paths=backup_paths,
            changes_log=changes_log,
        )
        for file_name in modified_files
    ]
    success = all(item.get("success") for item in validation_results)
    validation_summary = build_validation_summary(validation_results)

    logger.info(
        "Validator finished | validated_files=%d | success=%s",
        len(validation_results),
        success,
    )

    result = build_output(
        validation_results=validation_results,
        validation_summary=validation_summary,
        success=success,
    )
    if not success:
        result["retry_count"] = retry_count + 1
    return result
