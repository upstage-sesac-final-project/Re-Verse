"""State-based validator node for modified game snapshots."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

import agent.schemas as schemas_pkg
from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.validator_prompt import build_prompt as build_validator_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchemaSpec:
    canonical_name: str
    module_name: str
    model_name: str


@dataclass(frozen=True)
class ReferenceRule:
    source_file: str
    source_path: str
    target_kind: str
    target_name: str
    allow_values: frozenset[Any] = frozenset()


class _ContentValidationOutput(BaseModel):
    expected_changes: list[str] = Field(default_factory=list)
    actual_changes: list[str] = Field(default_factory=list)
    unexpected_changes: list[str] = Field(default_factory=list)
    missing_expected_changes: list[str] = Field(default_factory=list)
    is_consistent: bool = Field(description="Whether actual changes match intended changes.")
    reasoning: str = Field(default="", description="Short explanation of the consistency judgment.")


SCHEMA_REGISTRY: dict[str, SchemaSpec] = {
    "actor": SchemaSpec("actors", "actors", "ActorsFile"),
    "actors": SchemaSpec("actors", "actors", "ActorsFile"),
    "actors.json": SchemaSpec("actors", "actors", "ActorsFile"),
    "animation": SchemaSpec("animations", "animations", "AnimationsFile"),
    "animations": SchemaSpec("animations", "animations", "AnimationsFile"),
    "animations.json": SchemaSpec("animations", "animations", "AnimationsFile"),
    "armor": SchemaSpec("armors", "armors", "ArmorsFile"),
    "armors": SchemaSpec("armors", "armors", "ArmorsFile"),
    "armors.json": SchemaSpec("armors", "armors", "ArmorsFile"),
    "class": SchemaSpec("classes", "classes", "ClassesFile"),
    "classes": SchemaSpec("classes", "classes", "ClassesFile"),
    "classes.json": SchemaSpec("classes", "classes", "ClassesFile"),
    "enemy": SchemaSpec("enemies", "enemies", "EnemiesFile"),
    "enemies": SchemaSpec("enemies", "enemies", "EnemiesFile"),
    "enemies.json": SchemaSpec("enemies", "enemies", "EnemiesFile"),
    "item": SchemaSpec("items", "items", "ItemsFile"),
    "items": SchemaSpec("items", "items", "ItemsFile"),
    "items.json": SchemaSpec("items", "items", "ItemsFile"),
    "skill": SchemaSpec("skills", "skills", "SkillsFile"),
    "skills": SchemaSpec("skills", "skills", "SkillsFile"),
    "skills.json": SchemaSpec("skills", "skills", "SkillsFile"),
    "state": SchemaSpec("states", "states", "StatesFile"),
    "states": SchemaSpec("states", "states", "StatesFile"),
    "states.json": SchemaSpec("states", "states", "StatesFile"),
    "system": SchemaSpec("system", "system", "System"),
    "system.json": SchemaSpec("system", "system", "System"),
    "troop": SchemaSpec("troops", "troops", "TroopsFile"),
    "troops": SchemaSpec("troops", "troops", "TroopsFile"),
    "troops.json": SchemaSpec("troops", "troops", "TroopsFile"),
    "weapon": SchemaSpec("weapons", "weapons", "WeaponsFile"),
    "weapons": SchemaSpec("weapons", "weapons", "WeaponsFile"),
    "weapons.json": SchemaSpec("weapons", "weapons", "WeaponsFile"),
}

DB_REFERENCE_RULES: tuple[ReferenceRule, ...] = (
    ReferenceRule("Actors.json", "classId", "db", "Classes.json"),
    ReferenceRule("Classes.json", "learnings[].skillId", "db", "Skills.json"),
    ReferenceRule("Skills.json", "animationId", "db", "Animations.json", frozenset({0, -1})),
    ReferenceRule("Skills.json", "effects[code=21].dataId", "db", "States.json"),
    ReferenceRule("Items.json", "animationId", "db", "Animations.json", frozenset({0, -1})),
    ReferenceRule("Items.json", "effects[code=21].dataId", "db", "States.json"),
    ReferenceRule("Weapons.json", "animationId", "db", "Animations.json", frozenset({0, -1})),
    ReferenceRule("Enemies.json", "actions[].skillId", "db", "Skills.json"),
    ReferenceRule("Enemies.json", "dropItems[kind=1].dataId", "db", "Items.json"),
    ReferenceRule("Enemies.json", "dropItems[kind=2].dataId", "db", "Weapons.json"),
    ReferenceRule("Enemies.json", "dropItems[kind=3].dataId", "db", "Armors.json"),
    ReferenceRule("Troops.json", "members[].enemyId", "db", "Enemies.json"),
    ReferenceRule("System.json", "partyMembers[]", "db", "Actors.json"),
    ReferenceRule("System.json", "testBattlers[].actorId", "db", "Actors.json"),
    ReferenceRule("System.json", "testTroopId", "db", "Troops.json", frozenset({0})),
)

SYSTEM_INDEX_RULES: tuple[ReferenceRule, ...] = (
    ReferenceRule(
        "Skills.json", "damage.elementId", "system_index", "elements", frozenset({0, -1})
    ),
    ReferenceRule("Skills.json", "requiredWtypeId1", "system_index", "weaponTypes", frozenset({0})),
    ReferenceRule("Skills.json", "requiredWtypeId2", "system_index", "weaponTypes", frozenset({0})),
    ReferenceRule("Skills.json", "stypeId", "system_index", "skillTypes"),
    ReferenceRule("Items.json", "damage.elementId", "system_index", "elements", frozenset({0, -1})),
    ReferenceRule("Weapons.json", "etypeId", "system_index", "equipTypes"),
    ReferenceRule("Weapons.json", "wtypeId", "system_index", "weaponTypes"),
    ReferenceRule("Armors.json", "etypeId", "system_index", "equipTypes"),
    ReferenceRule("Armors.json", "atypeId", "system_index", "armorTypes"),
)

TRAIT_REFERENCE_TARGETS: dict[int, tuple[str, str]] = {
    51: ("system_index", "weaponTypes"),
    52: ("system_index", "armorTypes"),
    31: ("system_index", "elements"),
    11: ("system_index", "elements"),
    13: ("db", "States.json"),
}

TRAIT_REFERENCE_FILES = {
    "Actors.json",
    "Classes.json",
    "Weapons.json",
    "Armors.json",
    "Enemies.json",
}


def available_schemas() -> str:
    canonical_names = sorted({spec.canonical_name for spec in SCHEMA_REGISTRY.values()})
    return ", ".join(canonical_names)


def resolve_schema(file_name: str) -> SchemaSpec | None:
    normalized = Path(file_name).name.strip().lower()
    return SCHEMA_REGISTRY.get(normalized)


def load_model(spec: SchemaSpec) -> type:
    module = import_module(f"{schemas_pkg.__name__}.{spec.module_name}")
    model = getattr(module, spec.model_name, None)
    if not isinstance(model, type) or not hasattr(model, "model_validate"):
        raise ValueError(
            f"invalid schema configuration: {spec.canonical_name} -> "
            f"{spec.module_name}.{spec.model_name}"
        )
    return model


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def build_output(
    validation_results: list[dict[str, Any]],
    validation_summary: str,
    success: bool,
) -> dict[str, Any]:
    return {
        "validation_result": _build_validation_result_compat(validation_results, success),
        "validation_results": validation_results,
        "validation_summary": validation_summary,
        "success": success,
    }


def build_file_result(
    *,
    target: str,
    success: bool,
    message: str,
    errors: list[dict[str, Any]] | None = None,
    backup_path: str | None = None,
    related_steps: list[int] | None = None,
) -> dict[str, Any]:
    normalized_errors = errors or []
    result = {
        "target": target,
        "success": success,
        "message": message,
        "errors": normalized_errors,
        "error_count": len(normalized_errors),
    }
    if backup_path:
        result["backup_path"] = backup_path
    if related_steps is not None:
        result["related_steps"] = related_steps
    return result


def build_state_error(message: str) -> dict[str, Any]:
    result = build_file_result(
        target="state",
        success=False,
        message="Validator state is invalid",
        errors=[{"loc": "$", "msg": message}],
        related_steps=[],
    )
    return build_output(
        validation_results=[result],
        validation_summary=message,
        success=False,
    )


def find_first_difference(
    schema_value: Any, raw_value: Any, path: str = "$"
) -> tuple[str, Any, Any] | None:
    if type(schema_value) is not type(raw_value):
        return path, raw_value, schema_value

    if isinstance(schema_value, dict):
        schema_keys = set(schema_value.keys())
        raw_keys = set(raw_value.keys())

        extra_keys = sorted(raw_keys - schema_keys)
        if extra_keys:
            key = extra_keys[0]
            return f"{path}.{key}", raw_value[key], None

        missing_keys = sorted(schema_keys - raw_keys)
        if missing_keys:
            key = missing_keys[0]
            return f"{path}.{key}", None, schema_value[key]

        for key in schema_value:
            nested = find_first_difference(schema_value[key], raw_value[key], f"{path}.{key}")
            if nested is not None:
                return nested

        return None

    if isinstance(schema_value, list):
        if len(schema_value) != len(raw_value):
            return path, raw_value, schema_value

        for index, (schema_item, raw_item) in enumerate(zip(schema_value, raw_value)):
            nested = find_first_difference(schema_item, raw_item, f"{path}[{index}]")
            if nested is not None:
                return nested

        return None

    if schema_value != raw_value:
        return path, raw_value, schema_value

    return None


def validate_with_model(
    model: type, data: Any, target_name: str
) -> tuple[bool, list[dict[str, Any]]]:
    original_data = deepcopy(data)

    try:
        validated = model.model_validate(deepcopy(data))
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
        if file_name not in current_game_state or current_game_state[file_name] != modified_value:
            modified_files.append(file_name)
    return sorted(modified_files)


def merge_reference_snapshots(
    current_game_state: dict[str, Any],
    modified_game_state: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current_game_state)
    merged.update(modified_game_state)
    return merged


def _format_diff_path(base_path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{base_path}[{key}]"
    if base_path == "$":
        return f"$.{key}"
    return f"{base_path}.{key}"


def _extract_value_diff(
    current_value: Any,
    modified_value: Any,
    path: str,
) -> list[dict[str, Any]]:
    if type(current_value) is not type(modified_value):
        return [
            {
                "path": path,
                "change_type": "replace",
                "before": to_jsonable(current_value),
                "after": to_jsonable(modified_value),
            }
        ]

    if isinstance(current_value, dict):
        changes: list[dict[str, Any]] = []
        current_keys = set(current_value.keys())
        modified_keys = set(modified_value.keys())

        for key in sorted(current_keys - modified_keys):
            key_path = _format_diff_path(path, key)
            changes.append(
                {
                    "path": key_path,
                    "change_type": "remove",
                    "before": to_jsonable(current_value[key]),
                    "after": None,
                }
            )

        for key in sorted(modified_keys - current_keys):
            key_path = _format_diff_path(path, key)
            changes.append(
                {
                    "path": key_path,
                    "change_type": "add",
                    "before": None,
                    "after": to_jsonable(modified_value[key]),
                }
            )

        for key in sorted(current_keys & modified_keys):
            changes.extend(
                _extract_value_diff(
                    current_value[key],
                    modified_value[key],
                    _format_diff_path(path, key),
                )
            )
        return changes

    if isinstance(current_value, list):
        changes: list[dict[str, Any]] = []
        shared_length = min(len(current_value), len(modified_value))

        for index in range(shared_length):
            changes.extend(
                _extract_value_diff(
                    current_value[index],
                    modified_value[index],
                    _format_diff_path(path, index),
                )
            )

        for index in range(shared_length, len(current_value)):
            item_path = _format_diff_path(path, index)
            changes.append(
                {
                    "path": item_path,
                    "change_type": "remove",
                    "before": to_jsonable(current_value[index]),
                    "after": None,
                }
            )

        for index in range(shared_length, len(modified_value)):
            item_path = _format_diff_path(path, index)
            changes.append(
                {
                    "path": item_path,
                    "change_type": "add",
                    "before": None,
                    "after": to_jsonable(modified_value[index]),
                }
            )

        return changes

    if current_value != modified_value:
        return [
            {
                "path": path,
                "change_type": "replace",
                "before": to_jsonable(current_value),
                "after": to_jsonable(modified_value),
            }
        ]

    return []


def _extract_state_diff(
    current_game_state: dict[str, Any],
    modified_game_state: dict[str, Any],
) -> list[dict[str, Any]]:
    diff_entries: list[dict[str, Any]] = []
    file_names = sorted(set(current_game_state.keys()) | set(modified_game_state.keys()))

    for file_name in file_names:
        has_current = file_name in current_game_state
        has_modified = file_name in modified_game_state

        if not has_current:
            diff_entries.append(
                {
                    "file_name": file_name,
                    "path": "$",
                    "change_type": "add",
                    "before": None,
                    "after": to_jsonable(modified_game_state[file_name]),
                }
            )
            continue

        if not has_modified:
            diff_entries.append(
                {
                    "file_name": file_name,
                    "path": "$",
                    "change_type": "remove",
                    "before": to_jsonable(current_game_state[file_name]),
                    "after": None,
                }
            )
            continue

        if current_game_state[file_name] == modified_game_state[file_name]:
            continue

        for entry in _extract_value_diff(current_game_state[file_name], modified_game_state[file_name], "$"):
            diff_entries.append({"file_name": file_name, **entry})

    return diff_entries


def _changed_snapshot_subset(
    snapshot: dict[str, Any],
    file_names: set[str],
) -> dict[str, Any]:
    return {file_name: snapshot[file_name] for file_name in sorted(file_names) if file_name in snapshot}


def _flatten_errors(validation_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [error for item in validation_results for error in item.get("errors", [])]


def _build_validation_result_compat(
    validation_results: list[dict[str, Any]],
    success: bool,
) -> dict[str, Any]:
    return {
        "passed": success,
        "errors": _flatten_errors(validation_results),
        "error_count": sum(int(item.get("error_count", 0)) for item in validation_results),
    }


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
            errors=schema_errors,
            backup_path=backup_path,
            related_steps=related_steps,
        )

    reference_errors = validate_references(file_name, data, reference_snapshots)
    if reference_errors:
        return build_file_result(
            target=file_name,
            success=False,
            message=f"{file_name} reference validation failed",
            errors=reference_errors,
            backup_path=backup_path,
            related_steps=related_steps,
        )

    return build_file_result(
        target=file_name,
        success=True,
        message=f"{file_name} validation passed",
        errors=[],
        backup_path=backup_path,
        related_steps=related_steps,
    )


def _collect_all_step_ids(changes_log: list[dict[str, Any]]) -> list[int]:
    step_ids: list[int] = []
    for entry in changes_log:
        if not isinstance(entry, dict):
            continue

        step_value = entry.get("step_id", entry.get("step"))
        try:
            step_id = int(step_value)
        except (TypeError, ValueError):
            continue

        if step_id not in step_ids:
            step_ids.append(step_id)
    return step_ids


async def _run_content_validation_llm(
    *,
    current_game_state: dict[str, Any],
    modified_game_state: dict[str, Any],
    changes_log: list[dict[str, Any]],
    state_diff: list[dict[str, Any]],
) -> _ContentValidationOutput:
    changed_files = {entry["file_name"] for entry in state_diff if isinstance(entry.get("file_name"), str)}
    prompt_state: AgentState = {
        "_validator_prompt_mode": "content_validation",
        "current_game_state": _changed_snapshot_subset(current_game_state, changed_files),
        "modified_game_state": _changed_snapshot_subset(modified_game_state, changed_files),
        "changes_log": changes_log,
        "state_diff": state_diff,
    }
    messages = build_validator_prompt(prompt_state)
    result = await invoke_llm(messages, structured_output=_ContentValidationOutput)
    return result if isinstance(result, _ContentValidationOutput) else _ContentValidationOutput.model_validate(result)


def _build_content_validation_result(
    content_output: _ContentValidationOutput,
    *,
    state_diff: list[dict[str, Any]],
    changes_log: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    errors.extend(
        {"loc": "unexpected_changes", "msg": message}
        for message in content_output.unexpected_changes
    )
    errors.extend(
        {"loc": "missing_expected_changes", "msg": message}
        for message in content_output.missing_expected_changes
    )

    if not content_output.is_consistent and not errors:
        errors.append(
            {
                "loc": "$",
                "msg": content_output.reasoning or "Content validation reported an inconsistency.",
            }
        )

    message = "Content validation passed"
    if not content_output.is_consistent:
        message = "Content validation detected unexpected or missing changes"

    result = build_file_result(
        target="content_consistency",
        success=content_output.is_consistent,
        message=message,
        errors=errors,
        related_steps=_collect_all_step_ids(changes_log),
    )
    result["expected_changes"] = content_output.expected_changes
    result["actual_changes"] = content_output.actual_changes
    result["unexpected_changes"] = content_output.unexpected_changes
    result["missing_expected_changes"] = content_output.missing_expected_changes
    result["reasoning"] = content_output.reasoning
    result["diff_change_count"] = len(state_diff)
    return result


def _build_content_validation_error_result(
    error: Exception,
    *,
    state_diff: list[dict[str, Any]],
    changes_log: list[dict[str, Any]],
) -> dict[str, Any]:
    result = build_file_result(
        target="content_consistency",
        success=False,
        message="Content validation failed",
        errors=[{"loc": "$", "msg": f"content validation llm failed: {error}"}],
        related_steps=_collect_all_step_ids(changes_log),
    )
    result["expected_changes"] = []
    result["actual_changes"] = []
    result["unexpected_changes"] = []
    result["missing_expected_changes"] = []
    result["reasoning"] = ""
    result["diff_change_count"] = len(state_diff)
    return result


async def validate_content_consistency(
    *,
    current_game_state: dict[str, Any],
    modified_game_state: dict[str, Any],
    changes_log: list[dict[str, Any]],
    state_diff: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        content_output = await _run_content_validation_llm(
            current_game_state=current_game_state,
            modified_game_state=modified_game_state,
            changes_log=changes_log,
            state_diff=state_diff,
        )
    except Exception as error:
        logger.warning("Validator content validation fallback due to LLM error: %s", error)
        return _build_content_validation_error_result(
            error,
            state_diff=state_diff,
            changes_log=changes_log,
        )

    return _build_content_validation_result(
        content_output,
        state_diff=state_diff,
        changes_log=changes_log,
    )


def build_summary_payload(
    validation_results: list[dict[str, Any]],
    retry_count: int,
) -> dict[str, Any]:
    success_count = sum(1 for item in validation_results if item.get("success"))
    failed_items = [item for item in validation_results if not item.get("success")]
    total_error_count = sum(int(item.get("error_count", 0)) for item in validation_results)

    return {
        "modified_file_count": len(validation_results),
        "success_file_count": success_count,
        "failed_file_count": len(failed_items),
        "total_error_count": total_error_count,
        "failed_targets": [item.get("target") for item in failed_items],
        "results": validation_results,
        "retry_count": retry_count,
    }


def build_fallback_summary(
    validation_results: list[dict[str, Any]],
    retry_count: int,
) -> str:
    if not validation_results:
        return "수정된 파일이 없어 검증을 건너뛰었습니다."

    success_count = sum(1 for item in validation_results if item.get("success"))
    failed_count = len(validation_results) - success_count
    total_error_count = sum(int(item.get("error_count", 0)) for item in validation_results)

    if failed_count == 0:
        return f"수정된 파일 {success_count}개가 모두 검증을 통과했습니다."

    return (
        f"수정된 파일 {len(validation_results)}개 중 {failed_count}개 파일에서 "
        f"총 {total_error_count}개의 오류가 발견되었습니다. "
        f"재시도 횟수는 {retry_count}회입니다."
    )


def _messages_to_prompt_pair(messages: list[Any]) -> tuple[str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []

    for message in messages:
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            content = str(content)

        message_type = getattr(message, "type", "").lower()
        if message_type == "system":
            system_parts.append(content)
        else:
            user_parts.append(content)

    return "\n\n".join(system_parts).strip(), "\n\n".join(user_parts).strip()


async def summarize_validation_results(
    validation_results: list[dict[str, Any]],
    retry_count: int,
) -> str:
    fallback_summary = build_fallback_summary(validation_results, retry_count)

    if not validation_results:
        return fallback_summary

    prompt_state: AgentState = {
        "validation_results": validation_results,
        "success": all(item.get("success") for item in validation_results),
        "retry_count": retry_count,
    }
    messages = build_validator_prompt(prompt_state)
    system_prompt, user_message = _messages_to_prompt_pair(messages)

    if not system_prompt or not user_message:
        logger.warning("Validator prompt build failed, using fallback summary.")
        return fallback_summary

    try:
        from agent.core.llm_client import invoke_llm_simple

        summary = (await invoke_llm_simple(system_prompt, user_message)).strip()
        return summary or fallback_summary
    except Exception as error:
        logger.warning("Validator summary fallback due to LLM error: %s", error)
        return fallback_summary


async def validator(state: AgentState) -> dict:
    current_game_state, modified_game_state, changes_log, backup_paths, retry_count = (
        extract_validation_inputs(state)
    )

    if not modified_game_state:
        return build_state_error("modified_game_state is missing or empty.")

    modified_files = detect_modified_files(current_game_state, modified_game_state)
    reference_snapshots = merge_reference_snapshots(current_game_state, modified_game_state)
    state_diff = _extract_state_diff(current_game_state, modified_game_state)

    validation_results = [
        validate_single_file(
            file_name=file_name,
            data=modified_game_state[file_name],
            reference_snapshots=reference_snapshots,
            backup_paths=backup_paths,
            changes_log=changes_log,
        )
        for file_name in modified_files
    ]
    validation_results.append(
        await validate_content_consistency(
            current_game_state=current_game_state,
            modified_game_state=modified_game_state,
            changes_log=changes_log,
            state_diff=state_diff,
        )
    )

    success = all(item.get("success") for item in validation_results)
    validation_summary = await summarize_validation_results(validation_results, retry_count)

    logger.info(
        "Validator finished | modified_files=%d | success=%s",
        len(validation_results),
        success,
    )

    return build_output(
        validation_results=validation_results,
        validation_summary=validation_summary,
        success=success,
    )
