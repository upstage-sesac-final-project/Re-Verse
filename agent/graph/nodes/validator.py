"""Code-first validator node."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.graph.utils.game_state_json import load_snapshot_payload
from agent.prompts.validator_prompt import build_prompt as build_validator_prompt
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


class StepValidationLLMResult(BaseModel):
    is_match: bool
    reasoning: str


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


def build_state_error(message: str) -> ValidatorOutput:
    logger.warning("[Validator] 조기 종료: %s", message)
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
    )


def extract_validation_inputs(
    state: AgentState,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, str],
    int,
]:
    current_game_state = state.get("current_game_state", {})
    modified_game_state = state.get("modified_game_state", {})
    execution_plan = state.get("execution_plan", [])
    changes_log = state.get("changes_log", [])
    backup_paths = state.get("backup_paths", {})
    retry_count = state.get("retry_count", 0)

    if not isinstance(current_game_state, dict):
        current_game_state = {}
    if not isinstance(modified_game_state, dict):
        modified_game_state = {}
    if not isinstance(execution_plan, list):
        execution_plan = []
    if not isinstance(changes_log, list):
        changes_log = []
    execution_plan = [item for item in execution_plan if isinstance(item, dict)]
    changes_log = [item for item in changes_log if isinstance(item, dict)]
    if not isinstance(backup_paths, dict):
        backup_paths = {}
    try:
        retry_count = int(retry_count)
    except (TypeError, ValueError):
        retry_count = 0

    return (
        current_game_state,
        modified_game_state,
        execution_plan,
        changes_log,
        backup_paths,
        retry_count,
    )


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


def select_validation_targets(
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> list[tuple[str, Any, list[dict[str, Any]]]]:
    return [
        (file_name, payload, payload_errors)
        for file_name, (payload, payload_errors) in modified_entries.items()
    ]


def calculate_schema_success(validation_results: list[FileValidationResult]) -> bool:
    return all(item.success for item in validation_results)


def calculate_final_success(schema_success: bool, step_success: bool) -> bool:
    return schema_success and step_success


def calculate_retry_count(retry_count: int, success: bool) -> int | None:
    return None if success else retry_count + 1


def finalize_output(result: ValidatorOutput) -> dict[str, Any]:
    validated_result = ValidatorOutput.model_validate(result.model_dump(mode="python"))
    return validated_result.model_dump(mode="json", exclude_none=True)


def _coerce_step_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_step_id_map(entries: list[dict[str, Any]], source: str) -> dict[int, dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for entry in entries:
        step_id = _coerce_step_id(entry.get("step_id"))
        if step_id is None:
            logger.warning("[Validator] %s step_id 누락 또는 형식 오류: %s", source, entry)
            continue
        if step_id in by_id:
            logger.warning("[Validator] %s duplicate step_id=%s", source, step_id)
            continue
        by_id[step_id] = entry
    return by_id


def build_step_failure_result(step_id: int, message: str) -> FileValidationResult:
    return build_file_result(
        target=f"step:{step_id}",
        success=False,
        errors=[{"loc": "$", "msg": message}],
    )


def _normalize_modified_files(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _build_step_validation_prompt_state(
    planner_step: dict[str, Any],
    executor_log: dict[str, Any],
) -> dict[str, Any]:
    planner_step_id = _coerce_step_id(planner_step.get("step_id")) or -1
    executor_step_id = _coerce_step_id(executor_log.get("step_id")) or -1
    return {
        "_validator_prompt_mode": "step_validation",
        "planner_step": {
            "step_id": planner_step_id,
            "description": str(planner_step.get("description", "")),
            "action_type": str(planner_step.get("action_type", "")),
            "target_file": str(planner_step.get("target_file", "")),
        },
        "executor_log": {
            "step_id": executor_step_id,
            "tool_name": str(executor_log.get("tool_name", "")),
            "success": bool(executor_log.get("success")),
            "modified_files": _normalize_modified_files(executor_log.get("modified_files")),
        },
    }


async def judge_step_match_with_llm(
    planner_step: dict[str, Any],
    executor_log: dict[str, Any],
) -> StepValidationLLMResult:
    step_id = _coerce_step_id(planner_step.get("step_id")) or -1
    messages = build_validator_prompt(
        _build_step_validation_prompt_state(planner_step, executor_log)
    )

    try:
        result = await invoke_llm(messages, structured_output=StepValidationLLMResult)
    except Exception as error:
        logger.warning("[Validator] step validation LLM 실패: step_id=%s err=%s", step_id, error)
        return StepValidationLLMResult(
            is_match=False,
            reasoning=f"step validation LLM error: {error}",
        )

    if isinstance(result, StepValidationLLMResult):
        return result
    return StepValidationLLMResult.model_validate(result)


async def validate_execution_steps(
    execution_plan: list[dict[str, Any]],
    changes_log: list[dict[str, Any]],
) -> tuple[list[FileValidationResult], bool]:
    planner_steps = build_step_id_map(execution_plan, "planner step")
    executor_candidates = [entry for entry in changes_log if entry.get("step_id") is not None]
    executor_logs = build_step_id_map(executor_candidates, "executor log")
    failures: list[FileValidationResult] = []
    extra_step_ids = sorted(set(executor_logs) - set(planner_steps))

    logger.info(
        "[Validator] step 검증 시작: planner_steps=%d, executor_candidates=%d, executor_steps=%d",
        len(planner_steps),
        len(executor_candidates),
        len(executor_logs),
    )
    if extra_step_ids:
        logger.info("[Validator] step 검증 보류: extra executor steps=%s", extra_step_ids)

    for step_id in sorted(planner_steps):
        planner_step = planner_steps[step_id]
        executor_log = executor_logs.get(step_id)
        logger.info(
            "[Validator] step 검증: step_id=%d, action=%s, target=%s",
            step_id,
            str(planner_step.get("action_type", "")),
            str(planner_step.get("target_file", "")),
        )
        if executor_log is None:
            logger.warning(
                "[Validator] step 검증 실패: step_id=%d reason=missing executor log",
                step_id,
            )
            failures.append(
                build_step_failure_result(
                    step_id,
                    f"planner step {step_id}에 대응하는 executor log가 changes_log에 없습니다.",
                )
            )
            continue

        if executor_log.get("success") is not True:
            tool_name = str(executor_log.get("tool_name", ""))
            reason = str(
                executor_log.get("stderr")
                or executor_log.get("error")
                or executor_log.get("skip_reason")
                or "executor step failed"
            )
            logger.warning(
                "[Validator] step 검증 실패: step_id=%d tool=%s reason=%s",
                step_id,
                tool_name,
                reason,
            )
            failures.append(
                build_step_failure_result(
                    step_id,
                    f"executor step {step_id} failed: tool={tool_name}, reason={reason}",
                )
            )
            continue

        llm_result = await judge_step_match_with_llm(planner_step, executor_log)
        if not llm_result.is_match:
            logger.warning(
                "[Validator] step 검증 실패: step_id=%d tool=%s reason=%s",
                step_id,
                str(executor_log.get("tool_name", "")),
                llm_result.reasoning,
            )
            failures.append(build_step_failure_result(step_id, llm_result.reasoning))
            continue

        logger.info(
            "[Validator] step 검증 통과: step_id=%d tool=%s",
            step_id,
            str(executor_log.get("tool_name", "")),
        )

    logger.info(
        "[Validator] step 검증 종료: success=%s, failed=%d",
        not failures,
        len(failures),
    )
    return failures, not failures


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
        execution_plan,
        changes_log,
        _backup_paths,
        retry_count,
    ) = extract_validation_inputs(state)

    _t0 = time.perf_counter()
    logger.info("─── 🔎 Validator START ──────────────────────────────")

    logger.info("[Validator] 시작: files=%d, retry=%d", len(modified_game_state), retry_count)

    if not modified_game_state:
        result = build_state_error("modified_game_state is missing or empty.")
    elif not execution_plan:
        result = build_state_error("execution_plan is missing or empty.")
    else:
        current_entries = load_validation_entries(current_game_state)
        modified_entries = load_validation_entries(modified_game_state)
        detected_count, unchanged_count = summarize_modified_files(
            current_entries, modified_entries
        )
        logger.info(
            "[Validator] 변경 감지 요약: detected=%d, unchanged=%d, total=%d",
            detected_count,
            unchanged_count,
            len(modified_entries),
        )

        validation_targets = select_validation_targets(modified_entries)
        validation_results = [
            validate_single_file(file_name, payload, payload_errors)
            for file_name, payload, payload_errors in validation_targets
        ]
        schema_success = calculate_schema_success(validation_results)
        step_failures, step_success = await validate_execution_steps(execution_plan, changes_log)
        final_validation_results = validation_results + step_failures
        success = calculate_final_success(schema_success, step_success)
        result = build_output(
            validation_results=final_validation_results,
            validation_summary=build_validation_summary(final_validation_results),
            success=success,
        )

    next_retry_count = calculate_retry_count(retry_count, result.success)
    result = result.model_copy(update={"retry_count": next_retry_count})
    failed_count = sum(1 for item in result.validation_results if not item.success)

    logger.info(
        "[Validator] 종료: success=%s, validated=%d, failed=%d, retry_count=%s",
        result.success,
        len(result.validation_results),
        failed_count,
        result.retry_count,
    )

    logger.info(
        "─── %s Validator END (elapsed=%.2fs, validated=%d, failed=%d, retry_count=%s) ──",
        "✅" if result.success else "⚠️",
        time.perf_counter() - _t0,
        len(result.validation_results),
        failed_count,
        result.retry_count,
    )
    return finalize_output(result)
