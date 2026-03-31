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
