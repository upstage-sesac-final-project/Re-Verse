from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.schemas as schemas_pkg


@dataclass(frozen=True)
class SchemaSpec:
    canonical_name: str
    module_name: str
    model_name: str


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


def available_schemas() -> str:
    canonical_names = sorted({spec.canonical_name for spec in SCHEMA_REGISTRY.values()})
    return ", ".join(canonical_names)


def resolve_schema(schema_name: str) -> SchemaSpec:
    normalized = schema_name.strip().lower()
    spec = SCHEMA_REGISTRY.get(normalized)
    if spec is None:
        raise SystemExit(
            f"unknown schema: {schema_name}\n"
            f"available: {available_schemas()}"
        )
    return spec


def load_model(spec: SchemaSpec) -> type:
    try:
        module = import_module(f"{schemas_pkg.__name__}.{spec.module_name}")
    except Exception as error:
        raise SystemExit(
            f"failed to import schema: {spec.canonical_name}\n"
            f"reason: {error}"
        ) from error

    model = getattr(module, spec.model_name, None)
    if not isinstance(model, type) or not hasattr(model, "model_validate"):
        raise SystemExit(
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
        "validation_results": validation_results,
        "validation_summary": validation_summary,
        "success": success,
    }


def find_first_difference(schema_value: Any, raw_value: Any, path: str = "$") -> tuple[str, Any, Any] | None:
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


def validate_with_model(model: type, data: Any, target_name: str) -> dict[str, Any]:
    original_data = deepcopy(data)

    try:
        validated = model.model_validate(deepcopy(data))
    except ValidationError as error:
        return build_output(
            validation_results=[
                {
                    "target": target_name,
                    "success": False,
                    "message": f"{target_name} schema validation failed",
                    "errors": to_jsonable(error.errors()),
                }
            ],
            validation_summary=f"{target_name} validation failed",
            success=False,
        )

    print("MODEL =", model)
    print("MODULE =", model.__module__)
    print("RAW_KEYS[1] =", list(original_data[1].keys()))
    print("RAW_ITEM[1] =", original_data[1])

    normalized = validated.model_dump(mode="json", exclude_unset=True)

    print("NORM_KEYS[1] =", list(normalized[1].keys()))
    print("NORM_ITEM[1] =", normalized[1])

    mismatch = find_first_difference(normalized, original_data)
    if mismatch is not None:
        location, raw_value, schema_value = mismatch
        return build_output(
            validation_results=[
                {
                    "target": target_name,
                    "success": False,
                    "message": f"{target_name} schema validation failed",
                    "errors": [
                        {
                            "loc": location,
                            "msg": "input does not strictly match schema",
                            "raw": to_jsonable(raw_value),
                            "schema": to_jsonable(schema_value),
                        }
                    ],
                }
            ],
            validation_summary=f"{target_name} validation failed",
            success=False,
        )

    return build_output(
        validation_results=[
            {
                "target": target_name,
                "success": True,
                "message": f"{target_name} schema validation passed",
            }
        ],
        validation_summary=f"{target_name} validation passed",
        success=True,
    )


def load_json_file(json_path: Path) -> Any:
    try:
        with json_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except UnicodeDecodeError:
        with json_path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: python agent/tests/test_validator.py [schema] [json_path]")

    schema_name = sys.argv[1]
    json_path = Path(sys.argv[2])

    if not json_path.exists():
        raise SystemExit(f"file not found: {json_path}")

    spec = resolve_schema(schema_name)
    model = load_model(spec)

    try:
        data = load_json_file(json_path)
    except json.JSONDecodeError as error:
        result = build_output(
            validation_results=[
                {
                    "target": json_path.name,
                    "success": False,
                    "message": f"{json_path.name} schema validation failed",
                    "errors": [
                        {
                            "loc": "$",
                            "msg": "invalid JSON syntax",
                            "line": error.lineno,
                            "column": error.colno,
                        }
                    ],
                }
            ],
            validation_summary=f"{json_path.name} validation failed",
            success=False,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    result = validate_with_model(model=model, data=data, target_name=json_path.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()