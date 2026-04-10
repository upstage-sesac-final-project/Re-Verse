"""Code-first validator node."""

from __future__ import annotations

import json
import logging
import re
import time
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
    "Troops.json": TroopsFile,
    "Weapons.json": WeaponsFile,
}

_SCHEMA_MAP_NORMALIZED = {name.lower(): model for name, model in SCHEMA_MAP.items()}
_MAP_FILE_PATTERN = re.compile(r"map\d{3}\.json")
_QUERY_ACTIONS = {"query", "query_by_id", "search"}

# 배열 구조 JSON 파일과 해당 파일의 엔티티 ID를 담는 changes_log 필드명 매핑.
# System.json, 맵 파일 등 배열 구조가 아닌 파일은 포함하지 않는다.
# 이 맵에 포함된 파일만 정합성 검증(final state 대조)을 수행한다.
_FILE_ID_FIELD_MAP: dict[str, str] = {
    "Actors.json": "actor_id",
    "Animations.json": "animation_id",
    "Armors.json": "armor_id",
    "Classes.json": "class_id",
    "Enemies.json": "enemy_id",
    "Items.json": "item_id",
    "Skills.json": "skill_id",
    "States.json": "state_id",
    "Troops.json": "troop_id",
    "Weapons.json": "weapon_id",
}


class ValidationErrorItem(BaseModel):
    loc: Any
    msg: str


class FileValidationResult(BaseModel):
    target: str
    category: str
    success: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)


class ValidatorOutput(BaseModel):
    validation_results: list[FileValidationResult] = Field(default_factory=list)
    validation_summary: str
    success: bool
    retry_count: int


def to_jsonable(value: Any) -> Any:
    """값을 JSON 직렬화 가능한 형태로 변환한다. dict/list는 재귀 처리하고, 직렬화 불가능한 값은 문자열로 변환한다."""
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
    """파일명으로 대응하는 Pydantic 스키마 모델을 반환한다. map001.json 형태의 맵 파일은 MapFile로, 나머지는 SCHEMA_MAP에서 찾는다. 미지원 파일이면 None을 반환한다."""
    normalized_name = Path(file_name).name.strip().lower()
    if _MAP_FILE_PATTERN.fullmatch(normalized_name):
        return MapFile
    return _SCHEMA_MAP_NORMALIZED.get(normalized_name)


def normalize_validation_errors(
    errors: list[dict[str, Any]] | list[ValidationErrorItem] | None = None,
) -> list[ValidationErrorItem]:
    """다양한 형태의 에러 목록(dict, ValidationErrorItem, 문자열 등)을 ValidationErrorItem 리스트로 정규화한다."""
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
    category: str,
    success: bool,
    errors: list[dict[str, Any]] | list[ValidationErrorItem] | None = None,
) -> FileValidationResult:
    """단일 파일에 대한 FileValidationResult를 생성한다. errors는 자동으로 정규화된다."""
    return FileValidationResult(
        target=target,
        category=category,
        success=success,
        errors=normalize_validation_errors(errors),
    )


def build_output(
    validation_results: list[FileValidationResult],
    validation_summary: str,
    success: bool,
    retry_count: int,
) -> ValidatorOutput:
    """validator 노드의 최종 출력 객체(ValidatorOutput)를 생성한다."""
    return ValidatorOutput(
        validation_results=validation_results,
        validation_summary=validation_summary,
        success=success,
        retry_count=retry_count,
    )


def build_validation_summary(validation_results: list[FileValidationResult]) -> str:
    """검증 결과 목록을 받아 실패 건수를 category별로 집계한 한국어 요약 문자열을 반환한다. 전체 통과 시 성공 메시지를 반환한다."""
    failed_counts: dict[str, int] = {}
    for item in validation_results:
        if item.success:
            continue
        failed_counts[item.category] = failed_counts.get(item.category, 0) + 1

    if not failed_counts:
        return "스키마 검증과 query 결과 기반 정합성 검증을 모두 통과했습니다."

    ordered_parts: list[str] = []
    label_map = {
        "schema": "스키마 실패",
        "query_consistency": "query 정합성 실패",
        "executor_capability": "executor capability 실패",
        "path_issue": "path issue 실패",
    }
    for category in ("schema", "query_consistency", "executor_capability", "path_issue"):
        count = failed_counts.pop(category, 0)
        if count:
            ordered_parts.append(f"{label_map[category]} {count}건")
    for category, count in sorted(failed_counts.items()):
        ordered_parts.append(f"{category} 실패 {count}건")
    return ", ".join(ordered_parts) + "이 있습니다."


def build_state_error(message: str, *, category: str = "query_consistency") -> ValidatorOutput:
    """state 자체에 문제가 있어 검증을 시작할 수 없을 때 즉시 실패 결과를 반환한다. (예: modified_game_state 누락)"""
    logger.warning("[Validator] 조기 종료: %s", message)
    validation_results = [
        build_file_result(
            target="state",
            category=category,
            success=False,
            errors=[{"loc": "$", "msg": message}],
        )
    ]
    return build_output(
        validation_results=validation_results,
        validation_summary=message,
        success=False,
        retry_count=0,
    )


def extract_validation_inputs(
    state: AgentState,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    int,
]:
    """AgentState에서 validator에 필요한 입력값을 추출하고 타입을 정규화해 반환한다.
    반환 순서: current_game_state, modified_game_state, changes_log, retry_count
    """
    current_game_state = state.get("current_game_state", {})
    modified_game_state = state.get("modified_game_state", {})
    changes_log = state.get("changes_log", [])
    retry_count = state.get("retry_count", 0)

    if not isinstance(current_game_state, dict):
        current_game_state = {}
    if not isinstance(modified_game_state, dict):
        modified_game_state = {}
    if not isinstance(changes_log, list):
        changes_log = []
    changes_log = [item for item in changes_log if isinstance(item, dict)]
    try:
        retry_count = int(retry_count)
    except (TypeError, ValueError):
        retry_count = 0

    return (
        current_game_state,
        modified_game_state,
        changes_log,
        retry_count,
    )


def load_validation_payload(file_name: str, value: Any) -> tuple[Any, list[dict[str, Any]]]:
    """게임 state의 단일 파일 항목(snapshot 경로 또는 payload)을 로드한다.
    성공 시 (payload, []) 반환. 실패 시 (None, [에러 dict]) 반환.
    """
    payload = load_snapshot_payload(value)
    if isinstance(payload, dict) and payload.get("_snapshot_error"):
        logger.warning("[Validator] 스냅샷 로드 실패: target=%s err=%s", file_name, payload)
        return None, [{"loc": "$", "msg": str(payload["_snapshot_error"])}]
    return payload, []


def load_validation_entries(
    game_state: dict[str, Any],
) -> dict[str, tuple[Any, list[dict[str, Any]]]]:
    """game_state(파일명 → snapshot 경로/payload 맵)를 받아 각 파일의 payload를 로드한 결과를 반환한다.
    반환값: { 파일명: (payload, 에러 목록) }
    """
    entries: dict[str, tuple[Any, list[dict[str, Any]]]] = {}
    for file_name, value in game_state.items():
        entries[file_name] = load_validation_payload(file_name, value)
    return entries


def select_validation_targets(
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> list[tuple[str, Any, list[dict[str, Any]]]]:
    """로드된 modified_entries에서 스키마 검증 대상 목록을 (파일명, payload, 에러목록) 튜플 리스트로 반환한다."""
    return [
        (file_name, payload, payload_errors)
        for file_name, (payload, payload_errors) in modified_entries.items()
    ]


def calculate_retry_count(retry_count: int, success: bool) -> int:
    """검증 성공이면 retry_count를 유지하고, 실패면 1 증가시켜 반환한다."""
    return retry_count if success else retry_count + 1


def finalize_output(result: ValidatorOutput) -> dict[str, Any]:
    """ValidatorOutput을 JSON 직렬화 가능한 dict로 변환해 반환한다. AgentState에 저장되는 최종 형태다."""
    validated_result = ValidatorOutput.model_validate(result.model_dump(mode="python"))
    return validated_result.model_dump(mode="json")


def _coerce_step_id(value: Any) -> int | None:
    """값을 step_id용 int로 변환한다. 변환 불가능하면 None을 반환한다."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    """값을 int로 변환한다. 변환 불가능하면 None을 반환한다."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_latest_step_log_map(changes_log: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """changes_log(retry로 누적된 전체 로그)에서 step_id별 최신 로그 항목만 추출해 { step_id: log } 맵으로 반환한다.
    같은 step_id가 여러 번 등장하면 마지막 항목이 최신으로 덮어씌워진다.
    """
    latest: dict[int, dict[str, Any]] = {}
    for entry in changes_log:
        step_id = _coerce_step_id(entry.get("step_id"))
        if step_id is None:
            continue
        latest[step_id] = entry
    return latest


def _is_query_action_name(action: str) -> bool:
    """action이 read-only query 계열(query, query_by_id, search)인지 확인한다."""
    return action in _QUERY_ACTIONS


def _get_array_entry_by_id(payload: Any, item_id: int | None) -> dict[str, Any] | None:
    """RPGMaker JSON 배열(인덱스 0은 null)에서 item_id에 해당하는 항목을 반환한다.
    payload가 리스트가 아니거나 범위를 벗어나면 None을 반환한다.
    """
    if item_id is None or not isinstance(payload, list):
        return None
    if item_id < 1 or item_id >= len(payload):
        return None
    entry = payload[item_id]
    return entry if isinstance(entry, dict) else None


def _find_array_id_by_name(payload: Any, name: str | None) -> int | None:
    """RPGMaker JSON 배열에서 name 필드가 일치하는 항목의 인덱스를 반환한다.
    찾지 못하면 None을 반환한다.
    """
    if not isinstance(payload, list) or not name:
        return None
    normalized_name = name.strip()
    if not normalized_name:
        return None
    for index in range(1, len(payload)):
        entry = payload[index]
        if isinstance(entry, dict) and str(entry.get("name") or "").strip() == normalized_name:
            return index
    return None


def _build_query_consistency_failure(target: str, message: str) -> FileValidationResult:
    """정합성 검증 실패 결과를 생성한다. category는 'query_consistency'로 고정된다."""
    return build_file_result(
        target=target,
        category="query_consistency",
        success=False,
        errors=[{"loc": "$", "msg": message}],
    )


def _build_executor_capability_failure(target: str, message: str) -> FileValidationResult:
    """executor가 해당 step을 아예 지원하지 않아 실패한 경우의 결과를 생성한다. category는 'executor_capability'로 고정된다."""
    return build_file_result(
        target=target,
        category="executor_capability",
        success=False,
        errors=[{"loc": "$", "msg": message}],
    )


def validate_create_consistency(
    log: dict[str, Any],
    target_file: str,
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> FileValidationResult | None:
    """create 성공 후 final state에 해당 엔티티가 실제로 존재하는지 확인한다.
    _FILE_ID_FIELD_MAP을 참조해 파일별 ID 필드를 동적으로 결정한다.
    ID 또는 name으로 탐색하며, 존재하지 않으면 실패 결과를 반환한다.
    지원되지 않는 파일(id_field 없음)이면 None을 반환한다.
    """
    id_field = _FILE_ID_FIELD_MAP.get(target_file)
    if id_field is None:
        return None

    entity_id = _coerce_int(log.get(id_field))
    prefix = id_field.replace("_id", "")
    entity_name = str(log.get(f"{prefix}_name") or log.get("name") or "").strip()

    modified_payload = modified_entries.get(target_file, (None, []))[0]
    created_entity = _get_array_entry_by_id(modified_payload, entity_id)
    if created_entity is None and entity_name:
        found_id = _find_array_id_by_name(modified_payload, entity_name)
        created_entity = _get_array_entry_by_id(modified_payload, found_id)

    if created_entity is None:
        label = entity_name or str(entity_id) or "unknown"
        return _build_query_consistency_failure(
            target_file,
            f"create 실행 후 final state에 '{label}'가 없습니다.",
        )
    return None


def validate_update_consistency(
    log: dict[str, Any],
    target_file: str,
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> FileValidationResult | None:
    """update 성공 후 final state에 해당 엔티티가 여전히 존재하는지 확인한다.
    _FILE_ID_FIELD_MAP을 참조해 파일별 ID 필드를 동적으로 결정한다.
    ID를 log에서 확인할 수 없거나 지원되지 않는 파일이면 검증을 skip(None 반환)한다.
    """
    id_field = _FILE_ID_FIELD_MAP.get(target_file)
    if id_field is None:
        return None

    entity_id = _coerce_int(log.get(id_field))
    if entity_id is None:
        return None

    modified_payload = modified_entries.get(target_file, (None, []))[0]
    final_entity = _get_array_entry_by_id(modified_payload, entity_id)

    if final_entity is None:
        return _build_query_consistency_failure(
            target_file,
            f"update 실행 후 final state에 {id_field}={entity_id}가 없습니다.",
        )
    return None


def validate_query_consistency(
    changes_log: list[dict[str, Any]],
    schema_results: list[FileValidationResult],
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> list[FileValidationResult]:
    """changes_log의 각 step을 순회하며 정합성을 검증한다.

    판단 기준:
    - skipped=True인 step → 통과 (executor가 판단한 정당한 skip)
    - success=False인 step → 실패 리포트 (query 실패 포함, 실패한 query는 downstream skip을 유발하므로 반드시 잡아야 함)
    - success=True + query action → 통과 (read-only)
    - success=True + write action → _FILE_ID_FIELD_MAP에 있는 배열 파일이면 final state 대조 검증 수행 (create/update)

    스키마 검증이 이미 실패한 파일은 정합성 검증을 skip한다.
    """
    failures: list[FileValidationResult] = []
    latest_logs = build_latest_step_log_map(changes_log)
    schema_failed_targets = {item.target for item in schema_results if not item.success}

    logger.debug("[Validator] 정합성 검증 시작: steps=%d", len(latest_logs))

    for step_id in sorted(latest_logs):
        log = latest_logs[step_id]
        target_file = str(log.get("target_file") or "").strip()
        action = str(log.get("action") or "").strip().lower()

        # skipped → 정당한 skip, 통과
        if log.get("skipped"):
            logger.debug(
                "[Validator] [정합성] step %s: skip (skipped=true, reason=%s)",
                step_id,
                log.get("skip_reason", ""),
            )
            continue

        # 실패 step → 실패 리포트 (query 포함 — 실패한 query는 downstream skip을 유발)
        if log.get("success") is not True:
            message = str(log.get("stderr") or log.get("error") or "executor step failed").strip()
            logger.warning(
                "[Validator] [실행확인] step %s: 실패 (target=%s, msg=%s)",
                step_id,
                target_file,
                message[:200],
            )
            if "[UNSUPPORTED_STRUCTURED_STEP]" in message:
                failures.append(_build_executor_capability_failure(target_file, message))
            else:
                failures.append(_build_query_consistency_failure(target_file, message))
            continue

        logger.debug(
            "[Validator] [실행확인] step %s: 성공 (target=%s, action=%s)",
            step_id,
            target_file,
            action,
        )

        # 성공한 query → read-only, 통과
        if _is_query_action_name(action):
            logger.debug("[Validator] [정합성] step %s: skip (query 성공, read-only)", step_id)
            continue

        # 성공한 write step → final state 반영 확인
        if target_file in schema_failed_targets:
            logger.debug(
                "[Validator] [정합성] step %s: skip (스키마 이미 실패한 target=%s)",
                step_id,
                target_file,
            )
            continue
        if target_file not in _FILE_ID_FIELD_MAP:
            logger.debug(
                "[Validator] [정합성] step %s: skip (배열 구조 아닌 target=%s)",
                step_id,
                target_file,
            )
            continue
        if action not in {"create", "update"}:
            logger.debug(
                "[Validator] [정합성] step %s: skip (미지원 action=%s, target=%s)",
                step_id,
                action,
                target_file,
            )
            continue

        logger.debug(
            "[Validator] [정합성] step %s: 검증 중 (target=%s, action=%s)",
            step_id,
            target_file,
            action,
        )

        failure: FileValidationResult | None = None
        if action == "create":
            failure = validate_create_consistency(log, target_file, modified_entries)
        elif action == "update":
            failure = validate_update_consistency(log, target_file, modified_entries)

        if failure is not None:
            logger.warning(
                "[Validator] [정합성] step %s: 실패 (target=%s, action=%s) → %s",
                step_id,
                target_file,
                action,
                _format_first_error(failure.errors) if failure.errors else "unknown",
            )
            failures.append(failure)
        else:
            logger.debug(
                "[Validator] [정합성] step %s: 통과 (target=%s, action=%s)",
                step_id,
                target_file,
                action,
            )

    return failures


def _format_first_error(errors: list[dict[str, Any]] | list[ValidationErrorItem]) -> str:
    """에러 목록에서 첫 번째 에러를 'loc=..., msg=...' 형태의 문자열로 반환한다. 로그 출력용."""
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
    """단일 파일의 payload를 Pydantic 스키마로 검증한다.

    - payload_errors가 있으면 로드 실패로 즉시 path_issue 반환
    - 스키마 미지원 파일이면 즉시 schema 실패 반환
    - Pydantic ValidationError 발생 시 전체 에러 목록을 로그에 출력하고 schema 실패 반환
    - 통과 시 schema 성공 반환
    """
    model = resolve_schema(file_name)
    if model is None:
        logger.warning("[Validator] 미지원 스키마: target=%s", file_name)
        return build_file_result(
            target=file_name,
            category="schema",
            success=False,
            errors=[{"loc": "$", "msg": f"unsupported schema for {file_name}"}],
        )

    if payload_errors:
        return build_file_result(
            target=file_name,
            category="path_issue",
            success=False,
            errors=payload_errors,
        )

    try:
        model.model_validate(payload, strict=True)
    except ValidationError as error:
        validation_errors = to_jsonable(error.errors())
        logger.warning(
            "[Validator] 스키마 실패: target=%s, errors=%d건",
            file_name,
            len(validation_errors),
        )
        for i, err in enumerate(validation_errors):
            logger.warning(
                "[Validator]   [%d/%d] loc=%s | msg=%s",
                i + 1,
                len(validation_errors),
                err.get("loc"),
                err.get("msg"),
            )
        return build_file_result(
            target=file_name,
            category="schema",
            success=False,
            errors=validation_errors,
        )

    logger.debug("[Validator] 스키마 통과: target=%s", file_name)
    return build_file_result(
        target=file_name,
        category="schema",
        success=True,
        errors=[],
    )


async def validator(state: AgentState) -> dict[str, Any]:
    """LangGraph validator 노드 진입점.

    실행 순서:
    1. AgentState에서 입력값 추출
    2. modified_game_state의 각 파일에 대해 스키마 검증 수행
    3. changes_log 기반으로 정합성 검증 수행 (executor 실행 결과 vs final state 대조)
    4. 결과를 합산해 success 판정 및 retry_count 갱신 후 반환

    반환값은 AgentState에 병합된다: validation_results, validation_summary, success, retry_count
    """
    (
        current_game_state,
        modified_game_state,
        changes_log,
        retry_count,
    ) = extract_validation_inputs(state)

    _t0 = time.perf_counter()
    logger.info("─── 🔎 Validator START ──────────────────────────────")
    logger.info("[Validator] 시작: files=%d, retry=%d", len(modified_game_state), retry_count)

    if not modified_game_state:
        result = build_state_error("modified_game_state is missing or empty.")
    else:
        _current_entries = load_validation_entries(current_game_state)
        modified_entries = load_validation_entries(modified_game_state)
        validation_targets = select_validation_targets(modified_entries)

        target_names = [file_name for file_name, _, _ in validation_targets]
        logger.info("[Validator] 스키마 검증 시작: %s", target_names)
        schema_results = [
            validate_single_file(file_name, payload, payload_errors)
            for file_name, payload, payload_errors in validation_targets
        ]
        schema_failed = [r for r in schema_results if not r.success]
        logger.info(
            "[Validator] 스키마 검증 완료: total=%d, failed=%d",
            len(schema_results),
            len(schema_failed),
        )
        for r in schema_failed:
            first_err = _format_first_error(r.errors) if r.errors else "no error detail"
            logger.warning("[Validator]   스키마 실패 파일: %s | %s", r.target, first_err)

        consistency_results = validate_query_consistency(
            changes_log,
            schema_results,
            modified_entries,
        )
        consistency_failed = [r for r in consistency_results if not r.success]
        logger.info(
            "[Validator] 정합성 검증 완료: total=%d, failed=%d",
            len(consistency_results),
            len(consistency_failed),
        )
        for r in consistency_failed:
            first_err = _format_first_error(r.errors) if r.errors else "no error detail"
            logger.warning("[Validator] 정합성 실패: %s | %s", r.target, first_err)

        final_results = schema_results + consistency_results
        success = all(item.success for item in final_results)
        logger.info(
            "[Validator] 최종 판정: success=%s (스키마 실패=%d, 정합성 실패=%d)",
            success,
            len(schema_failed),
            len(consistency_failed),
        )
        result = build_output(
            validation_results=final_results,
            validation_summary=build_validation_summary(final_results),
            success=success,
            retry_count=retry_count,
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
