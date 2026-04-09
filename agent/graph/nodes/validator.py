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
_SUPPORTED_CONSISTENCY_ACTIONS = {
    "Actors.json": {"create", "update"},
    "Classes.json": {"create"},
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
    category: str,
    success: bool,
    errors: list[dict[str, Any]] | list[ValidationErrorItem] | None = None,
) -> FileValidationResult:
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
    return ValidatorOutput(
        validation_results=validation_results,
        validation_summary=validation_summary,
        success=success,
        retry_count=retry_count,
    )


def build_validation_summary(validation_results: list[FileValidationResult]) -> str:
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
    list[dict[str, Any]],
    int,
]:
    current_game_state = state.get("current_game_state", {})
    modified_game_state = state.get("modified_game_state", {})
    execution_plan = state.get("execution_plan", [])
    changes_log = state.get("changes_log", [])
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
    try:
        retry_count = int(retry_count)
    except (TypeError, ValueError):
        retry_count = 0

    return (
        current_game_state,
        modified_game_state,
        execution_plan,
        changes_log,
        retry_count,
    )


def load_validation_payload(file_name: str, value: Any) -> tuple[Any, list[dict[str, Any]]]:
    payload = load_snapshot_payload(value)
    if isinstance(payload, dict) and payload.get("_snapshot_error"):
        logger.warning("[Validator] 스냅샷 로드 실패: target=%s err=%s", file_name, payload)
        return None, [{"loc": "$", "msg": str(payload["_snapshot_error"])}]
    return payload, []


def load_validation_entries(
    game_state: dict[str, Any],
) -> dict[str, tuple[Any, list[dict[str, Any]]]]:
    entries: dict[str, tuple[Any, list[dict[str, Any]]]] = {}
    for file_name, value in game_state.items():
        entries[file_name] = load_validation_payload(file_name, value)
    return entries


def select_validation_targets(
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> list[tuple[str, Any, list[dict[str, Any]]]]:
    return [
        (file_name, payload, payload_errors)
        for file_name, (payload, payload_errors) in modified_entries.items()
    ]


def calculate_retry_count(retry_count: int, success: bool) -> int:
    return retry_count if success else retry_count + 1


def finalize_output(result: ValidatorOutput) -> dict[str, Any]:
    validated_result = ValidatorOutput.model_validate(result.model_dump(mode="python"))
    return validated_result.model_dump(mode="json")


def _coerce_step_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_step_id_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    normalized: list[int] = []
    seen: set[int] = set()
    for item in value:
        step_id = _coerce_step_id(item)
        if step_id is None or step_id in seen:
            continue
        normalized.append(step_id)
        seen.add(step_id)
    return normalized


def _normalize_id_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    normalized: list[int] = []
    for item in value:
        coerced = _coerce_int(item)
        if coerced is not None:
            normalized.append(coerced)
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def build_plan_step_map(execution_plan: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for step in execution_plan:
        step_id = _coerce_step_id(step.get("step_id"))
        if step_id is None:
            continue
        by_id[step_id] = step
    return by_id


def build_latest_step_log_map(changes_log: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for entry in changes_log:
        step_id = _coerce_step_id(entry.get("step_id"))
        if step_id is None:
            continue
        latest[step_id] = entry
    return latest


def _normalize_action_name(step: dict[str, Any] | None, log: dict[str, Any]) -> str:
    action = str(log.get("action") or (step or {}).get("action_type") or "").strip().lower()
    return "update" if action == "update_actor" else action


def _is_query_action_name(action: str) -> bool:
    return action in _QUERY_ACTIONS


def _normalize_query_result(
    query_result: dict[str, Any],
    *,
    default_query_type: str,
    default_query: dict[str, Any],
) -> dict[str, Any]:
    matched_ids = _normalize_id_list(query_result.get("matched_ids"))
    hit_count = _coerce_int(query_result.get("hit_count"))
    if hit_count is None:
        hit_count = len(matched_ids)
    not_found = query_result.get("not_found")
    if not isinstance(not_found, bool):
        not_found = hit_count == 0 and not matched_ids

    normalized = {
        "query_type": str(query_result.get("query_type") or default_query_type or "query"),
        "query": query_result.get("query")
        if isinstance(query_result.get("query"), dict)
        else default_query,
        "hit_count": max(hit_count, 0),
        "matched_ids": matched_ids,
        "not_found": bool(not_found),
    }
    matched_names = _normalize_string_list(query_result.get("matched_names"))
    if matched_names:
        normalized["matched_names"] = matched_names
    return normalized


def _build_legacy_query_result(
    target_file: str,
    action: str,
    log: dict[str, Any],
    step: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if target_file == "Actors.json":
        actor_id = _coerce_int(log.get("actor_id"))
        if actor_id is None and action == "query_by_id":
            actor_id = _coerce_int(((step or {}).get("target_info") or {}).get("actor_id"))
        exists = log.get("exists")
        if not isinstance(exists, bool):
            return None
        matched_ids = [actor_id] if actor_id is not None and exists else []
        hit_count = len(matched_ids) if matched_ids else (1 if exists else 0)
        return _normalize_query_result(
            {
                "query_type": action,
                "query": (step or {}).get("target_info") or {},
                "hit_count": hit_count,
                "matched_ids": matched_ids,
                "not_found": not exists,
            },
            default_query_type=action,
            default_query=(step or {}).get("target_info") or {},
        )

    if target_file == "Classes.json":
        class_id = _coerce_int(log.get("class_id"))
        exists = log.get("exists")
        if not isinstance(exists, bool):
            return None
        matched_ids = [class_id] if class_id is not None and exists else []
        hit_count = len(matched_ids) if matched_ids else (1 if exists else 0)
        return _normalize_query_result(
            {
                "query_type": action,
                "query": (step or {}).get("target_info") or {},
                "hit_count": hit_count,
                "matched_ids": matched_ids,
                "not_found": not exists,
            },
            default_query_type=action,
            default_query=(step or {}).get("target_info") or {},
        )

    return None


def extract_query_result(
    log: dict[str, Any], step: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    target_file = str(log.get("target_file") or (step or {}).get("target_file") or "").strip()
    action = _normalize_action_name(step, log)
    query_result = log.get("query_result")

    if isinstance(query_result, dict):
        return _normalize_query_result(
            query_result,
            default_query_type=action or "query",
            default_query=(step or {}).get("target_info") or {},
        )

    if not target_file or not _is_query_action_name(action):
        return None
    return _build_legacy_query_result(target_file, action, log, step)


def _normalize_name(value: Any) -> str:
    return str(value or "").strip()


def _extract_step_target_identity(
    target_file: str,
    step: dict[str, Any],
    log: dict[str, Any],
) -> tuple[int | None, str]:
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}

    if target_file == "Actors.json":
        actor_id = _coerce_int(log.get("actor_id"))
        if actor_id is None:
            actor_id = _coerce_int(target_info.get("actor_id") or target_info.get("actorId"))
        return actor_id, _extract_actor_name(step, log)

    if target_file == "Classes.json":
        class_id = _coerce_int(log.get("class_id"))
        if class_id is None:
            class_id = _coerce_int(target_info.get("class_id") or target_info.get("classId"))
        return class_id, _extract_class_name(step, log)

    return None, ""


def _extract_query_identity(
    target_file: str,
    query_result: dict[str, Any],
) -> tuple[int | None, list[int], set[str]]:
    query = query_result.get("query") if isinstance(query_result.get("query"), dict) else {}
    matched_ids = _normalize_id_list(query_result.get("matched_ids"))
    matched_names = {
        _normalize_name(item) for item in _normalize_string_list(query_result.get("matched_names"))
    }
    matched_names.discard("")

    if target_file == "Actors.json":
        query_id = _coerce_int(query.get("actor_id") or query.get("actorId"))
        query_name = _normalize_name(query.get("actor_name") or query.get("name"))
    elif target_file == "Classes.json":
        query_id = _coerce_int(query.get("class_id") or query.get("classId"))
        query_name = _normalize_name(query.get("class_name") or query.get("name"))
    else:
        query_id = None
        query_name = ""

    if query_name:
        matched_names.add(query_name)
    return query_id, matched_ids, matched_names


def _query_reference_match_score(
    target_file: str,
    step: dict[str, Any],
    log: dict[str, Any],
    query_result: dict[str, Any],
) -> int:
    target_id, target_name = _extract_step_target_identity(target_file, step, log)
    if target_id is None and not target_name:
        return 0

    query_id, matched_ids, matched_names = _extract_query_identity(target_file, query_result)
    score = 0

    if target_id is not None:
        if query_id is not None:
            if query_id != target_id:
                return 0
            score += 3
        if matched_ids:
            if target_id not in matched_ids:
                return 0
            score += 2

    if target_name:
        if matched_names:
            if target_name not in matched_names:
                return 0
            score += 1

    return score


def _resolve_best_query_candidate(
    step: dict[str, Any],
    log: dict[str, Any],
    latest_logs: dict[int, dict[str, Any]],
    plan_steps: dict[int, dict[str, Any]],
    candidate_ids: list[int],
    *,
    allow_zero_score: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    target_file = str(log.get("target_file") or step.get("target_file") or "").strip()
    if not target_file:
        return None, None

    best_score = 0
    best_id: int | None = None
    best_log: dict[str, Any] | None = None
    best_result: dict[str, Any] | None = None
    fallback_id: int | None = None
    fallback_log: dict[str, Any] | None = None
    fallback_result: dict[str, Any] | None = None

    for candidate_id in candidate_ids:
        candidate_log = latest_logs.get(candidate_id)
        candidate_step = plan_steps.get(candidate_id)
        query_result = extract_query_result(candidate_log or {}, candidate_step)
        if candidate_log is None or query_result is None:
            continue

        if allow_zero_score and (fallback_id is None or candidate_id > fallback_id):
            fallback_id = candidate_id
            fallback_log = candidate_log
            fallback_result = query_result

        score = _query_reference_match_score(target_file, step, log, query_result)
        if score <= 0:
            continue
        if score > best_score or (
            score == best_score and (best_id is None or candidate_id > best_id)
        ):
            best_score = score
            best_id = candidate_id
            best_log = candidate_log
            best_result = query_result

    if best_log is not None and best_result is not None:
        return best_log, best_result
    if allow_zero_score:
        return fallback_log, fallback_result
    return best_log, best_result


def _find_fallback_query_step_id(
    step: dict[str, Any],
    log: dict[str, Any],
    latest_logs: dict[int, dict[str, Any]],
    plan_steps: dict[int, dict[str, Any]],
) -> int | None:
    step_id = _coerce_step_id(step.get("step_id")) or _coerce_step_id(log.get("step_id")) or -1
    target_file = str(log.get("target_file") or step.get("target_file") or "").strip()
    if not target_file:
        return None

    best_score = 0
    best_id: int | None = None
    for candidate_id in sorted(latest_logs, reverse=True):
        if candidate_id >= step_id:
            continue
        candidate_log = latest_logs[candidate_id]
        candidate_step = plan_steps.get(candidate_id)
        candidate_target = str(
            candidate_log.get("target_file") or (candidate_step or {}).get("target_file") or ""
        ).strip()
        if candidate_target != target_file:
            continue
        query_result = extract_query_result(candidate_log, candidate_step)
        if query_result is None:
            continue
        score = _query_reference_match_score(target_file, step, log, query_result)
        if score > best_score:
            best_score = score
            best_id = candidate_id
    return best_id


def resolve_query_reference(
    step: dict[str, Any],
    log: dict[str, Any],
    latest_logs: dict[int, dict[str, Any]],
    plan_steps: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current_query_result = extract_query_result(log, step)
    target_file = str(log.get("target_file") or step.get("target_file") or "").strip()
    if (
        isinstance(log.get("query_result"), dict)
        and current_query_result is not None
        and _query_reference_match_score(target_file, step, log, current_query_result) > 0
    ):
        return log, current_query_result

    decision_basis = (
        log.get("decision_basis") if isinstance(log.get("decision_basis"), dict) else {}
    )
    source_ids = _normalize_step_id_list(decision_basis.get("source_query_step_ids"))
    if source_ids:
        query_log, query_result = _resolve_best_query_candidate(
            step,
            log,
            latest_logs,
            plan_steps,
            source_ids,
            allow_zero_score=True,
        )
        if query_log is not None and query_result is not None:
            return query_log, query_result

    dep_source_ids: list[int] = []
    for dep_id in _normalize_step_id_list(step.get("depends_on")):
        dep_step = plan_steps.get(dep_id)
        dep_log = latest_logs.get(dep_id)
        dep_action = _normalize_action_name(dep_step, dep_log or {})
        if extract_query_result(dep_log or {}, dep_step) is not None or _is_query_action_name(
            dep_action
        ):
            dep_source_ids.append(dep_id)

    if dep_source_ids:
        query_log, query_result = _resolve_best_query_candidate(
            step,
            log,
            latest_logs,
            plan_steps,
            dep_source_ids,
            allow_zero_score=True,
        )
        if query_log is not None and query_result is not None:
            return query_log, query_result

    fallback_step_id = _find_fallback_query_step_id(step, log, latest_logs, plan_steps)
    if fallback_step_id is None:
        return None, None

    fallback_log = latest_logs.get(fallback_step_id)
    fallback_step = plan_steps.get(fallback_step_id)
    fallback_result = extract_query_result(fallback_log or {}, fallback_step)
    if fallback_log is not None and fallback_result is not None:
        return fallback_log, fallback_result
    return None, None


def _query_is_not_found(query_result: dict[str, Any]) -> bool:
    return bool(query_result.get("not_found"))


def _query_single_match_id(query_result: dict[str, Any]) -> int | None:
    matched_ids = _normalize_id_list(query_result.get("matched_ids"))
    return matched_ids[0] if len(matched_ids) == 1 else None


def _get_array_entry_by_id(payload: Any, item_id: int | None) -> dict[str, Any] | None:
    if item_id is None or not isinstance(payload, list):
        return None
    if item_id < 1 or item_id >= len(payload):
        return None
    entry = payload[item_id]
    return entry if isinstance(entry, dict) else None


def _find_array_id_by_name(payload: Any, name: str | None) -> int | None:
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
    return build_file_result(
        target=target,
        category="query_consistency",
        success=False,
        errors=[{"loc": "$", "msg": message}],
    )


def _build_executor_capability_failure(target: str, message: str) -> FileValidationResult:
    return build_file_result(
        target=target,
        category="executor_capability",
        success=False,
        errors=[{"loc": "$", "msg": message}],
    )


def _extract_actor_name(step: dict[str, Any], log: dict[str, Any]) -> str:
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    return str(
        log.get("actor_name")
        or target_info.get("actor_name")
        or target_info.get("name")
        or target_info.get("new_name")
        or ""
    ).strip()


def _extract_class_name(step: dict[str, Any], log: dict[str, Any]) -> str:
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    return str(
        log.get("class_name") or target_info.get("class_name") or target_info.get("name") or ""
    ).strip()


def validate_actors_create_consistency(
    step: dict[str, Any],
    log: dict[str, Any],
    query_result: dict[str, Any],
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> FileValidationResult | None:
    actor_name = _extract_actor_name(step, log)
    modified_payload = modified_entries.get("Actors.json", (None, []))[0]
    is_skip = bool(log.get("skipped"))

    if is_skip:
        if _query_is_not_found(query_result):
            return _build_query_consistency_failure(
                "Actors.json",
                "query 결과는 not_found인데 create를 skip했습니다.",
            )
        if actor_name and _find_array_id_by_name(modified_payload, actor_name) is None:
            return _build_query_consistency_failure(
                "Actors.json",
                f"query 결과상 이미 존재해서 create를 skip했지만 final state에 actor '{actor_name}'가 없습니다.",
            )
        return None

    if _query_is_not_found(query_result) is False:
        return _build_query_consistency_failure(
            "Actors.json",
            "query 결과상 이미 존재하는 actor인데 create를 진행했습니다.",
        )

    actor_id = _coerce_int(log.get("actor_id"))
    created_actor = _get_array_entry_by_id(modified_payload, actor_id)
    if created_actor is None and actor_name:
        created_actor_id = _find_array_id_by_name(modified_payload, actor_name)
        created_actor = _get_array_entry_by_id(modified_payload, created_actor_id)

    if created_actor is None:
        label = actor_name or "target actor"
        return _build_query_consistency_failure(
            "Actors.json",
            f"query 결과는 not_found라서 create를 진행했지만 final state에 actor '{label}'가 없습니다.",
        )
    return None


def validate_classes_create_consistency(
    step: dict[str, Any],
    log: dict[str, Any],
    query_result: dict[str, Any],
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> FileValidationResult | None:
    class_name = _extract_class_name(step, log)
    modified_payload = modified_entries.get("Classes.json", (None, []))[0]
    is_skip = bool(log.get("skipped"))

    if is_skip:
        if _query_is_not_found(query_result):
            return _build_query_consistency_failure(
                "Classes.json",
                "query 결과는 not_found인데 create를 skip했습니다.",
            )
        if class_name and _find_array_id_by_name(modified_payload, class_name) is None:
            return _build_query_consistency_failure(
                "Classes.json",
                f"query 결과상 이미 존재해서 create를 skip했지만 final state에 class '{class_name}'가 없습니다.",
            )
        return None

    if _query_is_not_found(query_result) is False:
        return _build_query_consistency_failure(
            "Classes.json",
            "query 결과상 이미 존재하는 class인데 create를 진행했습니다.",
        )

    class_id = _coerce_int(log.get("class_id"))
    created_class = _get_array_entry_by_id(modified_payload, class_id)
    if created_class is None and class_name:
        created_class_id = _find_array_id_by_name(modified_payload, class_name)
        created_class = _get_array_entry_by_id(modified_payload, created_class_id)

    if created_class is None:
        label = class_name or "target class"
        return _build_query_consistency_failure(
            "Classes.json",
            f"query 결과는 not_found라서 create를 진행했지만 final state에 class '{label}'가 없습니다.",
        )
    return None


def validate_actors_update_consistency(
    step: dict[str, Any],
    log: dict[str, Any],
    query_result: dict[str, Any],
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> FileValidationResult | None:
    if _query_is_not_found(query_result):
        return _build_query_consistency_failure(
            "Actors.json",
            "query 결과가 대상을 찾지 못했는데 update를 진행했습니다.",
        )

    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    matched_ids = _normalize_id_list(query_result.get("matched_ids"))
    expected_actor_id = _query_single_match_id(query_result)
    target_actor_id = _coerce_int(log.get("actor_id"))
    if target_actor_id is None:
        target_actor_id = _coerce_int(target_info.get("actor_id") or target_info.get("actorId"))

    if (
        expected_actor_id is not None
        and target_actor_id is not None
        and expected_actor_id != target_actor_id
    ):
        return _build_query_consistency_failure(
            "Actors.json",
            f"query 결과는 actor_id={expected_actor_id}인데 후속 update는 actor_id={target_actor_id}를 대상으로 했습니다.",
        )

    if matched_ids and target_actor_id is not None and target_actor_id not in matched_ids:
        return _build_query_consistency_failure(
            "Actors.json",
            f"query 결과의 matched_ids={matched_ids}인데 후속 update는 actor_id={target_actor_id}를 대상으로 했습니다.",
        )

    final_actor_id = target_actor_id or expected_actor_id
    final_actor = _get_array_entry_by_id(
        modified_entries.get("Actors.json", (None, []))[0], final_actor_id
    )
    if final_actor is None:
        target_label = final_actor_id if final_actor_id is not None else "unknown"
        return _build_query_consistency_failure(
            "Actors.json",
            f"query 결과가 가리킨 actor_id={target_label}에 대한 final state 반영을 확인할 수 없습니다.",
        )

    class_id = _coerce_int(log.get("class_id"))
    if class_id is None:
        class_id = _coerce_int(target_info.get("class_id") or target_info.get("classId"))
    if class_id is not None and _coerce_int(final_actor.get("classId")) != class_id:
        return _build_query_consistency_failure(
            "Actors.json",
            f"query 결과가 가리킨 actor_id={final_actor_id}의 classId가 final state에서 {class_id}로 반영되지 않았습니다.",
        )

    updates = target_info.get("updates") if isinstance(target_info.get("updates"), dict) else {}
    for field, expected_value in updates.items():
        if final_actor.get(field) != expected_value:
            return _build_query_consistency_failure(
                "Actors.json",
                f"query 결과가 가리킨 actor_id={final_actor_id}의 field '{field}'가 final state에 올바르게 반영되지 않았습니다.",
            )

    new_name = str(target_info.get("new_name") or "").strip()
    if new_name and str(final_actor.get("name") or "").strip() != new_name:
        return _build_query_consistency_failure(
            "Actors.json",
            f"query 결과가 가리킨 actor_id={final_actor_id}의 이름 변경이 final state에 반영되지 않았습니다.",
        )

    return None


def validate_query_consistency(
    execution_plan: list[dict[str, Any]],
    changes_log: list[dict[str, Any]],
    schema_results: list[FileValidationResult],
    modified_entries: dict[str, tuple[Any, list[dict[str, Any]]]],
) -> list[FileValidationResult]:
    failures: list[FileValidationResult] = []
    latest_logs = build_latest_step_log_map(changes_log)
    plan_steps = build_plan_step_map(execution_plan)
    schema_failed_targets = {item.target for item in schema_results if not item.success}

    logger.debug("[Validator] consistency 검사 시작: steps=%d", len(latest_logs))

    # Pass 1: executor step 자체 실패 감지
    for step_id in sorted(latest_logs):
        log = latest_logs[step_id]
        step = plan_steps.get(step_id)
        target_file = str(
            log.get("target_file") or (step or {}).get("target_file") or "state"
        ).strip()
        if log.get("success") is True:
            logger.debug("[Validator] step %s: executor 성공 (target=%s)", step_id, target_file)
            continue

        message = str(log.get("stderr") or log.get("error") or "executor step failed").strip()
        logger.warning(
            "[Validator] step %s: executor 실패 → consistency 실패 추가 (target=%s, msg=%s)",
            step_id, target_file, message[:200],
        )
        if "[UNSUPPORTED_STRUCTURED_STEP]" in message:
            failures.append(_build_executor_capability_failure(target_file, message))
            continue
        failures.append(_build_query_consistency_failure(target_file, message))

    # Pass 2: query 기반 정합성 검사
    for step_id in sorted(latest_logs):
        log = latest_logs[step_id]
        step = plan_steps.get(step_id, {})

        target_file = str(log.get("target_file") or step.get("target_file") or "").strip()
        action = _normalize_action_name(step, log)

        if target_file in schema_failed_targets:
            logger.debug(
                "[Validator] step %s: skip (schema 이미 실패한 target=%s)", step_id, target_file
            )
            continue
        if target_file not in _SUPPORTED_CONSISTENCY_ACTIONS:
            logger.debug(
                "[Validator] step %s: skip (consistency 미지원 target=%s, action=%s)",
                step_id, target_file, action,
            )
            continue
        if action not in _SUPPORTED_CONSISTENCY_ACTIONS[target_file]:
            logger.debug(
                "[Validator] step %s: skip (지원 안 되는 action=%s, target=%s)",
                step_id, action, target_file,
            )
            continue
        if log.get("success") is not True and not log.get("skipped"):
            logger.debug(
                "[Validator] step %s: skip (executor 미성공 + skipped 아님, success=%s)",
                step_id, log.get("success"),
            )
            continue

        logger.debug(
            "[Validator] step %s: query consistency 검사 중 (target=%s, action=%s)",
            step_id, target_file, action,
        )

        _query_log, query_result = resolve_query_reference(
            step,
            log,
            latest_logs,
            plan_steps,
        )
        if query_result is None:
            msg = f"query 기반 판단이 필요한 {action}인데 참조 가능한 query_result 근거 로그가 없습니다."
            logger.warning("[Validator] step %s: query_result 없음 → 실패 (target=%s)", step_id, target_file)
            failures.append(_build_query_consistency_failure(target_file, msg))
            continue

        logger.debug("[Validator] step %s: query_result 확보됨, 세부 검증 진행", step_id)

        failure: FileValidationResult | None = None
        if target_file == "Actors.json" and action == "create":
            failure = validate_actors_create_consistency(step, log, query_result, modified_entries)
        elif target_file == "Actors.json" and action == "update":
            failure = validate_actors_update_consistency(step, log, query_result, modified_entries)
        elif target_file == "Classes.json" and action == "create":
            failure = validate_classes_create_consistency(step, log, query_result, modified_entries)

        if failure is not None:
            logger.warning(
                "[Validator] step %s: consistency 실패 (target=%s, action=%s) → %s",
                step_id, target_file, action,
                _format_first_error(failure.errors) if failure.errors else "unknown",
            )
            failures.append(failure)
        else:
            logger.debug(
                "[Validator] step %s: consistency 통과 (target=%s, action=%s)",
                step_id, target_file, action,
            )

    return failures


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
    (
        current_game_state,
        modified_game_state,
        execution_plan,
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

        schema_results = [
            validate_single_file(file_name, payload, payload_errors)
            for file_name, payload, payload_errors in validation_targets
        ]
        schema_failed = [r for r in schema_results if not r.success]
        logger.info(
            "[Validator] 스키마 검증 완료: total=%d, failed=%d",
            len(schema_results), len(schema_failed),
        )
        for r in schema_failed:
            first_err = _format_first_error(r.errors) if r.errors else "no error detail"
            logger.warning("[Validator]   스키마 실패 파일: %s | %s", r.target, first_err)

        consistency_results = validate_query_consistency(
            execution_plan,
            changes_log,
            schema_results,
            modified_entries,
        )
        consistency_failed = [r for r in consistency_results if not r.success]
        logger.info(
            "[Validator] consistency 검증 완료: total=%d, failed=%d",
            len(consistency_results), len(consistency_failed),
        )
        for r in consistency_failed:
            first_err = _format_first_error(r.errors) if r.errors else "no error detail"
            logger.warning("[Validator]   consistency 실패: %s | %s", r.target, first_err)

        final_results = schema_results + consistency_results
        success = all(item.success for item in final_results)
        logger.info(
            "[Validator] 최종 판정: success=%s (schema_fail=%d, consistency_fail=%d)",
            success, len(schema_failed), len(consistency_failed),
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
