from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules
from typing import Any

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.schemas as schemas_pkg


def build_model_map() -> dict[str, type]:
    models: dict[str, type] = {}

    for module_info in iter_modules(schemas_pkg.__path__):
        module_name = module_info.name
        if module_name.startswith("_"):
            continue

        module = import_module(f"{schemas_pkg.__name__}.{module_name}")

        candidates: list[type] = []
        for attr_name, value in module.__dict__.items():
            if not attr_name.endswith("File"):
                continue
            if isinstance(value, type) and hasattr(value, "model_validate"):
                candidates.append(value)

        if len(candidates) == 1:
            models[module_name] = candidates[0]

    return models


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


def validate_with_model(model: type, data: Any, target_name: str) -> dict[str, Any]:
    try:
        model.model_validate(data)
        return build_output(
            validation_results=[
                {
                    "target": target_name,
                    "success": True,
                    "message": f"{target_name} 스키마 검증 성공",
                }
            ],
            validation_summary=f"{target_name} 검증 성공",
            success=True,
        )
    except ValidationError as e:
        return build_output(
            validation_results=[
                {
                    "target": target_name,
                    "success": False,
                    "message": f"{target_name} 스키마 검증 실패",
                    "errors": e.errors(),
                }
            ],
            validation_summary=f"{target_name} 검증 실패",
            success=False,
        )


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: python tests/validation_test.py [schema] [json_path]")

    schema_name = sys.argv[1].lower()
    json_path = Path(sys.argv[2])

    if not json_path.exists():
        raise SystemExit(f"file not found: {json_path}")

    model_map = build_model_map()
    if schema_name not in model_map:
        available = ", ".join(sorted(model_map))
        raise SystemExit(f"unknown schema: {schema_name}\navailable: {available}")

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    model = model_map[schema_name]
    result = validate_with_model(model=model, data=data, target_name=json_path.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
