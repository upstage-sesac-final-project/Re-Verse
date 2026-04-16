"""Rule engine — 의존성 그래프 워크 + 실제 파일 확인 → execution_plan 생성.

LLM 0회. 순수 Python 결정론.

intake 의 operation_tuples 를 받아서:
  1. 각 operation 에 대해 WRITE_DEPENDENCIES 를 lookup
  2. 실제 게임 파일을 열어 Requirement 존재 여부를 확인
  3. 없으면 create step 을 앞에 추가
  4. topological sort 된 execution_plan (executor_yb 포맷) 반환
"""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from agent.constants import (
    ARRAY_FIELDS,
    FIELD_REROUTE_FIXES,
    FUZZY_THRESHOLD,
    SYSTEM_DEDICATED_FIELDS,
    SYSTEM_TYPE_ARRAY_NAMES,
)
from agent.editor.nodes.planner.array_op_resolver import resolve_array_op
from agent.editor.nodes.planner.dependencies import (
    Requirement,
    lookup_requirements,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 파일 유틸
# ──────────────────────────────────────────────


def _load_json(data_path: Path, filename: str) -> Any:
    fp = data_path / filename
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def _find_entity_by_name(data: list, name: str, threshold: float = FUZZY_THRESHOLD) -> dict | None:
    """이름 완전 일치 → 부분 일치 → fuzzy 매칭 순서로 탐색."""
    if not name or not isinstance(data, list):
        return None
    t = name.strip().lower()
    # 1. 완전 일치
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("name") or "").strip().lower() == t:
            return entry
    # 2. fuzzy
    best_entry, best_ratio = None, 0.0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        entry_name = str(entry.get("name") or "").strip().lower()
        if not entry_name:
            continue
        ratio = SequenceMatcher(None, t, entry_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_entry = entry
    if best_ratio >= threshold:
        return best_entry
    return None


def _find_entity_by_index(data: list, index: int) -> dict | None:
    """1-based 순서 인덱스로 엔티티를 찾는다.

    RPG Maker 배열은 [null, {id:1, ...}, {id:2, ...}, ...] 형태이므로
    index=1 → data[1], index=2 → data[2], ...
    """
    if not isinstance(data, list) or index < 1:
        return None
    if index < len(data) and isinstance(data[index], dict):
        return data[index]
    return None


def _find_in_system_type_list(system_data: dict, key: str, name: str) -> int | None:
    """System.json 의 배열(armorTypes 등)에서 문자열 검색 → index 반환."""
    arr = system_data.get(key)
    if not isinstance(arr, list):
        return None
    t = name.strip().lower()
    for idx, val in enumerate(arr):
        if isinstance(val, str) and val.strip().lower() == t:
            return idx
    return None


def _next_system_type_index(system_data: dict, key: str) -> int:
    """System.json 타입 배열에 추가할 다음 인덱스."""
    arr = system_data.get(key)
    if not isinstance(arr, list):
        return 1
    return len(arr)


# 파일 재라우팅 시 field 가 새 파일과 호환되지 않을 때 교정하는 규칙
# (원래 field, 새 파일이 아닌 파일 종류) → (교정된 field, 추가 value 패치)
# FIELD_REROUTE_FIXES 는 agent.constants 에서 import


def _fix_field_after_reroute(
    op: dict,
    new_file: str,
    field: str | None,
    value: dict,
) -> tuple[dict, str | None, dict]:
    """파일 재라우팅 후 field 호환성 교정."""
    if not field or field not in FIELD_REROUTE_FIXES:
        return op, field, value
    # Skills.json 전용 field 가 다른 파일로 갔을 때만 교정
    if new_file == "Skills.json":
        return op, field, value

    fix = FIELD_REROUTE_FIXES[field]
    new_field = fix["field"]
    value_patch = fix.get("value_patch", {})

    op = dict(op)
    op["field"] = new_field
    value = dict(value)
    value.update(value_patch)
    op["value"] = value

    logger.info(
        "[planner] field '%s' → '%s' 교정 (파일 %s 호환)",
        field,
        new_field,
        new_file,
    )
    return op, new_field, value


def _next_entity_id(data: list) -> int:
    """DB 배열에서 다음 id (null 슬롯 우선)."""
    for i in range(1, len(data)):
        if data[i] is None:
            return i
    return len(data)


# ──────────────────────────────────────────────
# System.json 전용 플래닝
# ──────────────────────────────────────────────

# SYSTEM_DEDICATED_FIELDS, SYSTEM_TYPE_ARRAY_NAMES 는 agent.constants 에서 import


def _extract_system_value(value: dict) -> Any:
    """OperationValue dict 에서 실제 값을 꺼낸다 (new_value > ref > name > amount 순)."""
    for key in ("new_value", "ref", "name", "amount"):
        v = value.get(key)
        if v is not None:
            return v
    return None


def _plan_system_operation(
    action: str,
    field: str | None,
    value: dict,
    step_offset: int,
) -> list[dict]:
    """System.json 전용 step 생성. 엔티티 로직을 타지 않는다."""

    # ── read ──
    if action == "read":
        return [
            {
                "step_id": step_offset,
                "action_type": "get_system",
                "target_file": "System.json",
                "target_info": {"field": field},
                "depends_on": [],
                "description": "System.json 조회" + (f" ({field})" if field else ""),
                "_op_action": "read",
            }
        ]

    if action != "update":
        return [
            {
                "step_id": step_offset,
                "action_type": "error",
                "target_file": "System.json",
                "target_info": {"error": f"System.json 은 {action} 을(를) 지원하지 않습니다"},
                "depends_on": [],
                "description": f"System.json {action} 미지원",
                "_op_action": action,
            }
        ]

    # ── update ──
    if not field:
        return [
            {
                "step_id": step_offset,
                "action_type": "error",
                "target_file": "System.json",
                "target_info": {"error": "System.json update 에는 field 가 필요합니다"},
                "depends_on": [],
                "description": "System.json update: field 누락",
                "_op_action": "update",
            }
        ]

    raw_value = _extract_system_value(value)

    # 1) 전용 액션이 있는 필드
    dedicated = SYSTEM_DEDICATED_FIELDS.get(field)
    if dedicated:
        target_info: dict[str, Any] = {}
        if dedicated == "update_game_title":
            target_info["title"] = raw_value
        return [
            {
                "step_id": step_offset,
                "action_type": dedicated,
                "target_file": "System.json",
                "target_info": target_info,
                "depends_on": [],
                "description": f"System.json {field} 업데이트",
                "_op_action": "update",
            }
        ]

    # 2) 타입 배열 추가
    if field in SYSTEM_TYPE_ARRAY_NAMES:
        return [
            {
                "step_id": step_offset,
                "action_type": "append_system_type",
                "target_file": "System.json",
                "target_info": {"system_key": field, "value": raw_value or ""},
                "depends_on": [],
                "description": f"System.json['{field}'] 에 항목 추가",
                "_op_action": "update",
            }
        ]

    # 3) variables / switches (field 에 인덱스 포함: "variables.42", "switches.5")
    for prefix, action_type in (
        ("variables", "set_variable_name"),
        ("switches", "set_switch_name"),
    ):
        if field.startswith(prefix):
            parts = field.split(".", 1)
            idx = int(parts[1]) if len(parts) > 1 else None
            id_key = "variableId" if prefix == "variables" else "switchId"
            target_info = {"name": raw_value}
            if idx is not None:
                target_info[id_key] = idx
            return [
                {
                    "step_id": step_offset,
                    "action_type": action_type,
                    "target_file": "System.json",
                    "target_info": target_info,
                    "depends_on": [],
                    "description": f"System.json {field} 이름 설정",
                    "_op_action": "update",
                }
            ]

    # 3.5) partyMembers — add/remove party member
    if field == "partyMembers":
        array_op = value.get("array_op") if isinstance(value, dict) else None
        if array_op not in ("add", "remove"):
            array_op = "add"
        action_type = "add_party_member" if array_op == "add" else "remove_party_member"
        actor_name = None
        actor_id = None
        if isinstance(value, dict):
            actor_name = value.get("ref")
            actor_id = value.get("resolved_id")
        target_info: dict[str, Any] = {"party_action": array_op}
        if actor_name:
            target_info["actor_name"] = actor_name
        if actor_id is not None:
            target_info["actor_id"] = actor_id
        return [
            {
                "step_id": step_offset,
                "action_type": action_type,
                "target_file": "System.json",
                "target_info": target_info,
                "depends_on": [],
                "description": f"System.partyMembers {array_op} '{actor_name or '?'}'",
                "_op_action": "update",
            }
        ]

    # 4) 그 외 → 범용 update_system_field
    return [
        {
            "step_id": step_offset,
            "action_type": "update_system_field",
            "target_file": "System.json",
            "target_info": {"key_path": field, "value": raw_value},
            "depends_on": [],
            "description": f"System.json {field} 업데이트",
            "_op_action": "update",
        }
    ]


# ──────────────────────────────────────────────
# Requirement → resolved result
# ──────────────────────────────────────────────


def _resolve_placeholder(
    placeholder: str | None,
    operation: dict,
    resolved_values: dict[str, Any],
) -> str:
    """placeholder 문자열을 operation 값이나 이전 resolve 결과로 채운다."""
    if not placeholder:
        return ""
    out = placeholder
    # operation 에서 채움
    subject = operation.get("subject") or {}
    value = operation.get("value") or {}
    out = out.replace("{subject_name}", str(subject.get("name") or ""))
    out = out.replace("{value_name}", str(value.get("ref") or ""))
    # slot_type / weapon_type: type_hint 우선, 없으면 kind fallback
    type_hint = str(value.get("type_hint") or value.get("kind") or "")
    out = out.replace("{slot_type}", type_hint)
    out = out.replace("{weapon_type}", type_hint)
    # 이전 결과에서 채움
    for k, v in resolved_values.items():
        out = out.replace(f"{{{k}}}", str(v))
    return out


def _check_requirement(
    req: Requirement,
    data_path: Path,
    search_name: str,
    resolved_values: dict[str, Any],
) -> dict[str, Any]:
    """하나의 Requirement 를 실제 파일에서 확인.

    Returns:
        {
            "exists": bool,
            "resolved_id": int | None,
            "action_needed": "create_entity" | "create_type" | None,
            "file": str,
        }
    """
    result: dict[str, Any] = {
        "exists": False,
        "resolved_id": None,
        "action_needed": None,
        "file": req.file,
        "search_name": search_name,
    }

    if req.lookup == "by_name":
        data = _load_json(data_path, req.file)
        if data is None or not isinstance(data, list):
            result["action_needed"] = req.if_missing if req.if_missing != "error" else None
            return result
        entry = _find_entity_by_name(data, search_name)
        if entry:
            result["exists"] = True
            result["resolved_id"] = entry.get("id")
        else:
            if req.if_missing == "error":
                result["action_needed"] = None  # 에러: 없으면 전체 plan 실패
                result["error"] = f"'{search_name}' 을(를) {req.file} 에서 찾을 수 없습니다"
            else:
                result["action_needed"] = req.if_missing
                result["resolved_id"] = _next_entity_id(data)

    elif req.lookup == "system_type_list":
        system_data = _load_json(data_path, "System.json")
        if not isinstance(system_data, dict):
            result["action_needed"] = req.if_missing if req.if_missing != "error" else None
            return result
        idx = _find_in_system_type_list(system_data, req.system_key or "", search_name)
        if idx is not None:
            result["exists"] = True
            result["resolved_id"] = idx
        else:
            if req.if_missing == "create_type":
                result["action_needed"] = "create_type"
                result["resolved_id"] = _next_system_type_index(system_data, req.system_key or "")
            elif req.if_missing == "error":
                result["error"] = (
                    f"'{search_name}' 을(를) System.json['{req.system_key}'] 에서 찾을 수 없습니다"
                )

    elif req.lookup == "by_id":
        data = _load_json(data_path, req.file)
        entity_id = resolved_values.get(req.resolve_key or "")
        if isinstance(data, list) and isinstance(entity_id, int):
            entry = data[entity_id] if 0 <= entity_id < len(data) else None
            if isinstance(entry, dict):
                result["exists"] = True
                result["resolved_id"] = entity_id

    elif req.lookup == "map_info":
        infos = _load_json(data_path, "MapInfos.json")
        if isinstance(infos, list):
            result["exists"] = False
            result["action_needed"] = req.if_missing
            # 다음 map id 계산
            max_id = max(
                (e.get("id", 0) for e in infos if isinstance(e, dict)),
                default=0,
            )
            result["resolved_id"] = max_id + 1

    return result


# ──────────────────────────────────────────────
# 공개 API — operation_tuples → execution_plan
# ──────────────────────────────────────────────


def build_execution_plan(
    operation_tuples: list[dict],
    data_path: Path,
) -> tuple[list[dict], dict, list[dict]]:
    """operation_tuples 를 execution_plan (executor_yb 포맷) 으로 변환.

    Returns:
        (execution_plan, plan_meta, deduped_operations)
    """
    deduped = _dedup_operations(operation_tuples)

    steps: list[dict] = []
    plan_meta: dict[int, list[int]] = {}
    step_counter = 0

    for op_idx, op in enumerate(deduped):
        op_steps = _plan_one_operation(op, data_path, step_counter)
        op_step_ids = [s["step_id"] for s in op_steps]
        plan_meta[op_idx] = op_step_ids
        steps.extend(op_steps)
        step_counter += len(op_steps)

    return steps, plan_meta, deduped


def _dedup_operations(ops: list[dict]) -> list[dict]:
    """같은 (file, subject.name, op) 조합의 중복 operation 을 병합한다."""
    seen_creates: dict[tuple[str, str], int] = {}  # (file, name) → index in result
    result: list[dict] = []

    for op in ops:
        action = op.get("op", "")
        target_file = op.get("file", "")
        subject = op.get("subject") or {}
        name = subject.get("name") or ""

        if action == "create" and name:
            key = (target_file, name.strip().lower())
            if key in seen_creates:
                # 이미 같은 create 가 있음 — skip
                logger.info("[planner] 중복 create skip: %s '%s'", target_file, name)
                continue
            seen_creates[key] = len(result)

        result.append(op)

    if len(result) < len(ops):
        logger.info("[planner] operation 중복 제거: %d → %d", len(ops), len(result))
    return result


def _plan_one_operation(op: dict, data_path: Path, step_offset: int) -> list[dict]:
    """단일 operation → step list."""
    target_file = op.get("file", "")
    field = op.get("field")
    value = op.get("value") or {}
    value_kind = value.get("kind")
    action = op.get("op", "read")
    subject = op.get("subject") or {}

    # System.json — 엔티티가 아닌 설정 파일, 전용 분기
    if target_file == "System.json":
        return _plan_system_operation(action, field, value, step_offset)

    # subject.index → 실제 이름으로 조기 해소
    if not subject.get("name") and subject.get("index") is not None:
        data = _load_json(data_path, target_file)
        if isinstance(data, list):
            entry = _find_entity_by_index(data, int(subject["index"]))
            if entry and entry.get("name"):
                subject = dict(subject)
                subject["name"] = entry["name"]
                op = dict(op)
                op["subject"] = subject

    # NOTE: subject→file 재라우팅은 resolver 노드가 담당. planner 는 file 을 신뢰한다.

    # read 요청은 단일 step
    if action == "read":
        return [
            {
                "step_id": step_offset,
                "action_type": "get" if subject.get("name") else "list",
                "target_file": target_file,
                "target_info": {
                    "name": subject.get("name"),
                    "field": field,
                },
                "depends_on": [],
                "description": f"{target_file} 에서 {subject.get('name', '전체')} 조회",
                "_op_action": "read",
            }
        ]

    # delete
    if action == "delete":
        return _plan_delete(op, data_path, step_offset)

    # create / update — 의존성 그래프 워크
    requirements = lookup_requirements(target_file, field, value_kind)

    if not requirements:
        # 의존성 없는 간단 작업
        return _plan_simple_mutation(op, data_path, step_offset)

    # 의존성 있는 작업 — requirement 순서대로 check + step 생성
    steps: list[dict] = []
    resolved_values: dict[str, Any] = {}
    sid = step_offset

    for req in requirements:
        search_name = _resolve_placeholder(req.placeholder, op, resolved_values)
        check = _check_requirement(req, data_path, search_name, resolved_values)

        if check.get("error"):
            # 필수 엔티티를 못 찾음 → 에러 step 하나만 반환
            steps.append(
                {
                    "step_id": sid,
                    "action_type": "error",
                    "target_file": req.file,
                    "target_info": {"error": check["error"]},
                    "depends_on": [],
                    "description": check["error"],
                    "_op_action": action,
                }
            )
            return steps

        if check["action_needed"] == "create_type":
            # System type 배열에 추가
            steps.append(
                {
                    "step_id": sid,
                    "action_type": "append_system_type",
                    "target_file": "System.json",
                    "target_info": {
                        "system_key": req.system_key,
                        "value": search_name,
                    },
                    "depends_on": [s["step_id"] for s in steps] if steps else [],
                    "description": f"System.json['{req.system_key}'] 에 '{search_name}' 추가",
                    "_op_action": "create",
                }
            )
            resolved_values[req.resolve_key or "new_type_id"] = check["resolved_id"]
            sid += 1

        elif check["action_needed"] == "create_entity":
            # 엔티티 생성 step — target_info 는 profiler 가 채울 빈 칸이 있을 수 있음
            creation_info: dict[str, Any] = {"name": search_name}
            # 이전 step 결과 바인딩
            for key, binding in (req.creation_bindings or {}).items():
                if binding.startswith("prev:"):
                    ref_key = binding[5:]
                    creation_info[key] = resolved_values.get(ref_key)
                else:
                    creation_info[key] = binding
            steps.append(
                {
                    "step_id": sid,
                    "action_type": "create",
                    "target_file": req.file,
                    "target_info": creation_info,
                    "depends_on": [s["step_id"] for s in steps] if steps else [],
                    "description": f"{req.file} 에 '{search_name}' 생성",
                    "_op_action": "create",
                    "_needs_profiling": True,
                }
            )
            resolved_values[req.resolve_key or "entity_id"] = check["resolved_id"]
            sid += 1

        else:
            # 이미 존재 — create step 불필요, resolve 만 기록
            if req.resolve_key and check["resolved_id"] is not None:
                resolved_values[req.resolve_key] = check["resolved_id"]

    # 최종 mutation step (원래 요청 — update, equip 등)
    final_step = _build_final_mutation_step(op, sid, steps, resolved_values, data_path)
    if final_step:
        steps.append(final_step)

    return steps


def _plan_simple_mutation(op: dict, data_path: Path, step_offset: int) -> list[dict]:
    """의존성 없는 단순 create/update."""
    target_file = op.get("file", "")
    action = op.get("op", "update")
    subject = op.get("subject") or {}
    value = op.get("value") or {}
    field = op.get("field")
    scope = subject.get("scope", "single")

    # bulk update (scope=all)
    if action == "update" and scope == "all":
        return _plan_bulk_update(target_file, field, value, step_offset)

    # subject 의 id 해소 — 이름 검색 → 인덱스 fallback
    entity_id = None
    resolved_name = subject.get("name")
    if action in ("update", "delete"):
        data = _load_json(data_path, target_file)
        if isinstance(data, list):
            entry = None
            # 1. 이름으로 검색
            if resolved_name:
                entry = _find_entity_by_name(data, resolved_name)
            # 2. 이름이 없거나 못 찾으면 index 로 검색
            if entry is None and subject.get("index") is not None:
                entry = _find_entity_by_index(data, int(subject["index"]))
            if entry:
                entity_id = entry.get("id")
                # index 로 찾은 경우 실제 이름으로 갱신
                if not resolved_name and entry.get("name"):
                    resolved_name = entry["name"]

    # create 시 subject.name 이 없으면 value 에서 이름 추출
    if action == "create" and not resolved_name:
        candidate = value.get("new_value") or value.get("ref")
        if isinstance(candidate, str) and candidate:
            resolved_name = candidate

    target_info: dict[str, Any] = {}
    if resolved_name:
        target_info["name"] = resolved_name
    if entity_id is not None:
        target_info["id"] = entity_id

    if action == "create":
        # value 의 메타 필드는 제외하고, 엔티티 데이터에 해당하는 것만 복사
        _VALUE_META_KEYS = {"kind", "ref", "new_value", "type_hint", "array_op", "match_hint"}
        target_info.update(
            {k: v for k, v in value.items() if v is not None and k not in _VALUE_META_KEYS}
        )
        return [
            {
                "step_id": step_offset,
                "action_type": "create",
                "target_file": target_file,
                "target_info": target_info,
                "depends_on": [],
                "description": f"{target_file} 에 '{subject.get('name', '?')}' 생성",
                "_op_action": "create",
                "_needs_profiling": True,
            }
        ]

    # update
    updates = _build_updates_dict(
        target_file, field, value, resolved_values={}, data_path=data_path
    )
    target_info["updates"] = updates

    return [
        {
            "step_id": step_offset,
            "action_type": "update",
            "target_file": target_file,
            "target_info": target_info,
            "depends_on": [],
            "description": f"{target_file} '{subject.get('name', '?')}' 업데이트",
            "_op_action": "update",
        }
    ]


def _plan_bulk_update(
    target_file: str,
    field: str | None,
    value: dict,
    step_offset: int,
) -> list[dict]:
    """scope=all 일 때 bulk update plan."""
    updates: dict[str, Any] = {}
    if field:
        new_value = value.get("new_value")
        if new_value is not None:
            if isinstance(new_value, float) and new_value == int(new_value):
                updates[field] = int(new_value)
            else:
                updates[field] = new_value
        elif value.get("ref"):
            updates[field] = value["ref"]
    return [
        {
            "step_id": step_offset,
            "action_type": "update_all",
            "target_file": target_file,
            "target_info": {"updates": updates},
            "depends_on": [],
            "description": f"{target_file} 전체 — {field}={updates.get(field, '?')}",
            "_op_action": "update",
        }
    ]


def _plan_delete(op: dict, data_path: Path, step_offset: int) -> list[dict]:
    """delete 요청."""
    target_file = op.get("file", "")
    subject = op.get("subject") or {}
    entity_id = None
    resolved_name = subject.get("name")
    data = _load_json(data_path, target_file)
    if isinstance(data, list):
        entry = None
        if resolved_name:
            entry = _find_entity_by_name(data, resolved_name)
        if entry is None and subject.get("index") is not None:
            entry = _find_entity_by_index(data, int(subject["index"]))
        if entry:
            entity_id = entry.get("id")
            if not resolved_name and entry.get("name"):
                resolved_name = entry["name"]
    return [
        {
            "step_id": step_offset,
            "action_type": "delete",
            "target_file": target_file,
            "target_info": {
                "name": resolved_name,
                "id": entity_id,
            },
            "depends_on": [],
            "description": f"{target_file} 에서 '{resolved_name or '?'}' 삭제",
            "_op_action": "delete",
        }
    ]


# ARRAY_FIELDS 는 agent.constants 에서 import 됨


def _build_updates_dict(
    target_file: str,
    field: str | None,
    value: dict,
    resolved_values: dict[str, Any],
    data_path: Path | None = None,
) -> dict[str, Any]:
    """field 에 따라 적절한 updates dict 를 생성한다.

    배열 조작이 필요한 필드는 커스텀 키(_equip, _array_op 등)를 생성.
    """
    # raw_updates — definition 에서 updates dict 통째로 넘어온 경우
    if value.get("raw_updates") and isinstance(value["raw_updates"], dict):
        return dict(value["raw_updates"])

    # 범용 배열 요소 조작 — array_op 이 설정되어 있으면 우선 처리
    if value.get("array_op") and field in ARRAY_FIELDS and data_path is not None:
        op = resolve_array_op(target_file, field, value, data_path)
        if op is not None:
            return {"_array_op": op}
        # array_op 해석 실패 — generic fallback 으로 배열을 스칼라로 덮어쓰면 안 됨
        logger.warning("[planner] array_op 해석 실패: %s.%s — 빈 updates 반환", target_file, field)
        return {}

    if field == "equips":
        item_id = resolved_values.get("armor_id") or resolved_values.get("weapon_id")
        etype_id = resolved_values.get("etypeId")
        return {
            "_equip": {
                "item_id": item_id,
                "etype_id": etype_id,
                "kind": value.get("kind"),
            }
        }
    if field == "learnings":
        skill_id = resolved_values.get("skill_id")
        # new_value 가 정수면 습득 레벨로 사용
        level = value.get("new_value") if isinstance(value.get("new_value"), (int, float)) else 1
        return {
            "_add_learning": {
                "skill_id": skill_id,
                "level": int(level),
            }
        }
    if field == "classId":
        class_id = resolved_values.get("class_id")
        return {"classId": class_id}
    if field == "actions":
        skill_id = resolved_values.get("skill_id")
        return {"_add_action": {"skill_id": skill_id}}
    if field == "dropItems":
        item_id = resolved_values.get("item_id")
        return {"_add_drop_item": {"item_id": item_id}}
    # 능력치 슬롯 — field="params[N]" 은 params 배열의 인덱스 N 만 갱신
    if field and field.startswith("params[") and field.endswith("]"):
        try:
            idx = int(field[len("params[") : -1])
        except ValueError:
            idx = -1
        if 0 <= idx < 8:
            new_value = value.get("new_value") if value else None
            if isinstance(new_value, float) and new_value == int(new_value):
                new_value = int(new_value)
            if new_value is not None:
                return {"_param_slot": {"index": idx, "value": new_value}}
        return {}
    # generic — new_value 에 설정할 값이 명확히 들어 있음
    if field and value:
        new_value = value.get("new_value")
        if new_value is not None:
            # float 정수면 int 로 변환
            if isinstance(new_value, float) and new_value == int(new_value):
                return {field: int(new_value)}
            return {field: new_value}
        # new_value 없으면 ref (엔티티명을 값으로 쓰는 경우)
        ref = value.get("ref")
        if ref:
            return {field: ref}
        return {}
    return {}


def _build_final_mutation_step(
    op: dict,
    step_id: int,
    preceding_steps: list[dict],
    resolved_values: dict[str, Any],
    data_path: Path,
) -> dict | None:
    """의존성 step 뒤에 오는 최종 mutation step 생성.

    예: equip armor 의 경우 최종 step 이 Actors.json update (equips 배열 수정).
    """
    action = op.get("op", "update")
    field = op.get("field")
    target_file = op.get("file", "")
    subject = op.get("subject") or {}
    value = op.get("value") or {}

    # create 이고 preceding steps 의 마지막이 이미 대상 파일 create 면 중복
    if action == "create":
        last = preceding_steps[-1] if preceding_steps else None
        if last and last.get("target_file") == target_file and last.get("action_type") == "create":
            return None  # profiler 가 이미 이 step 을 처리

    target_info: dict[str, Any] = {}

    # subject entity_id 해소 — resolved_values 에서 먼저 찾고, 없으면 파일에서 검색
    entity_id = None
    for key in (
        "actor_id",
        "skill_id",
        "enemy_id",
        "class_id",
        "item_id",
        "weapon_id",
        "armor_id",
        "state_id",
    ):
        val = resolved_values.get(key)
        if val is not None and key.replace("_id", "").capitalize() + "s.json" == target_file:
            entity_id = val
            break
        # Actors → actor_id 같은 매핑이 안 맞을 수 있으므로 범용 검색도
    if entity_id is None:
        # resolved_values 에 없으면 파일에서 직접 검색
        name = subject.get("name")
        if name:
            data = _load_json(data_path, target_file)
            if isinstance(data, list):
                entry = _find_entity_by_name(data, name)
                if entry:
                    entity_id = entry.get("id")

    if entity_id is not None:
        target_info["id"] = entity_id
    if subject.get("name"):
        target_info["name"] = subject["name"]

    updates = _build_updates_dict(target_file, field, value, resolved_values, data_path=data_path)
    target_info["updates"] = updates

    return {
        "step_id": step_id,
        "action_type": "update",
        "target_file": target_file,
        "target_info": target_info,
        "depends_on": [s["step_id"] for s in preceding_steps],
        "description": f"{target_file} '{subject.get('name', '?')}' — {field} 업데이트",
        "_op_action": "update",
    }
