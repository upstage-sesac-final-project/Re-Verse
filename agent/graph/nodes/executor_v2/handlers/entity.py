"""Entity handler — DB 배열 파일 8종 + System.json CRUD.

executor_yb 의 _dispatch_crud 를 이식한 것. RPGMakerCRUD 단일 진입점 사용.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.tools.rpgmaker_crud import RPGMakerCRUD

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 지원 파일 집합
# ──────────────────────────────────────────────

from agent.constants import ALL_SUPPORTED_FILES as ALL_SUPPORTED
from agent.constants import ENTITY_FILES

# action 정규화
_ACTION_ALIASES: dict[str, str] = {
    "query_by_id": "get",
    "query": "get",
    "search": "search",
    "list": "search",
    "get": "get",
    "get_system": "get_system",
    "create": "create",
    "create_damage": "create_damage",
    "create_healing": "create_healing",
    "create_buff": "create_buff",
    "create_state": "create_state",
    "update": "update",
    "update_actor": "update",
    "update_actor_bulk": "update_all",
    "delete": "delete",
    "update_game_title": "update_game_title",
    "set_variable_name": "set_variable_name",
    "set_switch_name": "set_switch_name",
    "update_starting_position": "update_starting_position",
    "update_system_field": "update_system_field",
    "append_system_type": "append_system_type",
}


def _resolve_entity_id(target_info: dict) -> int | None:
    for key in ("id", "entity_id", "actor_id", "skill_id", "item_id",
                "class_id", "enemy_id", "state_id", "weapon_id", "armor_id"):
        val = target_info.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _resolve_name(target_info: dict) -> str:
    return str(
        target_info.get("name")
        or target_info.get("actor_name")
        or target_info.get("skill_name")
        or target_info.get("item_name")
        or target_info.get("enemy_name")
        or ""
    ).strip()


def _resolve_search_term(target_info: dict) -> str:
    return str(
        target_info.get("searchTerm")
        or target_info.get("search_term")
        or target_info.get("query")
        or target_info.get("name")
        or ""
    ).strip()


def execute_entity_step(
    data_path: Path,
    action_raw: str,
    target_file: str,
    target_info: dict[str, Any],
) -> dict[str, Any]:
    """단일 entity step 실행. 동기 함수.

    Returns RPGMakerCRUD 호환 result dict.
    """
    action = _ACTION_ALIASES.get(action_raw.strip().lower(), action_raw.strip().lower())
    crud = RPGMakerCRUD(data_path)

    entity_id = _resolve_entity_id(target_info)
    name = _resolve_name(target_info)
    search_term = _resolve_search_term(target_info)
    updates = target_info.get("updates") if isinstance(target_info.get("updates"), dict) else {}

    # ── 조회 ──
    if action in ("get",) and target_file != "System.json":
        if entity_id is not None:
            return crud.get(target_file, entity_id=entity_id)
        return crud.get(target_file, name=name or search_term or None)

    if action in ("search",):
        return crud.search(target_file, search_term)

    # ── create 계열 ──
    if action in ("create", "create_damage", "create_healing", "create_buff", "create_state"):
        _sanitize_int_fields(target_info)
        return crud.create(target_file, target_info, action=action)

    # ── update ──
    if action == "update":
        if entity_id is None:
            return _fail(f"{target_file} update: entity_id 없음")
        # 커스텀 키 처리 — 배열 조작 연산
        resolved = _resolve_custom_updates(crud, target_file, entity_id, updates)
        return crud.update(target_file, entity_id, resolved)

    if action == "update_all":
        return crud.update_all(target_file, updates)

    # ── delete ──
    if action == "delete":
        if entity_id is None:
            return _fail(f"{target_file} delete: entity_id 없음")
        return crud.delete(target_file, entity_id)

    # ── System.json 전용 ──
    if target_file == "System.json":
        if action == "get_system":
            return crud.get_system()

        if action == "update_game_title":
            title = target_info.get("title") or target_info.get("game_title")
            if not title:
                return _fail("update_game_title: title 필드 없음")
            return crud.update_system_field("gameTitle", str(title))

        if action == "set_variable_name":
            vid = target_info.get("variableId") or target_info.get("variable_id")
            vname = target_info.get("name")
            if vid is None or vname is None:
                return _fail("set_variable_name: variableId/name 필요")
            return crud.update_system_field(f"variables.{int(vid)}", str(vname))

        if action == "set_switch_name":
            swid = target_info.get("switchId") or target_info.get("switch_id")
            swname = target_info.get("name")
            if swid is None or swname is None:
                return _fail("set_switch_name: switchId/name 필요")
            return crud.update_system_field(f"switches.{int(swid)}", str(swname))

        if action == "update_starting_position":
            return crud.update_starting_position(
                map_id=target_info.get("mapId") or target_info.get("map_id"),
                x=target_info.get("x"),
                y=target_info.get("y"),
            )

        if action == "update_system_field":
            key_path = target_info.get("key_path", "")
            value = target_info.get("value")
            if not key_path:
                return _fail("update_system_field: key_path 필요")
            return crud.update_system_field(key_path, value)

        if action == "append_system_type":
            system_key = target_info.get("system_key", "")
            value = target_info.get("value", "")
            return _append_system_type(crud, data_path, system_key, value)

    return _fail(f"지원하지 않는 action: {target_file}.{action}")


def _append_system_type(
    crud: RPGMakerCRUD, data_path: Path, system_key: str, value: str,
) -> dict[str, Any]:
    """System.json 의 타입 배열에 항목 추가 (armorTypes, weaponTypes 등)."""
    import json
    fp = data_path / "System.json"
    data = json.loads(fp.read_text(encoding="utf-8"))
    arr = data.get(system_key)
    if not isinstance(arr, list):
        return _fail(f"System.json['{system_key}'] 가 배열이 아닙니다")
    new_idx = len(arr)
    arr.append(value)
    fp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    logger.info("[entity] append_system_type %s[%d] = '%s'", system_key, new_idx, value)
    return {
        "success": True,
        "data": {"system_key": system_key, "index": new_idx, "value": value},
        "modified_files": ["System.json"],
        "error": None,
        "entity_id": new_idx,
    }


def _resolve_custom_updates(
    crud: RPGMakerCRUD,
    target_file: str,
    entity_id: int,
    updates: dict,
) -> dict:
    """커스텀 키(_equip, _add_learning 등)를 실제 필드 변경으로 해석한다."""
    resolved = {}

    for key, val in updates.items():
        if key == "_add_learning" and isinstance(val, dict):
            # Actor 에게 스킬 직접 부여 → trait code 43
            skill_id = val.get("skill_id")
            if skill_id is not None:
                current = crud.get(target_file, entity_id=entity_id)
                existing_traits = []
                if current.get("success") and isinstance(current.get("data"), dict):
                    existing_traits = list(current["data"].get("traits") or [])
                new_trait = {"code": 43, "dataId": int(skill_id), "value": 0}
                # 중복 방지
                if not any(
                    t.get("code") == 43 and t.get("dataId") == int(skill_id)
                    for t in existing_traits if isinstance(t, dict)
                ):
                    existing_traits.append(new_trait)
                resolved["traits"] = existing_traits

        elif key == "_equip" and isinstance(val, dict):
            # equips 배열의 특정 슬롯에 장비 장착
            item_id = val.get("item_id")
            etype_id = val.get("etype_id")
            if item_id is not None:
                current = crud.get(target_file, entity_id=entity_id)
                equips = [0, 0, 0, 0, 0]
                if current.get("success") and isinstance(current.get("data"), dict):
                    equips = list(current["data"].get("equips") or [0, 0, 0, 0, 0])
                # etype_id 로 슬롯 결정: 1=무기, 2=방패, 3=머리, 4=몸통, 5=장신구
                slot = 0
                if isinstance(etype_id, int) and 1 <= etype_id <= len(equips):
                    slot = etype_id - 1
                equips[slot] = int(item_id)
                resolved["equips"] = equips

        elif key == "_add_action" and isinstance(val, dict):
            # Enemy 에 행동 패턴 추가
            skill_id = val.get("skill_id")
            if skill_id is not None:
                current = crud.get(target_file, entity_id=entity_id)
                actions = []
                if current.get("success") and isinstance(current.get("data"), dict):
                    actions = list(current["data"].get("actions") or [])
                new_action = {
                    "conditionParam1": 0,
                    "conditionParam2": 0,
                    "conditionType": 0,
                    "rating": 5,
                    "skillId": int(skill_id),
                }
                actions.append(new_action)
                resolved["actions"] = actions

        elif key == "_add_drop_item" and isinstance(val, dict):
            # Enemy 에 드롭 아이템 추가
            item_id = val.get("item_id")
            if item_id is not None:
                current = crud.get(target_file, entity_id=entity_id)
                drops = []
                if current.get("success") and isinstance(current.get("data"), dict):
                    drops = list(current["data"].get("dropItems") or [])
                # 비어있는 슬롯(kind=0) 찾아서 교체
                replaced = False
                for d in drops:
                    if isinstance(d, dict) and d.get("kind", 0) == 0:
                        d["kind"] = 1  # 아이템
                        d["dataId"] = int(item_id)
                        d["denominator"] = 3
                        replaced = True
                        break
                if not replaced:
                    drops.append({"kind": 1, "dataId": int(item_id), "denominator": 3})
                resolved["dropItems"] = drops

        elif key == "_array_op" and isinstance(val, dict):
            # 범용 배열 요소 조작
            _apply_array_op(crud, target_file, entity_id, val, resolved)

        elif not key.startswith("_"):
            # 일반 필드는 그대로 통과
            resolved[key] = val

    return resolved


def _array_elem_matches(elem: dict, condition: dict) -> bool:
    """배열 요소가 조건과 일치하는지 확인."""
    return all(elem.get(k) == v for k, v in condition.items())


def _apply_array_op(
    crud: RPGMakerCRUD,
    target_file: str,
    entity_id: int,
    op_spec: dict,
    resolved: dict,
) -> None:
    """범용 배열 요소 조작 실행."""
    array_field = op_spec.get("array_field", "")
    op_type = op_spec.get("op", "update")
    match_cond = op_spec.get("match", {})
    set_fields = op_spec.get("set", {})

    # 현재 배열 가져오기
    current = crud.get(target_file, entity_id=entity_id)
    arr: list = []
    if current.get("success") and isinstance(current.get("data"), dict):
        arr = list(current["data"].get(array_field) or [])

    if op_type == "update":
        found = False
        for elem in arr:
            if isinstance(elem, dict) and _array_elem_matches(elem, match_cond):
                elem.update(set_fields)
                found = True
                break
        if not found:
            # upsert — 매칭 요소가 없으면 match 조건 + set 필드를 합쳐서 추가
            new_elem = dict(match_cond)
            new_elem.update(set_fields)
            arr.append(new_elem)
            logger.info(
                "[entity] _array_op upsert: match %s not found, added to %s.%s",
                match_cond, target_file, array_field,
            )

    elif op_type == "add":
        arr.append(dict(set_fields))

    elif op_type == "remove":
        arr = [
            e for e in arr
            if not (isinstance(e, dict) and _array_elem_matches(e, match_cond))
        ]

    resolved[array_field] = arr


def _sanitize_int_fields(info: dict) -> None:
    """create 직전 — float→int 강제 변환. LLM 이 만든 데이터 보정."""
    def _deep_int(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _deep_int(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_deep_int(v) for v in obj]
        if isinstance(obj, float) and obj == int(obj):
            return int(obj)
        return obj

    # actions, dropItems, learnings — 내부 모든 float→int (정수인 경우만)
    for key in ("actions", "dropItems", "learnings", "equips", "params", "expParams"):
        if key in info:
            info[key] = _deep_int(info[key])

    # top-level 정수 필드
    int_keys = {"exp", "gold", "price", "stypeId", "mpCost", "tpCost", "scope",
                "occasion", "hitType", "successRate", "repeats", "tpGain",
                "animationId", "itypeId", "wtypeId", "etypeId", "atypeId",
                "classId", "initialLevel", "maxLevel", "iconIndex",
                "restriction", "priority"}
    for k in int_keys:
        if k in info and isinstance(info[k], float) and info[k] == int(info[k]):
            info[k] = int(info[k])


def _fail(error: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "modified_files": [],
        "error": error,
        "entity_id": None,
    }
