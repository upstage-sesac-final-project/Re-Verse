"""Validation entrypoint for game JSON files (structure-only, Pydantic-based).

Current scope:
- Supports only `Actors.json`
- Performs only structure/type validation (no semantic rules, no cross-file checks)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent.graph.state import AgentState
from agent.validation.actor import ActorsFile

logger = logging.getLogger(__name__)


DEFAULT_GAME_DATA_DIR = Path("storage/games/game_001/data")

# Minimal registry (easy to extend later)
_MODEL_REGISTRY: dict[str, type[Any]] = {
    "Actors.json": ActorsFile,
}


def _format_pydantic_loc(loc: tuple[Any, ...]) -> str:
    if not loc:
        return "$"

    rendered = ""
    for part in loc:
        if isinstance(part, int):
            rendered += f"[{part}]"
            continue

        if rendered and not rendered.endswith("."):
            rendered += "."
        rendered += str(part)

    return rendered


def load_json_file(path: str | Path) -> Any:
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = file_path.read_text(encoding="utf-8-sig")

    return json.loads(raw)


def resolve_json_path(path_or_name: str | Path, *, base_dir: Path = DEFAULT_GAME_DATA_DIR) -> Path:
    candidate = Path(path_or_name)
    if candidate.is_file():
        return candidate

    if candidate.is_absolute():
        return candidate

    return base_dir / candidate.name


def validate_json(path_or_name: str | Path, *, base_dir: Path = DEFAULT_GAME_DATA_DIR) -> dict:
    path = resolve_json_path(path_or_name, base_dir=base_dir)
    filename = path.name

    if not path.is_file():
        return {
            "validation_result": [
                {
                    "source": "validator",
                    "level": "error",
                    "location": "file",
                    "message": f"File not found: {path}",
                }
            ],
            "validation_summary": f"{filename} validation failed with 1 error.",
            "success": False,
        }

    model_type = _MODEL_REGISTRY.get(filename)
    if model_type is None:
        return {
            "validation_result": [
                {
                    "source": "validator",
                    "level": "error",
                    "location": "file",
                    "message": f"Unsupported file for validation: {filename}",
                }
            ],
            "validation_summary": f"{filename} validation failed with 1 error.",
            "success": False,
        }

    try:
        data = load_json_file(path)
    except json.JSONDecodeError as exc:
        return {
            "validation_result": [
                {
                    "source": "validator",
                    "level": "error",
                    "location": "file",
                    "message": f"Invalid JSON syntax: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
                }
            ],
            "validation_summary": f"{filename} validation failed with 1 error.",
            "success": False,
        }

    try:
        # Structure-only validation (no semantic rules).
        model_type.model_validate(data)
    except ValidationError as exc:
        items: list[dict[str, str]] = []
        for err in exc.errors():
            loc_str = _format_pydantic_loc(tuple(err.get("loc", ())))
            msg = str(err.get("msg", "Invalid value.")).rstrip(".")
            fix_hint = (
                "Fix the JSON structure."
                if loc_str == "$"
                else f"Fix the value at {loc_str}."
            )
            items.append(
                {
                    "source": "pydantic",
                    "level": "error",
                    "location": loc_str,
                    "message": f"{msg}. {fix_hint}",
                }
            )

        error_count = len(items)
        return {
            "validation_result": items,
            "validation_summary": f"{filename} validation failed with {error_count} error(s).",
            "success": False,
        }

    return {
        "validation_result": [],
        "validation_summary": f"{filename} validation passed.",
        "success": True,
    }


async def validator(state: AgentState) -> dict:
    """
    LangGraph node wrapper.

    - If `state["target_files"]` exists, validates each entry by filename.
    - Otherwise validates `Actors.json` by default.
    """

    game_id = state.get("game_id", "game_001")
    base_dir = Path("storage/games") / game_id / "data"
    targets = state.get("target_files") or ["Actors.json"]

    combined_items: list[dict[str, str]] = []
    for target in targets:
        result = validate_json(target, base_dir=base_dir)
        if result["success"]:
            continue

        for item in result["validation_result"]:
            combined_items.append(
                {
                    "source": item["source"],
                    "level": item["level"],
                    "location": f"{Path(target).name}:{item['location']}",
                    "message": item["message"],
                }
            )

    if not combined_items:
        return {
            "validation_result": [],
            "validation_summary": "Actors.json validation passed."
            if targets == ["Actors.json"]
            else "All target files passed validation.",
            "success": True,
        }

    return {
        "validation_result": combined_items,
        "validation_summary": f"Validation failed with {len(combined_items)} error(s).",
        "success": False,
    }

