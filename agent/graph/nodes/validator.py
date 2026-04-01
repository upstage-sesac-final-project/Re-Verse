"""Code-first validator node."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agent.graph.state import AgentState
from agent.graph.utils.game_state_json import load_snapshot_payload
from agent.schemas.actors import ActorsFile
from agent.schemas.animations import AnimationsFile
from agent.schemas.armors import ArmorsFile
from agent.schemas.classes import ClassesFile
from agent.schemas.enemies import EnemiesFile
from agent.schemas.items import ItemsFile
from agent.schemas.maps import MapFile
from agent.schemas.skills import SkillsFile
from agent.schemas.states import StatesFile
from agent.schemas.system import System

# from agent.schemas.traits import TraitsFile
from agent.schemas.troops import TroopsFile
from agent.schemas.weapons import WeaponsFile

logger = logging.getLogger(__name__)

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
    # "Traits.json": TraitsFile,
    "Troops.json": TroopsFile,
    "Weapons.json": WeaponsFile,
}

_SCHEMA_MAP_NORMALIZED = {name.lower(): model for name, model in SCHEMA_MAP.items()}
_MAP_FILE_PATTERN = re.compile(r"map\d{3}\.json")


class ValidationErrorItem(BaseModel):
    loc: Any
    msg: str


class FileValidationResult(BaseModel):
    target: str
    success: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)


class ValidatorOutput(BaseModel):
    validation_results: list[FileValidationResult] = Field(default_factory=list)
    validation_summary: str
    success: bool
    retry_count: int | None = None


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def resolve_schema(file_name: str) -> type[Any] | None:
    normalized_name = Path(file_name).name.strip().lower()
    if _MAP_FILE_PATTERN.fullmatch(normalized_name):
        return MapFile
    return _SCHEMA_MAP_NORMALIZED.get(normalized_name)


def normalize_validation_errors(
    errors: list[dict[str, Any]] | list[ValidationErrorItem] | None = None,
) -> list[ValidationErrorItem]:
    normalized_errors: list[ValidationErrorItem] = []
    for error in errors or []:
        if isinstance(error, ValidationErrorItem):
            normalized_errors.append(error)
            continue
        if isinstance(error, dict):
            normalized_errors.append(
                ValidationErrorItem(
                    loc=to_jsonable(error.get("loc", "$")),
                    msg=str(error.get("msg", "validation error")),
                )
            )
            continue
        normalized_errors.append(ValidationErrorItem(loc="$", msg=str(error)))
    return normalized_errors


def build_file_result(
    target: str,
    success: bool,
    errors: list[dict[str, Any]] | list[ValidationErrorItem] | None = None,
) -> FileValidationResult:
    return FileValidationResult(
        target=target,
        success=success,
        errors=normalize_validation_errors(errors),
    )


def build_output(
    validation_results: list[FileValidationResult],
    validation_summary: str,
    success: bool,
    retry_count: int | None = None,
) -> ValidatorOutput:
    return ValidatorOutput(
        validation_results=validation_results,
        validation_summary=validation_summary,
        success=success,
        retry_count=retry_count,
    )


def build_validation_summary(validation_results: list[FileValidationResult]) -> str:
    if not validation_results:
        return "검증할 파일이 없어 validator를 종료했습니다."

    failed_count = sum(1 for item in validation_results if not item.success)
    if failed_count == 0:
        return f"총 {len(validation_results)}개 파일이 모두 스키마 검증을 통과했습니다."
    return f"총 {len(validation_results)}개 파일 중 {failed_count}개 파일 검증에 실패했습니다."


def build_state_error(message: str, retry_count: int | None = None) -> ValidatorOutput:
    logger.warning("[Validator] 조기 종료: %s (retry=%s)", message, retry_count)
    validation_results = [
        build_file_result(
            target="state",
            success=False,
            errors=[{"loc": "$", "msg": message}],
        )
    ]
    return build_output(
        validation_results=validation_results,
        validation_summary=message,
        success=False,
        retry_count=retry_count,
    )


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


def load_validation_payload(file_name: str, value: Any) -> tuple[Any, list[dict[str, Any]]]:
    payload = load_snapshot_payload(value)
    if isinstance(payload, dict) and payload.get("_snapshot_error"):
        return None, [{"loc": "$", "msg": str(payload["_snapshot_error"])}]
    return payload, []


def load_validation_entries(
    game_state: dict[str, Any],
) -> dict[str, tuple[Any, list[dict[str, Any]]]]:
    entries: dict[str, tuple[Any, list[dict[str, Any]]]] = {}
    for file_name, value in game_state.items():
        entries[file_name] = load_validation_payload(file_name, value)
    return entries


def summarize_modified_files(
    current_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> tuple[int, int]:
    detected_count = 0
    unchanged_count = 0
    for file_name, (modified_payload, modified_errors) in modified_entries.items():
        if file_name not in current_entries:
            detected_count += 1
            continue

        current_payload, current_errors = current_entries[file_name]
        if current_errors or modified_errors or current_payload != modified_payload:
            detected_count += 1
            continue

        unchanged_count += 1
    return detected_count, unchanged_count


def _format_first_error(errors: list[dict[str, Any]] | list[ValidationErrorItem]) -> str:
    normalized_errors = normalize_validation_errors(errors)
    if not normalized_errors:
        return "unknown error"

    first_error = normalized_errors[0]
    return f"loc={first_error.loc}, msg={first_error.msg}"


def validate_single_file(
    file_name: str,
    payload: Any,
    payload_errors: list[dict[str, Any]] | None = None,
) -> FileValidationResult:
    model = resolve_schema(file_name)
    if model is None:
        logger.warning("[Validator] 미지원 스키마: target=%s", file_name)
        return build_file_result(
            target=file_name,
            success=False,
            errors=[{"loc": "$", "msg": f"unsupported schema for {file_name}"}],
        )

    if payload_errors:
        return build_file_result(
            target=file_name,
            success=False,
            errors=payload_errors,
        )

    try:
        model.model_validate(payload, strict=True)
    except ValidationError as error:
        validation_errors = to_jsonable(error.errors())
        logger.warning(
            "[Validator] 검증 실패: target=%s, error=%s",
            file_name,
            _format_first_error(validation_errors),
        )
        return build_file_result(
            target=file_name,
            success=False,
            errors=validation_errors,
        )

    return build_file_result(
        target=file_name,
        success=True,
        errors=[],
    )


async def validator(state: AgentState) -> dict[str, Any]:
    (
        current_game_state,
        modified_game_state,
        _changes_log,
        _backup_paths,
        retry_count,
    ) = extract_validation_inputs(state)

    logger.info("[Validator] 시작: files=%d, retry=%d", len(modified_game_state), retry_count)

    if not modified_game_state:
        result = build_state_error(
            "modified_game_state is missing or empty.",
            retry_count=retry_count + 1,
        )
        return result.model_dump(mode="json", exclude_none=True)

    current_entries = load_validation_entries(current_game_state)
    modified_entries = load_validation_entries(modified_game_state)
    detected_count, unchanged_count = summarize_modified_files(current_entries, modified_entries)
    logger.info(
        "[Validator] 변경 감지 요약: detected=%d, unchanged=%d, total=%d",
        detected_count,
        unchanged_count,
        len(modified_entries),
    )

    validation_results = [
        validate_single_file(file_name, payload, payload_errors)
        for file_name, (payload, payload_errors) in modified_entries.items()
    ]
    success = all(item.success for item in validation_results)
    validation_summary = build_validation_summary(validation_results)
    next_retry_count = retry_count + 1 if not success else None
    failed_count = sum(1 for item in validation_results if not item.success)

    logger.info(
        "[Validator] 종료: success=%s, validated=%d, failed=%d, retry_count=%s",
        success,
        len(validation_results),
        failed_count,
        next_retry_count,
    )

    result = build_output(
        validation_results=validation_results,
        validation_summary=validation_summary,
        success=success,
        retry_count=next_retry_count,
    )
    return result.model_dump(mode="json", exclude_none=True)
