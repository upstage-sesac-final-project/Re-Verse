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

from new_agent.nodes.planner.dependencies import (
    Requirement,
    lookup_requirements,
)

logger = logging.getLogger(__name__)

# SequenceMatcher 임계값 — 이름 검색 시 퍼지 매칭 최소 유사도
_FUZZY_THRESHOLD = 0.6


# ──────────────────────────────────────────────
# 파일 유틸
# ──────────────────────────────────────────────


def _load_json(data_path: Path, filename: str) -> Any:
    fp = data_path / filename
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def _find_entity_by_name(
    data: list, name: str, threshold: float = _FUZZY_THRESHOLD
) -> dict | None:
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


def _find_in_system_type_list(
    system_data: dict, key: str, name: str
) -> int | None:
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


def _next_entity_id(data: list) -> int:
    """DB 배열에서 다음 id (null 슬롯 우선)."""
    for i in range(1, len(data)):
        if data[i] is None:
            return i
    return len(data)


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
    out = out.replace("{subject_name}", str(subject.get("name", "")))
    out = out.replace("{value_name}", str(value.get("name", "")))
    # slot_type / weapon_type: hints 가 있으면 hints 우선 (한국어 타입명), 없으면 kind
    hints = str(value.get("hints") or "")
    out = out.replace("{slot_type}", hints or str(value.get("slot_type", value.get("kind", ""))))
    out = out.replace("{weapon_type}", hints or str(value.get("weapon_type", value.get("kind", ""))))
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
) -> tuple[list[dict], dict]:
    """operation_tuples 를 execution_plan (executor_yb 포맷) 으로 변환.

    Returns:
        (execution_plan, plan_meta)
        plan_meta: { op_index: [step_ids] } 역매핑
    """
    steps: list[dict] = []
    plan_meta: dict[int, list[int]] = {}
    step_counter = 0

    for op_idx, op in enumerate(operation_tuples):
        op_steps = _plan_one_operation(op, data_path, step_counter)
        op_step_ids = [s["step_id"] for s in op_steps]
        plan_meta[op_idx] = op_step_ids
        steps.extend(op_steps)
        step_counter += len(op_steps)

    return steps, plan_meta


def _plan_one_operation(
    op: dict, data_path: Path, step_offset: int
) -> list[dict]:
    """단일 operation → step list."""
    target_file = op.get("file", "")
    field = op.get("field")
    value = op.get("value") or {}
    value_kind = value.get("kind")
    action = op.get("op", "read")
    subject = op.get("subject") or {}

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
        search_name = _resolve_placeholder(
            req.placeholder, op, resolved_values
        )
        check = _check_requirement(req, data_path, search_name, resolved_values)

        if check.get("error"):
            # 필수 엔티티를 못 찾음 → 에러 step 하나만 반환
            steps.append({
                "step_id": sid,
                "action_type": "error",
                "target_file": req.file,
                "target_info": {"error": check["error"]},
                "depends_on": [],
                "description": check["error"],
                "_op_action": action,
            })
            return steps

        if check["action_needed"] == "create_type":
            # System type 배열에 추가
            steps.append({
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
            })
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
            steps.append({
                "step_id": sid,
                "action_type": "create",
                "target_file": req.file,
                "target_info": creation_info,
                "depends_on": [s["step_id"] for s in steps] if steps else [],
                "description": f"{req.file} 에 '{search_name}' 생성",
                "_op_action": "create",
                "_needs_profiling": True,
            })
            resolved_values[req.resolve_key or "entity_id"] = check["resolved_id"]
            sid += 1

        else:
            # 이미 존재 — create step 불필요, resolve 만 기록
            if req.resolve_key and check["resolved_id"] is not None:
                resolved_values[req.resolve_key] = check["resolved_id"]

    # 최종 mutation step (원래 요청 — update, equip 등)
    final_step = _build_final_mutation_step(
        op, sid, steps, resolved_values
    )
    if final_step:
        steps.append(final_step)

    return steps


def _plan_simple_mutation(
    op: dict, data_path: Path, step_offset: int
) -> list[dict]:
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

    # subject 의 id 해소
    entity_id = None
    if action in ("update", "delete") and subject.get("name"):
        data = _load_json(data_path, target_file)
        if isinstance(data, list):
            entry = _find_entity_by_name(data, subject["name"])
            if entry:
                entity_id = entry.get("id")

    target_info: dict[str, Any] = {}
    if subject.get("name"):
        target_info["name"] = subject["name"]
    if entity_id is not None:
        target_info["id"] = entity_id

    if action == "create":
        target_info.update({k: v for k, v in value.items() if v is not None})
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
    updates = _build_updates_dict(target_file, field, value, resolved_values={})
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
    amount = value.get("amount")
    updates: dict[str, Any] = {}
    if field and amount is not None:
        updates[field] = int(amount) if isinstance(amount, float) and amount == int(amount) else amount
    elif field and value:
        updates[field] = value.get("name") or value
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


def _plan_delete(
    op: dict, data_path: Path, step_offset: int
) -> list[dict]:
    """delete 요청."""
    target_file = op.get("file", "")
    subject = op.get("subject") or {}
    entity_id = None
    if subject.get("name"):
        data = _load_json(data_path, target_file)
        if isinstance(data, list):
            entry = _find_entity_by_name(data, subject["name"])
            if entry:
                entity_id = entry.get("id")
    return [
        {
            "step_id": step_offset,
            "action_type": "delete",
            "target_file": target_file,
            "target_info": {
                "name": subject.get("name"),
                "id": entity_id,
            },
            "depends_on": [],
            "description": f"{target_file} 에서 '{subject.get('name', '?')}' 삭제",
            "_op_action": "delete",
        }
    ]


def _build_updates_dict(
    target_file: str,
    field: str | None,
    value: dict,
    resolved_values: dict[str, Any],
) -> dict[str, Any]:
    """field 에 따라 적절한 updates dict 를 생성한다.

    배열 조작이 필요한 필드는 커스텀 키(_equip, _add_learning 등)를 생성.
    """
    if field == "equips":
        item_id = resolved_values.get("armor_id") or resolved_values.get("weapon_id")
        etype_id = resolved_values.get("etypeId")
        return {"_equip": {
            "item_id": item_id,
            "etype_id": etype_id,
            "kind": value.get("kind"),
        }}
    if field == "learnings":
        skill_id = resolved_values.get("skill_id")
        return {"_add_learning": {
            "skill_id": skill_id,
            "level": value.get("level", 1),
        }}
    if field == "classId":
        class_id = resolved_values.get("class_id")
        return {"classId": class_id}
    if field == "actions":
        skill_id = resolved_values.get("skill_id")
        return {"_add_action": {"skill_id": skill_id}}
    if field == "dropItems":
        item_id = resolved_values.get("item_id")
        return {"_add_drop_item": {"item_id": item_id}}
    # generic — amount 이 있으면 숫자값 우선, 없으면 name
    if field and value:
        amount = value.get("amount")
        if amount is not None:
            return {field: int(amount) if isinstance(amount, float) and amount == int(amount) else amount}
        name = value.get("name")
        if name:
            return {field: name}
        return {field: value}
    return {}


def _build_final_mutation_step(
    op: dict,
    step_id: int,
    preceding_steps: list[dict],
    resolved_values: dict[str, Any],
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

    # equips 같은 "참조 필드 update" 케이스
    target_info: dict[str, Any] = {}
    actor_id = resolved_values.get("actor_id")
    if actor_id is not None:
        target_info["id"] = actor_id
    if subject.get("name"):
        target_info["name"] = subject["name"]

    updates = _build_updates_dict(target_file, field, value, resolved_values)
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
