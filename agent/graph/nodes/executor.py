"""Executor 노드 — 4단계: 룰베이스 JSON 물리 수정."""

import asyncio
import functools
import json
import logging
import os
import shutil
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent.graph.nodes.executor_v2.dispatch import dispatch_step
from agent.graph.state import AgentState
from agent.mcp_toolbox import (
    build_stdio_server_parameters,
    call_mcp_tool,
    is_mcp_enabled,
    resolve_mcp_server_key,
)
from app.backend.core.game_paths import get_game_data_path
from app.backend.services.json_modify_tools.managers.actor_manager import ActorManager
from app.backend.services.json_modify_tools.managers.class_manager import ClassManager
from app.backend.services.json_modify_tools.managers.skill_manager import SkillManager
from app.backend.services.json_modify_tools.managers.system_manager import SystemManager

logger = logging.getLogger(__name__)

# 동일 game_id에 대한 구조화 스텝이 겹치지 않도록 (단일 프로세스 내)
game_locks: defaultdict[str, asyncio.Lock] = defaultdict(lambda: asyncio.Lock())

# ────────────────────────────────────────────────────────────
# MCP (k4zuki RPG Maker MZ Node 서버) — 구조화 스텝만 인터셉트
# (target_file, action_type) → list_tools() 이름과 동일. 맵 전용 툴(get_map*, *map_event*, add_event_command)은 제외.
#
# 통합 MCP (integration_MCP / @rein634/rpg-maker-mz-mcp) 기준 툴 매핑.
# 4개 리포를 하나로 합친 서버가 제공하는 tool 이름에 맞춤.
# ────────────────────────────────────────────────────────────
MCP_TOOL_MAP: dict[tuple[str, str], dict[str, Any]] = {
    # Actors.json
    ("Actors.json", "list"): {"tool": "list_actors", "backup_files": []},
    ("Actors.json", "search"): {"tool": "search_actors", "backup_files": []},
    ("Actors.json", "query_by_id"): {"tool": "get_actor", "backup_files": []},
    ("Actors.json", "create"): {"tool": "create_actor", "backup_files": ["Actors.json"]},
    ("Actors.json", "update_actor"): {"tool": "update_actor", "backup_files": ["Actors.json"]},
    # Skills.json
    ("Skills.json", "list"): {"tool": "list_skills", "backup_files": []},
    ("Skills.json", "query"): {"tool": "get_skill", "backup_files": []},
    ("Skills.json", "search"): {"tool": "search_skills", "backup_files": []},
    ("Skills.json", "create"): {"tool": "create_skill", "backup_files": ["Skills.json"]},
    ("Skills.json", "create_damage"): {
        "tool": "create_damage_skill",
        "backup_files": ["Skills.json"],
    },
    ("Skills.json", "create_healing"): {
        "tool": "create_healing_skill",
        "backup_files": ["Skills.json"],
    },
    ("Skills.json", "create_buff"): {"tool": "create_buff_skill", "backup_files": ["Skills.json"]},
    ("Skills.json", "create_state"): {
        "tool": "create_state_skill",
        "backup_files": ["Skills.json"],
    },
    ("Skills.json", "update"): {"tool": "update_skill", "backup_files": ["Skills.json"]},
    # Items.json
    ("Items.json", "list"): {"tool": "list_items", "backup_files": []},
    ("Items.json", "search"): {"tool": "search_items", "backup_files": []},
    ("Items.json", "create"): {"tool": "create_item", "backup_files": ["Items.json"]},
    ("Items.json", "update"): {"tool": "update_item", "backup_files": ["Items.json"]},
    # Weapons.json
    ("Weapons.json", "list"): {"tool": "list_weapons", "backup_files": []},
    ("Weapons.json", "create"): {"tool": "create_weapon", "backup_files": ["Weapons.json"]},
    ("Weapons.json", "update"): {"tool": "update_weapon", "backup_files": ["Weapons.json"]},
    # Armors.json
    ("Armors.json", "list"): {"tool": "list_armors", "backup_files": []},
    ("Armors.json", "create"): {"tool": "create_armor", "backup_files": ["Armors.json"]},
    ("Armors.json", "update"): {"tool": "update_armor", "backup_files": ["Armors.json"]},
    # Classes.json (통합 MCP에서 추가)
    ("Classes.json", "list"): {"tool": "list_classes", "backup_files": []},
    ("Classes.json", "create"): {"tool": "create_class", "backup_files": ["Classes.json"]},
    ("Classes.json", "update"): {"tool": "update_class", "backup_files": ["Classes.json"]},
    # States.json (통합 MCP에서 추가)
    ("States.json", "list"): {"tool": "list_states", "backup_files": []},
    ("States.json", "create"): {"tool": "create_state", "backup_files": ["States.json"]},
    ("States.json", "update"): {"tool": "update_state", "backup_files": ["States.json"]},
    # Enemies.json (통합 MCP에서 추가)
    ("Enemies.json", "list"): {"tool": "list_enemies", "backup_files": []},
    ("Enemies.json", "create"): {"tool": "create_enemy", "backup_files": ["Enemies.json"]},
    ("Enemies.json", "update"): {"tool": "update_enemy", "backup_files": ["Enemies.json"]},
    # System.json
    ("System.json", "query"): {"tool": "get_system", "backup_files": []},
    ("System.json", "list_variables"): {"tool": "get_variables", "backup_files": []},
    ("System.json", "set_variable_name"): {
        "tool": "set_variable_name",
        "backup_files": ["System.json"],
    },
    ("System.json", "list_switches"): {"tool": "get_switches", "backup_files": []},
    ("System.json", "set_switch_name"): {
        "tool": "set_switch_name",
        "backup_files": ["System.json"],
    },
    ("System.json", "get_game_title"): {"tool": "get_game_title", "backup_files": []},
    ("System.json", "update_game_title"): {
        "tool": "update_game_title",
        "backup_files": ["System.json"],
    },
    ("System.json", "update_starting_position"): {
        "tool": "update_starting_position",
        "backup_files": ["System.json"],
    },
}


def _coerce_list_from_mcp_search_payload(data: Any) -> list[Any]:
    """MCP 검색 응답 JSON 형태가 제각각일 때 리스트 후보를 꺼낸다."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("items", "results", "matches", "data", "actors", "skills", "enemies"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    for key in ("item", "actor", "skill", "enemy", "result"):
        v = data.get(key)
        if isinstance(v, dict):
            return [v]
    return []


def _first_numeric_id_from_row(row: Any, keys: tuple[str, ...]) -> int | None:
    if not isinstance(row, dict):
        return None
    for k in keys:
        if k not in row or row[k] is None:
            continue
        try:
            return int(row[k])
        except (TypeError, ValueError):
            continue
    return None


def _row_name_matches_search_term(row: dict[str, Any], term: str) -> bool:
    """검색어가 있을 때 MCP 행이 실제로 그 대상인지(이름 기준) 완화 검증한다."""
    t = (term or "").strip().lower()
    if not t:
        return True
    nm = str(row.get("name") or row.get("displayName") or "").strip().lower()
    if not nm:
        return False
    return t in nm or nm == t


def _items_local_search_by_name(data_path: Path, term: str) -> tuple[bool, int | None]:
    """MCP가 hits를 안 주거나 exists를 안 넣어도 Items.json으로 존재 여부를 판별한다."""
    t = (term or "").strip().lower()
    if not t:
        return False, None
    fp = data_path / "Items.json"
    if not fp.is_file():
        return False, None
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(raw, list):
        return False, None
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip().lower()
        if not name:
            continue
        # 검색어가 이름의 부분 문자열일 때만 매칭 (name in term 은 'actor' in 'zzz_actor_…' 같은 오탐을 만든다)
        if t in name:
            rid = entry.get("id")
            try:
                return True, int(rid) if rid is not None else idx
            except (TypeError, ValueError):
                return True, idx
    return False, None


def _actors_local_search_by_name(data_path: Path, term: str) -> tuple[bool, int | None]:
    t = (term or "").strip().lower()
    if not t:
        return False, None
    fp = data_path / "Actors.json"
    if not fp.is_file():
        return False, None
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(raw, list):
        return False, None
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip().lower()
        if not name:
            continue
        if t in name:
            rid = entry.get("id")
            try:
                return True, int(rid) if rid is not None else idx
            except (TypeError, ValueError):
                return True, idx
    return False, None


def _skills_local_search_by_name(data_path: Path, term: str) -> tuple[bool, int | None]:
    t = (term or "").strip().lower()
    if not t:
        return False, None
    fp = data_path / "Skills.json"
    if not fp.is_file():
        return False, None
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(raw, list):
        return False, None
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip().lower()
        if not name:
            continue
        if t in name:
            rid = entry.get("id")
            try:
                return True, int(rid) if rid is not None else idx
            except (TypeError, ValueError):
                return True, idx
    return False, None


def _enemies_local_search_by_name(data_path: Path, term: str) -> tuple[bool, int | None]:
    t = (term or "").strip().lower()
    if not t:
        return False, None
    fp = data_path / "Enemies.json"
    if not fp.is_file():
        return False, None
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(raw, list):
        return False, None
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip().lower()
        if not name:
            continue
        if t in name:
            rid = entry.get("id")
            try:
                return True, int(rid) if rid is not None else idx
            except (TypeError, ValueError):
                return True, idx
    return False, None


def _enrich_mcp_search_tool_result(
    tool_name: str,
    r: dict[str, Any],
    *,
    data_path: Path,
    norm_args: dict[str, Any],
) -> dict[str, Any]:
    """조건부 create 스킵용으로 검색 MCP 결과에 exists·첫 id를 채운다.

    Node MCP는 JSON에 exists를 안 넣는 경우가 많아, 성공(success)만으로는
    '이미 있음 → create 생략'이 동작하지 않는다.
    """
    out = dict(r)
    data = r.get("data")
    st = str(
        norm_args.get("searchTerm") or norm_args.get("search_term") or norm_args.get("query") or ""
    ).strip()

    cfg = {
        "search_items": (("id", "itemId"), _items_local_search_by_name),
        "search_actors": (("id", "actorId"), _actors_local_search_by_name),
        "search_skills": (("id", "skillId"), _skills_local_search_by_name),
        "search_enemies": (("id", "enemyId"), _enemies_local_search_by_name),
    }
    if tool_name not in cfg:
        return out

    id_keys, local_fn = cfg[tool_name]
    rows = _coerce_list_from_mcp_search_payload(data)
    first_id: int | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not st:
            # 빈 검색어로는 MCP 행을 신뢰하지 않는다(목록 전체가 올 수 있음).
            continue
        if not _row_name_matches_search_term(row, st):
            continue
        rid = _first_numeric_id_from_row(row, id_keys)
        if rid is not None:
            first_id = rid
            break
    # 빈 객체 리스트만 오거나 exists 플래그만 true인 경우 오판하지 않도록, id 확보 또는 로컬 매칭이 있을 때만 존재로 본다.
    exists = first_id is not None

    if not exists and st:
        exists, first_id = local_fn(data_path, st)

    out["exists"] = exists
    if first_id is not None:
        if tool_name == "search_items":
            out["item_id"] = first_id
        elif tool_name == "search_actors":
            out["actor_id"] = first_id
        elif tool_name == "search_skills":
            out["skill_id"] = first_id
        elif tool_name == "search_enemies":
            out["enemy_id"] = first_id
    return out


def _enrich_items_target_info_from_deps(
    step: dict, step_results: dict[int, dict], target_info: dict[str, Any]
) -> dict[str, Any]:
    """선행 Items 검색 스텝에 item_id가 있으나 update 스텝에 빠진 경우 채운다."""
    ti = dict(target_info)
    if ti.get("item_id") is not None or ti.get("itemId") is not None:
        return ti
    for d in step.get("depends_on") or []:
        try:
            did = int(d)
        except (TypeError, ValueError):
            continue
        prev = step_results.get(did)
        if not isinstance(prev, dict):
            continue
        iid = prev.get("item_id")
        if iid is not None:
            ti["item_id"] = iid
            logger.debug(
                "[Executor] 선행 검색에서 item_id 보강 step=%s item_id=%s", step.get("step_id"), iid
            )
            break
    return ti


def _as_int(v: Any) -> Any:
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _normalize_mcp_arguments(
    target_file: str, action: str, target_info: dict[str, Any]
) -> dict[str, Any]:
    """플래너 dict를 복사한 뒤 MCP 툴 스키마에 맞게 키를 맞춘다 (원본 오염 방지)."""
    out = dict(target_info)

    def _search_term() -> str:
        return str(out.get("searchTerm") or out.get("search_term") or out.get("query") or "")

    # ── Actors.json ──
    if target_file == "Actors.json" and action == "create":
        if "name" not in out and "actor_name" in out:
            out["name"] = out.pop("actor_name")
        return out

    if target_file == "Actors.json" and action == "search":
        if not (out.get("searchTerm") or out.get("search_term") or out.get("query")):
            nm = out.get("actor_name") or out.get("name")
            if nm is not None:
                out["searchTerm"] = str(nm)
        return {"searchTerm": _search_term()}

    if target_file == "Actors.json" and action == "query_by_id":
        aid = out.get("actorId", out.get("actor_id"))
        if aid is None:
            return {}
        return {"actorId": _as_int(aid)}

    if target_file == "Actors.json" and action == "update_actor":
        aid = out.get("actorId", out.get("actor_id"))
        updates = out.get("updates")
        built: dict[str, Any] = {}
        if aid is not None:
            built["actorId"] = _as_int(aid)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # ── Skills.json ──
    if target_file == "Skills.json" and action == "create":
        if "name" not in out and "skill_name" in out:
            out["name"] = out.pop("skill_name")
        return out

    if target_file == "Skills.json" and action == "query":
        sid = out.get("skillId", out.get("skill_id"))
        if sid is None:
            return {}
        return {"skillId": _as_int(sid)}

    if target_file == "Skills.json" and action == "search":
        if not (out.get("searchTerm") or out.get("search_term") or out.get("query")):
            nm = out.get("skill_name") or out.get("name")
            if nm is not None:
                out["searchTerm"] = str(nm)
        return {"searchTerm": _search_term()}

    if target_file == "Skills.json" and action == "update":
        sid = out.get("skillId", out.get("skill_id"))
        updates = out.get("updates")
        built = {}
        if sid is not None:
            built["skillId"] = _as_int(sid)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # create_damage / healing / buff / state — MCP 스키마 필드명 그대로 전달(플래너가 snake_case 쓰면 보정)
    if target_file == "Skills.json" and action in (
        "create_damage",
        "create_healing",
        "create_buff",
        "create_state",
    ):
        if "name" not in out and "skill_name" in out:
            out["name"] = out.pop("skill_name")
        if action == "create_damage" and "damageFormula" not in out and "damage_formula" in out:
            out["damageFormula"] = out.pop("damage_formula")
        if action == "create_healing" and "healFormula" not in out and "heal_formula" in out:
            out["healFormula"] = out.pop("heal_formula")
        return out

    # ── Items.json ──
    if target_file == "Items.json" and action == "create":
        if "name" not in out and "item_name" in out:
            out["name"] = out.pop("item_name")
        return out

    if target_file == "Items.json" and action == "search":
        # query→search 정규화 후에도 플래너가 name/item_name 만 넘기는 경우가 있어 searchTerm 으로 맞춘다.
        if not (out.get("searchTerm") or out.get("search_term") or out.get("query")):
            nm = out.get("name") or out.get("item_name")
            if nm is not None:
                out["searchTerm"] = str(nm)
        return {"searchTerm": _search_term()}

    if target_file == "Items.json" and action == "update":
        iid = out.get("itemId", out.get("item_id"))
        # 플래너가 updates 없이 new_description·damage 등만 줄 때가 많아 MCP 스키마용 updates로 합친다.
        updates: dict[str, Any] = {}
        if isinstance(out.get("updates"), dict):
            updates = dict(out["updates"])
        nd = out.get("new_description")
        if nd is not None and "description" not in updates:
            updates["description"] = str(nd)
        desc = out.get("description")
        if desc is not None and "description" not in updates:
            updates["description"] = str(desc)
        new_name = out.get("new_name") or out.get("newName")
        if new_name is not None and "name" not in updates:
            updates["name"] = str(new_name)
        if isinstance(out.get("damage"), dict) and "damage" not in updates:
            updates["damage"] = dict(out["damage"])
        if isinstance(out.get("effects"), list) and "effects" not in updates:
            updates["effects"] = list(out["effects"])
        built: dict[str, Any] = {}
        if iid is not None:
            built["itemId"] = _as_int(iid)
        if updates:
            built["updates"] = updates
        return built

    # ── System.json ──
    if target_file == "System.json" and action == "set_variable_name":
        vid = out.get("variableId", out.get("variable_id"))
        name = out.get("name")
        b: dict[str, Any] = {}
        if vid is not None:
            b["variableId"] = _as_int(vid)
        if name is not None:
            b["name"] = str(name)
        return b

    if target_file == "System.json" and action == "set_switch_name":
        sid = out.get("switchId", out.get("switch_id"))
        name = out.get("name")
        b = {}
        if sid is not None:
            b["switchId"] = _as_int(sid)
        if name is not None:
            b["name"] = str(name)
        return b

    if target_file == "System.json" and action == "update_game_title":
        title = out.get("title") or out.get("game_title")
        return {"title": str(title)} if title is not None else {}

    if target_file == "System.json" and action == "update_starting_position":
        mid = out.get("mapId", out.get("map_id"))
        x = out.get("x")
        y = out.get("y")
        b = {}
        if mid is not None:
            b["mapId"] = _as_int(mid)
        if x is not None:
            b["x"] = _as_int(x)
        if y is not None:
            b["y"] = _as_int(y)
        return b

    # ── Weapons.json ──
    if target_file == "Weapons.json" and action == "create":
        if "name" not in out and "weapon_name" in out:
            out["name"] = out.pop("weapon_name")
        return out

    if target_file == "Weapons.json" and action == "update":
        wid = out.get("weaponId", out.get("weapon_id"))
        updates = out.get("updates")
        built = {}
        if wid is not None:
            built["weaponId"] = _as_int(wid)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # ── Armors.json ──
    if target_file == "Armors.json" and action == "create":
        if "name" not in out and "armor_name" in out:
            out["name"] = out.pop("armor_name")
        return out

    if target_file == "Armors.json" and action == "update":
        aid = out.get("armorId", out.get("armor_id"))
        updates = out.get("updates")
        built = {}
        if aid is not None:
            built["armorId"] = _as_int(aid)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # ── Classes.json ──
    if target_file == "Classes.json" and action == "create":
        if "name" not in out and "class_name" in out:
            out["name"] = out.pop("class_name")
        return out

    if target_file == "Classes.json" and action == "update":
        cid = out.get("classId", out.get("class_id"))
        updates = out.get("updates")
        built = {}
        if cid is not None:
            built["classId"] = _as_int(cid)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # ── States.json ──
    if target_file == "States.json" and action == "create":
        if "name" not in out and "state_name" in out:
            out["name"] = out.pop("state_name")
        return out

    if target_file == "States.json" and action == "update":
        sid_val = out.get("stateId", out.get("state_id"))
        updates = out.get("updates")
        built = {}
        if sid_val is not None:
            built["stateId"] = _as_int(sid_val)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # ── Enemies.json ──
    if target_file == "Enemies.json" and action == "create":
        if "name" not in out and "enemy_name" in out:
            out["name"] = out.pop("enemy_name")
        return out

    if target_file == "Enemies.json" and action == "update":
        eid = out.get("enemyId", out.get("enemy_id"))
        updates = out.get("updates")
        built = {}
        if eid is not None:
            built["enemyId"] = _as_int(eid)
        if isinstance(updates, dict):
            built["updates"] = updates
        return built

    # list / query(get_system 등 인자 없음) / get_game_title / get_variables / get_switches
    if action in ("list", "query", "get_game_title", "list_variables", "list_switches"):
        return {}

    return out


def _normalize_structured_action(target_file: str, action: str, target_info: dict[str, Any]) -> str:
    """3단계 플래너 action_type 편차를 4단계(MCP/레거시) 기준으로 정규화한다."""
    a = (action or "").strip().lower()

    if target_file == "Actors.json":
        # 레거시 query는 이름 기반 존재 확인, MCP get_actor는 ID 기반.
        if a == "query" and ("actor_id" in target_info or "actorId" in target_info):
            return "query_by_id"
        # 플래너가 query만 쓰는 경우: 목록/부분검색은 MCP get_actors·search_actors에 맞춤
        if a == "query":
            ti = target_info
            if (
                ti.get("list_actors")
                or ti.get("list_all_actors")
                or ti.get("scope") == "all_actors"
            ):
                return "list"
            has_name = bool(str(ti.get("actor_name") or ti.get("name") or "").strip())
            sterm = str(
                ti.get("searchTerm") or ti.get("search_term") or ti.get("query") or ""
            ).strip()
            if sterm and not has_name:
                return "search"
        # 기존 update(클래스 변경)과 MCP update_actor(일반 속성 수정)를 분리.
        # class_name/class_id가 없으면 이름 변경·일반 필드 수정이지 classId 변경이 아님 → update_actor.
        if a == "update":
            ti = target_info
            has_aid = ti.get("actor_id") is not None or ti.get("actorId") is not None
            has_updates = isinstance(ti.get("updates"), dict) and bool(ti.get("updates"))
            selector = ti.get("selector")
            has_bulk_selector = isinstance(selector, dict) and selector.get("mode") == "all"
            has_class = (
                bool(str(ti.get("class_name") or "").strip()) or ti.get("class_id") is not None
            )

            if has_updates and has_bulk_selector:
                return "update_actor_bulk"
            if has_updates and has_aid:
                return "update_actor"

            new_nm = str(ti.get("new_name") or ti.get("newName") or "").strip()
            old_nm = str(
                ti.get("actor_name") or ti.get("old_name") or ti.get("oldName") or ""
            ).strip()
            nm_field = str(ti.get("name") or "").strip()

            if not has_class:
                if new_nm and (has_aid or old_nm):
                    return "update_actor"
                if nm_field and has_aid:
                    return "update_actor"
                if new_nm or old_nm or has_updates or has_aid or nm_field:
                    return "update_actor"
                return a
            return a

    if target_file == "System.json" and a == "update":
        # 플래너가 광의의 update로 주더라도 MCP 세부 액션으로 자동 분기.
        if "title" in target_info or "game_title" in target_info:
            return "update_game_title"
        if ("variable_id" in target_info or "variableId" in target_info) and "name" in target_info:
            return "set_variable_name"
        if ("switch_id" in target_info or "switchId" in target_info) and "name" in target_info:
            return "set_switch_name"
        if (
            "x" in target_info
            and "y" in target_info
            and ("map_id" in target_info or "mapId" in target_info)
        ):
            return "update_starting_position"
        return a

    # Items / Enemies: 플래너가 "존재 여부 확인"에 query를 쓰는 경우가 많다.
    # MCP·레거시는 read에 search(이름)만 있으므로 query → search 로 흡수한다. (Actors의 query/query_by_id 분기와 대칭)
    if target_file == "Items.json" and a == "query":
        return "search"
    if target_file == "Enemies.json" and a == "query":
        return "search"

    return a


def _actors_old_name_for_reconcile(target_info: dict[str, Any]) -> str:
    """플래너가 준 이전 이름(대상 액터 식별).

    우선순위: actor_name > old_name > oldName > previous_name
    CRITICAL: new_name, newName은 결과 이름이므로 제외!
    """
    candidates = [
        target_info.get("actor_name"),
        target_info.get("old_name"),
        target_info.get("oldName"),
        target_info.get("previous_name"),
        target_info.get("source_name"),  # 추가적인 기존 이름 필드
    ]
    for candidate in candidates:
        if candidate and str(candidate).strip():
            result = str(candidate).strip()
            # new_name과 같으면 사용하지 않음 (혼란 방지)
            new_names = [
                str(target_info.get("new_name") or "").strip(),
                str(target_info.get("newName") or "").strip(),
            ]
            if result not in new_names:
                return result
    return ""


def _actors_reconcile_actor_id_from_name(
    data_path: Path, target_info: dict[str, Any]
) -> dict[str, Any]:
    """이전 이름이 있으면 Actors.json에서 인덱스를 찾아 actor_id를 덮어쓴다.

    플래너가 잘못된 actor_id(예: 세티≠12)를 주는 경우 이름 기준으로 보정한다.
    """
    ti = dict(target_info)
    old_nm = _actors_old_name_for_reconcile(ti)

    # CRITICAL: new_name은 결과 이름이므로 대상 식별에 사용하면 안됨!
    # 대상 식별은 오직 기존 이름(actor_name, old_name 등)으로만 해야 함
    if not old_nm:
        # name 필드만 추가로 확인 (target_name은 제외)
        name_field = str(ti.get("name") or "").strip()
        new_name_field = str(ti.get("new_name") or ti.get("newName") or "").strip()

        # name이 new_name과 다르면 name을 기존 이름으로 간주
        if name_field and name_field != new_name_field:
            old_nm = name_field

    if not old_nm:
        return ti
    try:
        mgr = ActorManager(data_path, "actor_id_reconcile")
        data = mgr.load_json_data()
        if not isinstance(data, list) or not data or data[0] is not None:
            return ti
        idx = mgr.find_by_name(data, old_nm)
        if idx is None:
            logger.warning("[Executor] 액터 '%s' 이름으로 찾기 실패 - 전체 액터 목록 확인", old_nm)
            # 디버깅: 현재 액터 목록 출력
            actors = []
            for i in range(1, min(len(data), 20)):  # 첫 20개만
                if isinstance(data[i], dict) and data[i].get("name"):
                    actors.append(f"id={i}:{data[i]['name']}")
            logger.info("[Executor] 현재 액터들: %s", ", ".join(actors))
            return ti

        planned = ti.get("actorId", ti.get("actor_id"))
        if planned is not None:
            try:
                pi = int(planned)
            except (TypeError, ValueError):
                pi = None
            if pi is not None and pi != idx:
                # 잘못된 매핑인지 실제 확인
                wrong_actor = data[pi] if pi < len(data) and isinstance(data[pi], dict) else None
                wrong_name = wrong_actor.get("name") if wrong_actor else "존재하지 않음"
                logger.error(
                    "[Executor] CRITICAL actor_id 보정: 이름 '%s' → 올바른 id=%s (Definition/플래너 오류: id=%s는 '%s')",
                    old_nm,
                    idx,
                    pi,
                    wrong_name,
                )
        else:
            logger.info("[Executor] actor_id 없음 → 이름 '%s'로 id=%s 설정", old_nm, idx)

        ti["actor_id"] = idx
        ti.pop("actorId", None)

        # 성공적으로 찾은 액터 정보 로깅
        found_actor = data[idx] if idx < len(data) and isinstance(data[idx], dict) else None
        if found_actor:
            logger.info("[Executor] 대상 액터 확인: id=%s, 이름='%s'", idx, found_actor.get("name"))

    except Exception as e:
        logger.error("[Executor] actor_id 이름 보정 실패: %s", e, exc_info=True)
    return ti


def _actors_validate_actor_id_context(
    data_path: Path, target_info: dict[str, Any], step: dict, execution_plan: list = None
) -> dict[str, Any]:
    """actor_name 없이 actor_id만 있을 때, 요청 맥락으로 올바른 액터인지 검증.

    예: "세티를 정민으로 바꿔줘" 요청에서 actor_id=12가 세티가 아니면 보정.
    원본 의도를 execution_plan, step 설명, 글로벌 컨텍스트 등에서 추출.
    """
    ti = dict(target_info)
    aid = ti.get("actor_id")

    try:
        aid_int = int(aid)
        mgr = ActorManager(data_path, "context_validation")
        data = mgr.load_json_data()

        # 범위 밖이어도 의도 추출은 시도 (Definition 오류 보정용)
        current_actor = None
        current_name = ""
        is_invalid_id = aid_int < 1 or aid_int >= len(data)

        if not is_invalid_id and isinstance(data[aid_int], dict):
            current_actor = data[aid_int]
            current_name = current_actor.get("name", "")
        else:
            logger.warning("[Executor] 잘못된/없는 actor_id: %s (범위 밖 또는 null)", aid_int)

        # 스텝 설명에서 원래 의도한 이름 추출 시도
        description = str(step.get("description") or "").lower()
        step_info = str(step.get("target_info") or "")

        # 다양한 소스에서 원본 의도 추출
        original_request = ""

        # 원본 user_input 직접 활용
        user_input = getattr(_execute_one_structured_step, "_current_user_input", "")
        if user_input:
            original_request = str(user_input).lower()
            print(f"🔧 [DEBUG] 원본 사용자 요청: '{user_input[:100]}'")
            logger.warning("[Executor] 🔧 원본 사용자 요청 확인: '%s'", user_input[:100])

        # execution_plan 전체의 다른 스텝들에서도 힌트 추출
        if execution_plan and isinstance(execution_plan, list):
            for other_step in execution_plan:
                if isinstance(other_step, dict):
                    other_desc = str(other_step.get("description") or "").lower()
                    other_info = str(other_step.get("target_info") or "")
                    if other_desc:
                        original_request += " " + other_desc
                    if other_info:
                        original_request += " " + other_info

        # 원본 요청과 스텝 설명 모두에서 의도 추출
        search_texts = [description, step_info, original_request]

        # "세티", "리드" 등 일반적인 이름들 체크
        common_names = [
            "세티",
            "리드",
            "프리실라",
            "게일",
            "미쉘",
            "알버트",
            "케이시",
            "엘리엇",
            "로자",
        ]
        intended_name = None

        for text in search_texts:
            if not text:
                continue
            for name in common_names:
                if name.lower() in text:
                    intended_name = name
                    logger.info("[Executor] 의도한 액터 발견: '%s' (from: %s)", name, text[:50])
                    break
            if intended_name:
                break

        # 의도한 이름이 있고 (현재 actor_id가 다른 액터를 가리키거나 잘못된 ID이면) 보정
        if intended_name and (is_invalid_id or intended_name != current_name):
            correct_idx = mgr.find_by_name(data, intended_name)
            if correct_idx:
                error_desc = f"잘못된 id={aid_int}"
                if is_invalid_id:
                    error_desc += " (범위 밖)"
                elif current_name:
                    error_desc += f" (실제: '{current_name}')"

                logger.error(
                    "[Executor] CRITICAL 맥락 기반 actor_id 보정: 의도='%s' → 올바른 id=%s (%s)",
                    intended_name,
                    correct_idx,
                    error_desc,
                )
                ti["actor_id"] = correct_idx
                ti["_context_corrected"] = True
            else:
                logger.error("[Executor] 의도한 액터 '%s'를 찾을 수 없음", intended_name)

        return ti

    except Exception as e:
        logger.warning("[Executor] 맥락 기반 actor_id 검증 실패: %s", e)
        return ti


def _enrich_actors_target_info_from_deps(
    step: dict,
    step_results: dict[int, dict],
    target_info: dict[str, Any],
) -> dict[str, Any]:
    """선행 step(create/query 등)의 actor_id를 이어 받는다.

    플래너가 query→update에서 서로 다른 actor_id를 주는 경우(예: 설명은 미쉘인데 id=1),
    선행 스텝의 step_results.actor_id가 있으면 update에서 그 값을 우선한다.
    """
    ti = dict(target_info)
    action = str(step.get("action_type") or "").lower()
    dep_actor_id = None
    for d in reversed(step.get("depends_on") or []):
        try:
            did = int(d)
        except (TypeError, ValueError):
            continue
        prev = step_results.get(did)
        if isinstance(prev, dict) and prev.get("actor_id") is not None:
            dep_actor_id = prev["actor_id"]
            break
    if action == "update" and dep_actor_id is not None:
        ti["actor_id"] = dep_actor_id

    if ti.get("actor_id") is not None or ti.get("actorId") is not None:
        return ti
    for d in reversed(step.get("depends_on") or []):
        try:
            did = int(d)
        except (TypeError, ValueError):
            continue
        prev = step_results.get(did)
        if not isinstance(prev, dict):
            continue
        aid = prev.get("actor_id")
        if aid is not None:
            ti["actor_id"] = aid
            break
    return ti


# update_actor: 플래너가 Actors.json 필드를 updates 밖 최상위에 둘 때 MCP updates로 합친다.
_ACTOR_UPDATE_RESERVED_KEYS = frozenset(
    {
        "actor_id",
        "actorId",
        "actor_name",
        "old_name",
        "oldName",
        "new_name",
        "newName",
        "class_name",
        "id",
        "updates",
        "searchTerm",
        "search_term",
        "query",
        "list_actors",
        "list_all_actors",
        "scope",
        "description",
        "condition",
        "_context_corrected",
    }
)


@functools.lru_cache(maxsize=1)
def _actor_target_info_patch_field_names() -> frozenset[str]:
    """agent.schemas.actors.Actor 기준 패치 허용 필드(MZ JSON camelCase). id는 슬롯 식별용이라 제외."""
    from agent.schemas.actors import Actor

    return frozenset(n for n in Actor.model_fields if n != "id")


def _planner_key_to_actor_schema_field(key: str, allowed: frozenset[str]) -> str | None:
    """camelCase 그대로 또는 snake_case → camelCase 로 Actor 필드명에 맞춘다."""
    if key in allowed:
        return key
    if "_" not in key:
        return None
    parts = [p for p in key.split("_") if p]
    if not parts:
        return None
    camel = parts[0].lower() + "".join(p[0].upper() + p[1:].lower() for p in parts[1:] if p)
    return camel if camel in allowed else None


def _coerce_actors_update_actor_target_info(target_info: dict[str, Any]) -> dict[str, Any]:
    """update_actor용: updates·이름 변경·최상위 Actor 스키마 필드를 MCP updates dict로 합친다."""
    ti = dict(target_info)
    merged: dict[str, Any] = {}
    if isinstance(ti.get("updates"), dict):
        merged.update(ti["updates"])

    aid = ti.get("actorId", ti.get("actor_id"))
    new_nm = str(ti.get("new_name") or ti.get("newName") or "").strip()
    old_nm = str(ti.get("actor_name") or ti.get("old_name") or ti.get("oldName") or "").strip()
    if new_nm and (aid is not None or old_nm):
        merged["name"] = new_nm
    else:
        nm = str(ti.get("name") or "").strip()
        has_class = bool(str(ti.get("class_name") or "").strip()) or ti.get("class_id") is not None
        if nm and aid is not None and not has_class and "name" not in merged:
            merged["name"] = nm

    allowed = _actor_target_info_patch_field_names()
    for k, v in ti.items():
        if k in _ACTOR_UPDATE_RESERVED_KEYS:
            continue
        field = _planner_key_to_actor_schema_field(k, allowed)
        if field is None:
            continue
        if field == "name" and "name" in merged:
            continue
        if v is not None:
            merged[field] = v

    if merged:
        ti["updates"] = merged
    return ti


def _structured_error(
    code: str,
    target_file: str,
    action: str,
    message: str,
    *,
    hint: str = "",
) -> str:
    """구조화 실행 경로의 에러 메시지 포맷을 표준화한다."""
    suffix = f" hint={hint}" if hint else ""
    # 외부(LLM/플래너/집계기)가 파싱할 수 있게 고정 포맷으로 반환한다.
    return f"[{code}] target_file={target_file} action={action} message={message}{suffix}"


def _normalize_query_result_for_log(
    step: dict[str, Any],
    entry: dict[str, Any],
    raw_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    target_file = str(step.get("target_file") or entry.get("target_file") or "").strip()
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    action = _normalize_structured_action(
        target_file,
        str(step.get("action_type") or entry.get("action") or ""),
        dict(target_info),
    )
    if action not in {"query", "query_by_id", "search"}:
        return None

    base = raw_result if isinstance(raw_result, dict) else entry
    data = base.get("data") if isinstance(base.get("data"), dict) else {}

    def _as_bool(value: Any) -> bool | None:
        return value if isinstance(value, bool) else None

    def _as_int_list(value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        normalized: list[int] = []
        for item in value:
            try:
                normalized.append(int(item))
            except (TypeError, ValueError):
                continue
        return normalized

    def _as_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    matched_ids: list[int] = []
    matched_names: list[str] = []
    exists = _as_bool(base.get("exists"))

    if target_file == "Actors.json":
        actor_id = base.get("actor_id")
        if actor_id is None:
            actor_id = data.get("id")
        try:
            actor_id_int = int(actor_id) if actor_id is not None else None
        except (TypeError, ValueError):
            actor_id_int = None
        if actor_id_int is not None:
            matched_ids = [actor_id_int]
        if data.get("name"):
            matched_names = [str(data["name"])]
        if exists is None:
            exists = actor_id_int is not None
    elif target_file == "Classes.json":
        class_id = base.get("class_id")
        if class_id is None:
            class_id = data.get("id")
        try:
            class_id_int = int(class_id) if class_id is not None else None
        except (TypeError, ValueError):
            class_id_int = None
        if class_id_int is not None:
            matched_ids = [class_id_int]
        if data.get("name"):
            matched_names = [str(data["name"])]
        if exists is None:
            exists = class_id_int is not None
    else:
        matched_ids = _as_int_list(data.get("matched_ids"))
        matched_names = _as_str_list(data.get("matched_names"))
        if exists is None:
            found = _as_bool(data.get("found"))
            if found is not None:
                exists = found
            elif matched_ids or matched_names:
                exists = True

    if exists is None:
        exists = False

    hit_count = len(matched_ids)
    if hit_count == 0 and exists:
        hit_count = 1

    query_result = {
        "query_type": action,
        "query": dict(target_info),
        "hit_count": hit_count,
        "matched_ids": matched_ids,
        "not_found": not exists,
    }
    if matched_names:
        query_result["matched_names"] = matched_names
    return query_result


def _is_query_like_result(result: dict[str, Any]) -> bool:
    action = str(result.get("action") or "").strip().lower()
    tool_name = str(result.get("tool_name") or "").strip().lower()
    return (
        bool(result.get("query_result"))
        or action in {"query", "query_by_id", "search"}
        or "query" in tool_name
        or "search" in tool_name
    )


def _coerce_optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_log_name(value: Any) -> str:
    return str(value or "").strip()


def _extract_log_target_identity(
    target_file: str,
    step: dict[str, Any],
    log: dict[str, Any],
) -> tuple[int | None, str]:
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}

    if target_file == "Actors.json":
        actor_id = _coerce_optional_int(log.get("actor_id"))
        if actor_id is None:
            actor_id = _coerce_optional_int(
                target_info.get("actor_id") or target_info.get("actorId")
            )
        actor_name = _normalize_log_name(
            log.get("actor_name")
            or target_info.get("actor_name")
            or target_info.get("name")
            or target_info.get("new_name")
        )
        return actor_id, actor_name

    if target_file == "Classes.json":
        class_id = _coerce_optional_int(log.get("class_id"))
        if class_id is None:
            class_id = _coerce_optional_int(
                target_info.get("class_id") or target_info.get("classId")
            )
        class_name = _normalize_log_name(
            log.get("class_name") or target_info.get("class_name") or target_info.get("name")
        )
        return class_id, class_name

    return None, ""


def _extract_query_identity_from_log(
    target_file: str,
    query_result: dict[str, Any],
) -> tuple[int | None, list[int], set[str]]:
    query = query_result.get("query") if isinstance(query_result.get("query"), dict) else {}
    matched_ids = [_coerce_optional_int(item) for item in query_result.get("matched_ids", [])]
    normalized_ids = [item for item in matched_ids if item is not None]
    matched_names = {
        _normalize_log_name(item)
        for item in query_result.get("matched_names", [])
        if _normalize_log_name(item)
    }

    if target_file == "Actors.json":
        query_id = _coerce_optional_int(query.get("actor_id") or query.get("actorId"))
        query_name = _normalize_log_name(query.get("actor_name") or query.get("name"))
    elif target_file == "Classes.json":
        query_id = _coerce_optional_int(query.get("class_id") or query.get("classId"))
        query_name = _normalize_log_name(query.get("class_name") or query.get("name"))
    else:
        query_id = None
        query_name = ""

    if query_name:
        matched_names.add(query_name)
    return query_id, normalized_ids, matched_names


def _query_reference_match_score_for_log(
    target_file: str,
    step: dict[str, Any],
    log: dict[str, Any],
    query_result: dict[str, Any],
) -> int:
    target_id, target_name = _extract_log_target_identity(target_file, step, log)
    if target_id is None and not target_name:
        return 0

    query_id, matched_ids, matched_names = _extract_query_identity_from_log(
        target_file, query_result
    )
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


def _find_direct_source_query_step_ids(
    step: dict[str, Any],
    log: dict[str, Any],
    step_results: dict[int, dict],
) -> list[int]:
    target_file = str(log.get("target_file") or step.get("target_file") or "").strip()
    current_step_id = _coerce_optional_int(log.get("step_id") or step.get("step_id"))
    if not target_file or current_step_id is None:
        return []

    best_score = 0
    best_step_id: int | None = None
    for candidate_step_id in sorted(step_results, reverse=True):
        if candidate_step_id >= current_step_id:
            continue
        candidate_log = step_results.get(candidate_step_id)
        if not isinstance(candidate_log, dict):
            continue
        candidate_target = str(candidate_log.get("target_file") or "").strip()
        candidate_query_result = candidate_log.get("query_result")
        if candidate_target != target_file or not isinstance(candidate_query_result, dict):
            continue
        score = _query_reference_match_score_for_log(target_file, step, log, candidate_query_result)
        if score > best_score:
            best_score = score
            best_step_id = candidate_step_id

    return [best_step_id] if best_step_id is not None else []


def _enrich_changes_log_entry(
    step: dict[str, Any],
    entry: dict[str, Any],
    raw_result: dict[str, Any] | None,
    step_results: dict[int, dict],
) -> dict[str, Any]:
    enriched = dict(entry)
    target_file = str(step.get("target_file") or enriched.get("target_file") or "").strip()
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    action = _normalize_structured_action(
        target_file,
        str(step.get("action_type") or enriched.get("action") or ""),
        dict(target_info),
    )

    if target_file and "target_file" not in enriched:
        enriched["target_file"] = target_file
    if action and "action" not in enriched:
        enriched["action"] = action

    source = raw_result if isinstance(raw_result, dict) else {}
    for key in (
        "exists",
        "actor_id",
        "actor_name",
        "class_id",
        "class_name",
        "updated_fields",
        "original_values",
        "modified_files",
    ):
        if key not in enriched and key in source:
            enriched[key] = source[key]

    query_result = enriched.get("query_result")
    if not isinstance(query_result, dict):
        query_result = _normalize_query_result_for_log(step, enriched, source)
        if query_result is not None:
            enriched["query_result"] = query_result

    if "exists" not in enriched and isinstance(query_result, dict):
        enriched["exists"] = not bool(query_result.get("not_found"))

    if action in {"query", "query_by_id", "search"} and "modified_files" not in enriched:
        enriched["modified_files"] = []

    if action not in {"query", "query_by_id", "search"} and (
        enriched.get("success") is True or enriched.get("skipped")
    ):
        source_query_step_ids = _find_direct_source_query_step_ids(step, enriched, step_results)
        if source_query_step_ids:
            decision_basis = (
                enriched.get("decision_basis")
                if isinstance(enriched.get("decision_basis"), dict)
                else {}
            )
            if not isinstance(
                decision_basis.get("source_query_step_ids"), list
            ) or not decision_basis.get("source_query_step_ids"):
                decision_basis["source_query_step_ids"] = source_query_step_ids
            if not str(decision_basis.get("reason") or "").strip():
                decision_basis["reason"] = "matched prior query_result by target identity"
            enriched["decision_basis"] = decision_basis

    return enriched


def _supports_legacy_fallback(target_file: str, action: str) -> bool:
    """해당 (target_file, action)이 MCP 실패 시 레거시 매니저로 폴백 가능한지."""
    # 이 세트는 "MCP가 실패하더라도 같은 의미의 Python 레거시 처리가 가능한지"를
    # 액션별로 딱 잘라서 정의한다. (자동 추정 금지)
    # 현재 _execute_one_structured_step 내 레거시 분기와 1:1로 맞춘다.
    legacy_supported = {
        ("Classes.json", "query"),
        ("Classes.json", "create"),
        ("Classes.json", "update"),
        ("Actors.json", "query"),
        ("Actors.json", "query_by_id"),
        ("Actors.json", "list"),
        ("Actors.json", "search"),
        ("Actors.json", "create"),
        ("Actors.json", "update"),
        ("Actors.json", "update_actor"),
        ("Actors.json", "update_actor_bulk"),
        ("System.json", "update"),
        ("System.json", "update_game_title"),
        ("System.json", "set_variable_name"),
        ("System.json", "set_switch_name"),
        ("System.json", "update_starting_position"),
        ("Skills.json", "create"),
        ("Skills.json", "create_damage"),
        ("Skills.json", "create_healing"),
        ("Skills.json", "create_buff"),
        ("Skills.json", "create_state"),
        ("Skills.json", "update"),
        ("Items.json", "create"),
        ("Items.json", "update"),
        ("Items.json", "search"),
        ("Enemies.json", "create"),
        ("Enemies.json", "update"),
        ("Enemies.json", "search"),
    }
    return (target_file, action) in legacy_supported


def _is_structured_execution_plan(plan: list[dict]) -> bool:
    """3단계 Planner가 만든 "구조화 실행 플랜"인지 판별한다.

    기대 포맷(필수 키):
      - `step_id`
      - `action_type` (query/create/update 등)
      - `target_file` (예: `Actors.json`, `Classes.json`, `System.json`)
    """
    if not plan or not isinstance(plan[0], dict):
        return False
    row = plan[0]
    return "action_type" in row and "step_id" in row and "target_file" in row


def _collect_structured_target_files(execution_plan: list[dict]) -> set[str]:
    """구조화 플랜에 등장한 JSON 파일들을 추려서 snapshot/backup 범위를 결정한다."""
    files: set[str] = set()
    for step in execution_plan:
        if not isinstance(step, dict):
            continue
        tf = step.get("target_file")
        if isinstance(tf, str) and tf.endswith(".json"):
            files.add(tf)
    return files


def _backup_files_for_structured_step(step: dict[str, Any]) -> list[str]:
    """read-only step은 제외하고 실제 백업이 필요한 파일만 계산한다."""
    if not isinstance(step, dict):
        return []

    target_file = str(step.get("target_file") or "").strip()
    if not target_file.endswith(".json"):
        return []

    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    action = _normalize_structured_action(
        target_file,
        str(step.get("action_type") or ""),
        dict(target_info),
    )
    if not action:
        return []

    mcp_entry = MCP_TOOL_MAP.get((target_file, action))
    if isinstance(mcp_entry, dict):
        raw_backup_files = mcp_entry.get("backup_files")
        if isinstance(raw_backup_files, list):
            return [
                str(file_name)
                for file_name in raw_backup_files
                if isinstance(file_name, str) and file_name.endswith(".json")
            ]

    if action in {
        "query",
        "query_by_id",
        "search",
        "list",
        "list_variables",
        "list_switches",
        "get_game_title",
    }:
        return []

    return [target_file]


def _collect_structured_backup_files(execution_plan: list[dict]) -> list[str]:
    files: set[str] = set()
    for step in execution_plan:
        for file_name in _backup_files_for_structured_step(step):
            files.add(file_name)
    return sorted(files)


def _topological_sort_steps(execution_plan: list[dict]) -> list[dict]:
    """depends_on(step_id) 기준 위상 정렬.

    - 정상: 의존 step이 먼저 실행되게 순서를 만든다.
    - 비정상(순환/누락): 완전 보장은 못하지만 step_id 오름차순으로 폴백한다.
    """
    by_id: dict[int, dict] = {}
    for step in execution_plan:
        if not isinstance(step, dict) or "step_id" not in step:
            continue
        try:
            sid = int(step["step_id"])
        except (TypeError, ValueError):
            continue
        by_id[sid] = step

    if not by_id:
        return list(execution_plan)

    dependents: dict[int, list[int]] = {sid: [] for sid in by_id}
    in_degree: dict[int, int] = {sid: 0 for sid in by_id}

    for sid, step in by_id.items():
        deps_raw = step.get("depends_on") or []
        for d in deps_raw:
            try:
                did = int(d)
            except (TypeError, ValueError):
                continue
            if did in by_id:
                dependents[did].append(sid)
                in_degree[sid] += 1

    queue = sorted(sid for sid in by_id if in_degree[sid] == 0)
    ordered: list[dict] = []
    while queue:
        sid = queue.pop(0)
        ordered.append(by_id[sid])
        for nxt in sorted(dependents[sid]):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
        queue.sort()

    if len(ordered) != len(by_id):
        logger.warning(
            "[Executor] execution_plan 위상 정렬 불완전(순환 또는 누락) → step_id 순으로 폴백"
        )
        return sorted(by_id.values(), key=lambda s: int(s.get("step_id", 0)))
    return ordered


def _should_execute_structured_step(step: dict, step_results: dict[int, dict]) -> tuple[bool, str]:
    """조건부로 step 실행/스킵을 결정한다.

    MVP에서는 아래 휴리스틱을 적용한다.
    - `depends_on` 결과가 없거나(누락), 의존 step이 실패하면 현재 step은 실행하지 않는다.
    - `action_type == "create"`이고 `condition`에 "존재하지 않/없을 경우..." 같은 문구가 있으면
      이전 `query` 결과의 `exists`를 보고 create를 스킵한다.
    """
    try:
        # step_id 파싱이 실패하면(형식 이상) 안전하게 실행 여부를 기본값으로 반환
        int(step.get("step_id", -1))
    except (TypeError, ValueError):
        return True, ""

    deps = step.get("depends_on") or []
    dep_ids: list[int] = []
    for d in deps:
        try:
            dep_ids.append(int(d))
        except (TypeError, ValueError):
            continue

    for did in dep_ids:
        if did not in step_results:
            return False, f"의존 step {did} 결과 없음"

    action = (step.get("action_type") or "").strip().lower()
    condition = (step.get("condition") or "").strip()

    if action in {"create", "update", "delete"} and dep_ids:
        for did in dep_ids:
            prev = step_results[did]
            if not prev.get("skipped") and prev.get("success") is False:
                return False, f"의존 step {did} 실패로 {action} 불가"

    if action == "create" and condition:
        cond_create = any(k in condition for k in ("존재하지 않", "없을 경우", "없으면", "없을 때"))
        if cond_create and dep_ids:
            for did in dep_ids:
                prev = step_results[did]
                if prev.get("skipped"):
                    continue
                if prev.get("exists") is True:
                    return False, "조건: 이미 존재 → create 스킵"
                if prev.get("action") == "query" and prev.get("exists") is True:
                    return False, "조건: 이미 존재 → create 스킵"

    return True, ""


async def _execute_one_structured_step(
    step: dict,
    data_path: Path,
    step_results: dict[int, dict],
    game_id: str,
) -> dict[str, Any]:
    """단일 구조화 step 실행(4단계).

    - 입력: Planner가 만든 한 step(=action_type + target_file + target_info)
    - 처리: (선택) MCP_ENABLED + MCP_TOOL_MAP 이면 Node MCP `call_tool` → 실패 시 매니저 폴백
    - 출력: `changes_log`에 들어갈 step 결과 + `step_results` 누적
    """
    sid = int(step["step_id"])
    target_file = (step.get("target_file") or "").strip()
    target_info = step.get("target_info") if isinstance(step.get("target_info"), dict) else {}
    target_info = dict(target_info)
    if target_file == "Items.json":
        target_info = _enrich_items_target_info_from_deps(step, step_results, target_info)
    if target_file == "Actors.json":
        print(f"🔧 [EXECUTOR DEBUG] 액터 스텝 처리 시작: step_id={sid}")
        logger.warning("🔧 [EXECUTOR DEBUG] 액터 스텝 처리 시작: step_id=%s", sid)

        target_info = _enrich_actors_target_info_from_deps(step, step_results, target_info)
        target_info = _actors_reconcile_actor_id_from_name(data_path, target_info)

        # CRITICAL: actor_name 없이 actor_id만 있는 경우 추가 검증
        old_name_check = _actors_old_name_for_reconcile(target_info)
        aid = target_info.get("actor_id")

        print(f"🔧 [DEBUG] old_name_check='{old_name_check}', actor_id={aid}")
        logger.warning("🔧 [DEBUG] old_name_check='%s', actor_id=%s", old_name_check, aid)

        if not old_name_check and aid:
            aid_str = str(aid)
            print(f"🔧 [DEBUG] 맥락 검증 진입: aid={aid}, isdigit={aid_str.isdigit()}")
            logger.warning("🔧 [DEBUG] 맥락 검증 진입: aid=%s, isdigit=%s", aid, aid_str.isdigit())

            if aid_str.isdigit():
                # execution_plan 전체를 맥락 검증에 전달
                ep = getattr(_execute_one_structured_step, "_current_execution_plan", None)
                print("🔧 [DEBUG] 맥락 검증 실행 중...")
                logger.warning("🔧 [DEBUG] 맥락 검증 실행 중...")

                target_info = _actors_validate_actor_id_context(data_path, target_info, step, ep)

                print(f"🔧 [DEBUG] 맥락 검증 완료: {target_info}")
                logger.warning("🔧 [DEBUG] 맥락 검증 완료: %s", target_info)
    # raw_action은 디버그/에러 메시지에 남기고, 실제 실행 분기는 정규화된 action으로 통일한다.
    raw_action = (step.get("action_type") or "").strip().lower()
    action = _normalize_structured_action(target_file, raw_action, target_info)
    if target_file == "Actors.json" and action == "update_actor":
        target_info = _coerce_actors_update_actor_target_info(target_info)
    ts = datetime.now().isoformat()

    # 정규화 결과 로깅 (편차가 있을 때만)
    if raw_action != action:
        logger.debug("[Executor] action 정규화: %s → %s (step %d)", raw_action, action, sid)

    try:
        # ── MCP 인터셉터: 켜져 있고 (파일, 액션) 매핑이 있으면 stdio MCP 우선 ──
        # 성공 시 즉시 반환. 실패·미설정 시 아래 Class/Actor/System 매니저로 폴백한다.
        if is_mcp_enabled():
            mcp_entry = MCP_TOOL_MAP.get((target_file, action))
            mcp_server_id: str | None = None
            if isinstance(mcp_entry, dict):
                _explicit = (
                    str(mcp_entry["mcp_server"]).strip() if mcp_entry.get("mcp_server") else None
                )
                _tool_nm = str(mcp_entry["tool"]).strip() if mcp_entry.get("tool") else None
                mcp_server_id = resolve_mcp_server_key(target_file, _tool_nm, _explicit)
                _eff_srv = (
                    mcp_server_id
                    or os.environ.get("MCP_DEFAULT_SERVER", "default").strip()
                    or "default"
                )
                logger.debug(
                    "[Executor] MCP 서버 키=%s (effective=%s) target_file=%s tool=%s step=%d",
                    mcp_server_id,
                    _eff_srv,
                    target_file,
                    _tool_nm,
                    sid,
                )
            if mcp_entry and build_stdio_server_parameters(mcp_server=mcp_server_id) is not None:
                logger.debug("[Executor] MCP 시도: tool=%s, step=%d", mcp_entry["tool"], sid)
                # MCP 툴은 구조화 step의 target_info를 툴 inputSchema에 맞게 정규화한 뒤 호출한다.
                # 결과 성공 여부는 call_mcp_tool이 {success,data,error,modified_files}로 정리한 값을 사용한다.
                norm = _normalize_mcp_arguments(target_file, action, target_info)
                path_key = os.environ.get("MCP_PATH_ARG_NAME", "targetDir")
                async with game_locks[game_id]:
                    r = await call_mcp_tool(
                        mcp_entry["tool"],
                        norm,
                        data_path,
                        path_arg_name=path_key,
                        mcp_server=mcp_server_id,
                    )
                if r.get("success"):
                    modified_files = r.get("modified_files") or mcp_entry.get(
                        "backup_files", [target_file]
                    )
                    r_out = _enrich_mcp_search_tool_result(
                        mcp_entry["tool"],
                        r,
                        data_path=data_path,
                        norm_args=norm,
                    )
                    if mcp_entry.get("tool") == "get_actor":
                        aid_norm = norm.get("actorId") if norm else None
                        if aid_norm is not None:
                            r_out["actor_id"] = _as_int(aid_norm)
                    logger.info(
                        "[Executor] MCP 성공: step=%d, tool=%s, files=%s exists=%s",
                        sid,
                        mcp_entry["tool"],
                        modified_files,
                        r_out.get("exists"),
                    )
                    step_results[sid] = {**r_out, "step_id": sid}
                    entry: dict[str, Any] = {
                        "step_id": sid,
                        "tool_name": mcp_entry["tool"],
                        "success": True,
                        "stdout": str(r_out.get("data", "")),
                        "stderr": r_out.get("error") or "",
                        "modified_files": modified_files,
                        "structured": True,
                        "timestamp": ts,
                    }
                    if "exists" in r_out:
                        entry["exists"] = r_out["exists"]
                    if r_out.get("item_id") is not None:
                        entry["item_id"] = r_out["item_id"]
                    if r_out.get("actor_id") is not None:
                        entry["actor_id"] = r_out["actor_id"]
                    if r_out.get("skill_id") is not None:
                        entry["skill_id"] = r_out["skill_id"]
                    return entry
                logger.warning(
                    "[Executor] MCP 실패, 레거시 매니저로 폴백 step_id=%s err=%s",
                    sid,
                    r.get("error"),
                )
                if not _supports_legacy_fallback(target_file, action):
                    # MCP는 실패했지만, 동일 작업을 레거시로 복구할 수 없는 케이스이므로 중단(Abort).
                    err = _structured_error(
                        "MCP_ABORT_NO_FALLBACK",
                        target_file,
                        action,
                        str(r.get("error") or "unknown mcp error"),
                        hint=f"tool={mcp_entry['tool']}",
                    )
                    logger.error("[Executor] MCP 중단: step=%d, %s", sid, err)
                    step_results[sid] = {"success": False, "error": err, "step_id": sid}
                    return {
                        "step_id": sid,
                        "tool_name": mcp_entry["tool"],
                        "success": False,
                        "stderr": err,
                        "structured": True,
                        "timestamp": ts,
                    }
            else:
                if not mcp_entry:
                    logger.debug("[Executor] MCP 매핑 없음: (%s, %s)", target_file, action)
                else:
                    logger.debug("[Executor] MCP 설정 없음, 레거시로")

        # target_file/action_type 조합을 현재 MVP에서 지원하는 매니저 호출로 매핑한다.
        if target_file == "Classes.json" and action == "query":
            logger.debug("[Executor] 레거시 분기: Classes.query")
            mgr = ClassManager(data_path, f"struct_{sid}")
            r = await mgr.execute("query", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_classes_query",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "exists": r.get("exists"),
                "class_id": r.get("class_id"),
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Classes.json" and action == "create":
            logger.debug("[Executor] 레거시 분기: Classes.create")
            mgr = ClassManager(data_path, f"struct_{sid}")
            r = await mgr.execute("create", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_classes_create",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "class_id": r.get("class_id"),
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Classes.json" and action == "update":
            logger.debug("[Executor] 레거시 분기: Classes.update")
            mgr = ClassManager(data_path, f"struct_{sid}")
            r = await mgr.execute("update", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_classes_update",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "list":
            logger.debug("[Executor] 레거시 분기: Actors.list")
            mgr = ActorManager(data_path, f"struct_{sid}")
            r = await mgr.execute("list", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_list",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "search":
            logger.debug("[Executor] 레거시 분기: Actors.search")
            mgr = ActorManager(data_path, f"struct_{sid}")
            r = await mgr.execute("search", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_search",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "exists": r.get("exists"),
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "query":
            logger.debug("[Executor] 레거시 분기: Actors.query")
            mgr = ActorManager(data_path, f"struct_{sid}")
            r = await mgr.execute("query", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_query",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "exists": r.get("exists"),
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "query_by_id":
            # MCP get_actor 미구동 시에도 플래너의 ID 조회 스텝이 실패하지 않도록 ActorManager로 처리
            logger.debug("[Executor] 레거시 분기: Actors.query_by_id")
            mgr = ActorManager(data_path, f"struct_{sid}")
            r = await mgr.execute("query_by_id", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_query_by_id",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "exists": r.get("exists"),
                "actor_id": r.get("actor_id"),
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "create":
            logger.debug("[Executor] 레거시 분기: Actors.create")
            mgr = ActorManager(data_path, f"struct_{sid}")
            # Planner가 class_id를 생략할 수 있어서 기본값(=1)으로 안전 처리한다.
            class_id = target_info.get("class_id", 1)
            try:
                class_id = int(class_id)
            except (TypeError, ValueError):
                class_id = 1
            r = await mgr.execute("create", target_info=target_info, class_id=class_id)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_create",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "update":
            logger.debug("[Executor] 레거시 분기: Actors.update (classId 변경)")
            mgr = ActorManager(data_path, f"struct_{sid}")
            # MVP update는 `classId` 변경만 지원한다(=class_name 또는 class_id로 resolve).
            r = await mgr.execute("update_class", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_update",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "update_actor_bulk":
            logger.debug("[Executor] 레거시 분기: Actors.update_actor_bulk (일괄 속성)")
            mgr = ActorManager(data_path, f"struct_{sid}")
            r = await mgr.execute("update_general_bulk", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_bulk_update_general",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if False and target_file == "Actors.json" and action == "update_actor_bulk":
            logger.debug("[Executor] 레거시 분기: Actors.update_actor_bulk (일괄 수정)")
            mgr = ActorManager(data_path, f"struct_{sid}")
            r = await mgr.execute("update_general_bulk", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_bulk_update_general",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Actors.json" and action == "update_actor":
            logger.debug("[Executor] 레거시 분기: Actors.update_actor (일반 속성)")
            mgr = ActorManager(data_path, f"struct_{sid}")
            # update_actor는 이름 변경 등 일반 속성 수정을 처리한다.
            r = await mgr.execute("update_general", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_actors_update_general",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "System.json" and action == "update":
            logger.debug("[Executor] 레거시 분기: System.update (partyMembers)")
            mgr = SystemManager(data_path, f"struct_{sid}")
            # MVP update는 `partyMembers`에 actor를 추가하는 케이스만 지원한다.
            r = await mgr.execute("add_party_member", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_system_update",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        # System의 세부 update 액션들 (MCP 폴백용)
        if target_file == "System.json" and action in (
            "update_game_title",
            "set_variable_name",
            "set_switch_name",
            "update_starting_position",
        ):
            logger.debug("[Executor] 레거시 분기: System.%s", action)
            mgr = SystemManager(data_path, f"struct_{sid}")
            r = await mgr.execute(action, target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": f"structured_system_{action}",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Skills.json" and action in (
            "create",
            "create_damage",
            "create_healing",
            "create_buff",
            "create_state",
        ):
            logger.debug("[Executor] 레거시 분기: Skills.%s", action)
            mgr = SkillManager(data_path, f"struct_{sid}")
            name = (target_info.get("name") or target_info.get("skill_name") or "").strip()
            if not name:
                err = f"Skills 스텝 {action}: name 또는 skill_name 필요"
                logger.warning("[Executor] %s", err)
                step_results[sid] = {"success": False, "error": err, "step_id": sid}
                return {
                    "step_id": sid,
                    "tool_name": f"structured_skills_{action}",
                    "success": False,
                    "stderr": err,
                    "structured": True,
                    "timestamp": ts,
                }
            extra = {
                k: target_info[k]
                for k in ("mpCost", "description", "damageFormula", "healFormula")
                if k in target_info
            }
            r = await mgr.execute("add", name, **extra)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": f"structured_skills_{action}",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "modified_files": r.get("modified_files"),
                "structured": True,
                "timestamp": ts,
            }

        if target_file == "Skills.json" and action == "update":
            logger.debug("[Executor] 레거시 분기: Skills.update")
            mgr = SkillManager(data_path, f"struct_{sid}")
            skill_id = target_info.get("skill_id") or target_info.get("skillId")
            updates = target_info.get("updates")
            if skill_id is None or not isinstance(updates, dict):
                err = "Skills update에는 skill_id와 updates가 필요합니다."
                logger.warning("[Executor] %s", err)
                step_results[sid] = {"success": False, "error": err, "step_id": sid}
                return {
                    "step_id": sid,
                    "tool_name": "structured_skills_update",
                    "success": False,
                    "stderr": err,
                    "structured": True,
                    "timestamp": ts,
                }
            # SkillManager의 update 액션 사용 (skill_id 기반)
            r = await mgr.execute("update", f"skill_{skill_id}", target_info=target_info)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_skills_update",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "modified_files": r.get("modified_files"),
                "structured": True,
                "timestamp": ts,
            }

        # Items/Enemies 신규 생성: Definition이 item_id/enemy_id를 주면 JSON에 직접 쓴다.
        # (MCP에 create_item이 없던 레거시 한계를 우회)
        if target_file == "Items.json" and action == "create":
            if target_info.get("item_id") is not None or target_info.get("itemId") is not None:
                logger.debug("[Executor] 구조화: Items.json.create → JSON 직접 저장")
                async with game_locks[game_id]:
                    r = await asyncio.to_thread(
                        _structured_create_item_sync, data_path, target_info
                    )
                step_results[sid] = {**r, "step_id": sid}
                mf = r.get("modified_files") or ["Items.json"]
                return {
                    "step_id": sid,
                    "tool_name": "structured_items_create_json",
                    "success": bool(r.get("success")),
                    "stdout": r.get("stdout", ""),
                    "stderr": r.get("stderr", ""),
                    "modified_files": mf,
                    "structured": True,
                    "timestamp": ts,
                }

        if target_file == "Enemies.json" and action == "create":
            if target_info.get("enemy_id") is not None or target_info.get("enemyId") is not None:
                logger.debug("[Executor] 구조화: Enemies.json.create → JSON 직접 저장")
                async with game_locks[game_id]:
                    r = await asyncio.to_thread(
                        _structured_create_enemy_sync, data_path, target_info
                    )
                step_results[sid] = {**r, "step_id": sid}
                mf = r.get("modified_files") or ["Enemies.json"]
                return {
                    "step_id": sid,
                    "tool_name": "structured_enemies_create_json",
                    "success": bool(r.get("success")),
                    "stdout": r.get("stdout", ""),
                    "stderr": r.get("stderr", ""),
                    "modified_files": mf,
                    "structured": True,
                    "timestamp": ts,
                }

        # Items/Enemies는 executor_v2 dispatch로 처리한다.
        if target_file in ("Items.json", "Enemies.json") and action in (
            "create",
            "update",
            "search",
        ):
            logger.debug("[Executor] executor_v2 dispatch fallback: %s.%s", target_file, action)
            try:
                async with game_locks[game_id]:
                    r = await asyncio.to_thread(
                        dispatch_step, data_path, action, target_file, target_info
                    )
                step_results[sid] = {**r, "step_id": sid}
                return {
                    "step_id": sid,
                    "tool_name": f"structured_{target_file.replace('.json', '').lower()}_{action}",
                    "success": bool(r.get("success", False)),
                    "stdout": r.get("message", ""),
                    "stderr": r.get("error") or "",
                    "modified_files": r.get("modified_files", []),
                    "structured": True,
                    "timestamp": ts,
                }
            except Exception as e:
                err = f"executor_v2 dispatch 호출 실패: {e}"
                logger.error("[Executor] %s (step %d)", err, sid)
                step_results[sid] = {"success": False, "error": err, "step_id": sid}
                return {
                    "step_id": sid,
                    "tool_name": f"structured_{target_file.replace('.json', '').lower()}_{action}",
                    "success": False,
                    "stderr": err,
                    "structured": True,
                    "timestamp": ts,
                }

        # ── executor_v2 dispatch 최종 fallback ──────────────────
        # MCP 매핑 없음 + 레거시 매니저 매핑 없음인 경우,
        # executor_v2 의 dispatch_step (순수 Python CRUD) 으로 최종 시도한다.
        # dispatch_step 은 entity 8종 + System.json + Map 을 커버하므로
        # 대부분의 미지원 action 을 여기서 처리할 수 있다.
        logger.info(
            "[Executor] MCP/레거시 미지원 → executor_v2 dispatch 최종 fallback: %s.%s (step %d)",
            target_file,
            action,
            sid,
        )
        try:
            async with game_locks[game_id]:
                r = await asyncio.to_thread(
                    dispatch_step, data_path, action, target_file, target_info
                )
            if r.get("success"):
                step_results[sid] = {**r, "step_id": sid}
                return {
                    "step_id": sid,
                    "tool_name": f"structured_{target_file.replace('.json', '').lower()}_{action}",
                    "success": True,
                    "stdout": r.get("message", ""),
                    "stderr": "",
                    "entity_id": r.get("entity_id"),
                    "modified_files": r.get("modified_files", []),
                    "structured": True,
                    "timestamp": ts,
                }
            # dispatch_step 도 실패한 경우 아래 UNSUPPORTED 로 진행
            logger.warning(
                "[Executor] executor_v2 dispatch 도 실패: %s (step %d)",
                r.get("error", "unknown"),
                sid,
            )
        except Exception as e:
            logger.warning(
                "[Executor] executor_v2 dispatch 예외: %s (step %d)",
                e,
                sid,
            )

        # ── 최종 미지원 ──────────────────────────────────────
        # MCP, 레거시 매니저, executor_v2 dispatch 모두 실패한 경우.
        err = _structured_error(
            "UNSUPPORTED_STRUCTURED_STEP",
            target_file,
            action,
            "no mcp/legacy/dispatch handler",
            hint=f"raw_action={raw_action}",
        )
        logger.error("[Executor] 미지원 스텝: %s", err)
        step_results[sid] = {"success": False, "error": err, "step_id": sid}
        result = {
            "step_id": sid,
            "tool_name": f"structured_{target_file}_{action}_UNSUPPORTED",
            "success": False,
            "stderr": f"CRITICAL: {err}",
            "stdout": "",
            "structured": True,
            "timestamp": ts,
        }
        return result
    except Exception as e:
        logger.exception("[Executor] 구조화 스텝 실행 실패 step_id=%s", sid)
        step_results[sid] = {"success": False, "error": str(e), "step_id": sid}
        result = {
            "step_id": sid,
            "tool_name": "structured_error",
            "success": False,
            "stderr": str(e),
            "structured": True,
            "timestamp": ts,
        }
        return result


_ITEM_CREATE_SKIP_KEYS = frozenset(
    {
        "item_id",
        "itemId",
        "updates",
        "new_description",
        "new_name",
        "newName",
        "query",
        "searchTerm",
        "search_term",
        "item_name",
    }
)


def _sanitize_mz_item_effects_for_schema(effects: Any) -> list[dict[str, Any]]:
    """MZ 관례(code 11/12는 회복량을 value2에 두는 경우가 많음)에 맞게 보정한다."""
    if not isinstance(effects, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in effects:
        if not isinstance(raw, dict):
            continue
        e = dict(raw)
        code = e.get("code")
        if code in (11, 12):
            v1, v2 = e.get("value1", 0), e.get("value2", 0)
            try:
                v1n = float(v1)
                v2n = float(v2)
            except (TypeError, ValueError):
                v1n, v2n = 0.0, 0.0
            if v1n > 10 and v2n == 0:
                e["value2"] = v1
                e["value1"] = 0
        out.append(e)
    return out


def _apply_mz_item_required_defaults(payload: dict[str, Any]) -> None:
    """Planner/LLM이 Item 필수 필드를 빼거나 null로 넣는 경우를 보정한다.

    setdefault만으로는 부족함: target_info에 ``occasion: null``이 있으면 키가 존재해 기본값이 안 들어감.
    """
    int_defaults: dict[str, int] = {
        "occasion": 0,
        "scope": 7,
        "speed": 0,
        "successRate": 100,
        "repeats": 1,
        "tpGain": 0,
        "hitType": 0,
        "animationId": -1,
    }
    for key, default in int_defaults.items():
        cur = payload.get(key)
        if cur is None:
            payload[key] = default
            continue
        if isinstance(cur, str) and cur.strip() == "":
            payload[key] = default


def _structured_create_item_sync(data_path: Path, target_info: dict[str, Any]) -> dict[str, Any]:
    """구조화 플랜의 target_info로 Items.json 슬롯에 아이템을 기록한다 (MCP create_item 미노출 대응)."""
    from agent.schemas.items import Item

    ts = datetime.now().isoformat()
    raw_id = target_info.get("item_id") or target_info.get("itemId")
    if raw_id is None:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "Items create: item_id가 필요합니다.",
            "modified_files": [],
            "timestamp": ts,
        }
    try:
        item_id = int(raw_id)
    except (TypeError, ValueError):
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"Items create: 잘못된 item_id: {raw_id!r}",
            "modified_files": [],
            "timestamp": ts,
        }

    fp = data_path / "Items.json"
    if not fp.is_file():
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "Items.json 파일이 없습니다.",
            "modified_files": [],
            "timestamp": ts,
        }

    try:
        arr = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"Items.json 읽기 실패: {e}",
            "modified_files": [],
            "timestamp": ts,
        }

    if not isinstance(arr, list) or not arr:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "Items.json 루트는 비어 있지 않은 배열이어야 합니다.",
            "modified_files": [],
            "timestamp": ts,
        }

    while len(arr) <= item_id:
        arr.append(None)

    existing = arr[item_id]
    # Planner는 표시명을 item_name으로만 넘기는 경우가 있음(name 키 없음).
    new_name = str(target_info.get("name") or target_info.get("item_name") or "").strip()
    if existing is not None and isinstance(existing, dict):
        ex_name = str(existing.get("name") or "").strip()
        if ex_name and new_name and ex_name != new_name:
            return {
                "success": False,
                "exit_code": 2,
                "stdout": "",
                "stderr": (f"item_id={item_id} 슬롯에 이미 다른 아이템이 있습니다 ({ex_name!r})."),
                "modified_files": [],
                "timestamp": ts,
            }

    payload: dict[str, Any] = {}
    for k, v in target_info.items():
        if k in _ITEM_CREATE_SKIP_KEYS:
            continue
        if k == "damage" and isinstance(v, dict):
            payload["damage"] = dict(v)
        elif k == "effects" and isinstance(v, list):
            payload["effects"] = _sanitize_mz_item_effects_for_schema(v)
        elif isinstance(v, dict | list | str | int | float | bool) or v is None:
            payload[k] = v

    payload["id"] = item_id
    if not str(payload.get("name") or "").strip():
        payload["name"] = new_name or f"Item {item_id}"

    if "damage" not in payload:
        payload["damage"] = {
            "type": 0,
            "elementId": 0,
            "formula": "0",
            "variance": 20,
            "critical": False,
        }
    else:
        d = payload["damage"]
        if isinstance(d, dict):
            d.setdefault("critical", False)
            d.setdefault("variance", 20)

    payload.setdefault("effects", [])

    _apply_mz_item_required_defaults(payload)

    try:
        model = Item.model_validate(payload)
        final_obj = model.model_dump(mode="json")
    except ValidationError as e:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"아이템 스키마 검증 실패: {e}",
            "modified_files": [],
            "timestamp": ts,
        }

    arr[item_id] = final_obj
    try:
        fp.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": str(e),
            "modified_files": [],
            "timestamp": ts,
        }

    return {
        "success": True,
        "exit_code": 0,
        "stdout": f"Items.json에 아이템 id={item_id} ({final_obj.get('name')}) 저장",
        "stderr": "",
        "modified_files": ["Items.json"],
        "timestamp": ts,
    }


_ENEMY_CREATE_SKIP_KEYS = frozenset(
    {
        "enemy_id",
        "enemyId",
        "updates",
        "query",
        "searchTerm",
        "search_term",
        "enemy_name",
    }
)


def _default_enemy_template_dict() -> dict[str, Any]:
    return {
        "battlerHue": 0,
        "battlerName": "",
        "params": [100, 0, 10, 10, 10, 10, 10, 10],
        "dropItems": [
            {"kind": 0, "dataId": 1, "denominator": 1},
            {"kind": 0, "dataId": 1, "denominator": 1},
            {"kind": 0, "dataId": 1, "denominator": 1},
        ],
        "actions": [
            {
                "skillId": 1,
                "rating": 5,
                "conditionType": 0,
                "conditionParam1": 0,
                "conditionParam2": 0,
            }
        ],
        "traits": [],
        "exp": 10,
        "gold": 5,
        "note": "",
        "name": "",
    }


def _structured_create_enemy_sync(data_path: Path, target_info: dict[str, Any]) -> dict[str, Any]:
    """구조화 플랜으로 Enemies.json 슬롯에 적을 기록한다."""
    from agent.schemas.enemies import Enemy

    ts = datetime.now().isoformat()
    raw_id = target_info.get("enemy_id") or target_info.get("enemyId")
    if raw_id is None:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "Enemies create: enemy_id가 필요합니다.",
            "modified_files": [],
            "timestamp": ts,
        }
    try:
        enemy_id = int(raw_id)
    except (TypeError, ValueError):
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"Enemies create: 잘못된 enemy_id: {raw_id!r}",
            "modified_files": [],
            "timestamp": ts,
        }

    fp = data_path / "Enemies.json"
    if not fp.is_file():
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "Enemies.json 파일이 없습니다.",
            "modified_files": [],
            "timestamp": ts,
        }

    try:
        arr = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"Enemies.json 읽기 실패: {e}",
            "modified_files": [],
            "timestamp": ts,
        }

    if not isinstance(arr, list) or not arr:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": "Enemies.json 루트는 비어 있지 않은 배열이어야 합니다.",
            "modified_files": [],
            "timestamp": ts,
        }

    while len(arr) <= enemy_id:
        arr.append(None)

    existing = arr[enemy_id]
    new_name = str(target_info.get("name") or "").strip()
    if existing is not None and isinstance(existing, dict):
        ex_name = str(existing.get("name") or "").strip()
        if ex_name and new_name and ex_name != new_name:
            return {
                "success": False,
                "exit_code": 2,
                "stdout": "",
                "stderr": (f"enemy_id={enemy_id} 슬롯에 이미 다른 적이 있습니다 ({ex_name!r})."),
                "modified_files": [],
                "timestamp": ts,
            }

    base = _default_enemy_template_dict()
    for k, v in target_info.items():
        if k in _ENEMY_CREATE_SKIP_KEYS:
            continue
        if k in base or k in ("name", "note", "battlerName", "battlerHue", "params", "traits"):
            base[k] = v
        elif k == "actions" and isinstance(v, list):
            base["actions"] = v
        elif k == "dropItems" and isinstance(v, list):
            base["dropItems"] = v

    base["id"] = enemy_id
    if not str(base.get("name") or "").strip():
        base["name"] = new_name or f"Enemy {enemy_id}"

    try:
        model = Enemy.model_validate(base)
        final_obj = model.model_dump(mode="json")
    except ValidationError as e:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"적 스키마 검증 실패: {e}",
            "modified_files": [],
            "timestamp": ts,
        }

    arr[enemy_id] = final_obj
    try:
        fp.write_text(json.dumps(arr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": str(e),
            "modified_files": [],
            "timestamp": ts,
        }

    return {
        "success": True,
        "exit_code": 0,
        "stdout": f"Enemies.json에 적 id={enemy_id} ({final_obj.get('name')}) 저장",
        "stderr": "",
        "modified_files": ["Enemies.json"],
        "timestamp": ts,
    }


_ITEM_UPDATE_ID_KEYS = frozenset({"item_id", "itemId", "id"})


def _enrich_execution_plan_items_from_modifications(
    execution_plan: list[dict],
    modifications: list[dict] | None,
) -> list[dict]:
    """Items.json update 스텝에 플래너가 빼먹은 필드를 Definition modifications.params에서 보강한다.

    damage·effects뿐 아니라 price, description 등 Definition이 넣은 키를 동일 item_id 기준으로
    target_info.updates에 오버레이한다(Definition 값이 우선).
    """
    if not modifications:
        return execution_plan

    mod_params_by_item_id: dict[int, dict[str, Any]] = {}
    for m in modifications:
        if not isinstance(m, dict):
            continue
        if m.get("type") != "update" or m.get("target") != "item":
            continue
        p = m.get("params")
        if not isinstance(p, dict):
            continue
        raw_id = p.get("item_id") or p.get("itemId")
        if raw_id in (None, "NEW"):
            continue
        try:
            iid = int(raw_id)
        except (TypeError, ValueError):
            continue
        mod_params_by_item_id[iid] = p

    if not mod_params_by_item_id:
        return execution_plan

    enriched: list[dict] = []
    for step in execution_plan:
        if not isinstance(step, dict):
            enriched.append(step)
            continue
        s = dict(step)
        if s.get("target_file") != "Items.json":
            enriched.append(s)
            continue
        if str(s.get("action_type") or "").lower() != "update":
            enriched.append(s)
            continue
        ti = s.get("target_info")
        if not isinstance(ti, dict):
            enriched.append(s)
            continue
        ti = dict(ti)
        raw_iid = ti.get("item_id") or ti.get("itemId")
        try:
            iid = int(raw_iid) if raw_iid is not None else None
        except (TypeError, ValueError):
            iid = None
        if iid is None or iid not in mod_params_by_item_id:
            enriched.append(s)
            continue
        src = mod_params_by_item_id[iid]

        overlay_keys = [
            k
            for k in src
            if k not in _ITEM_UPDATE_ID_KEYS and str(k).lower() not in ("item_id", "itemid")
        ]
        if not overlay_keys:
            enriched.append(s)
            continue

        updates: dict[str, Any] = dict(ti["updates"]) if isinstance(ti.get("updates"), dict) else {}
        merged = 0
        for k in overlay_keys:
            v = src[k]
            if v is None:
                continue
            if isinstance(v, dict):
                updates[k] = dict(v)
            elif isinstance(v, list):
                updates[k] = list(v)
            else:
                updates[k] = v
            merged += 1

        if merged == 0:
            enriched.append(s)
            continue

        ti["updates"] = updates
        s["target_info"] = ti
        logger.info(
            "[Executor] Items update에 Definition params 오버레이 | item_id=%s keys=%s",
            iid,
            sorted(updates.keys()),
        )
        enriched.append(s)
    return enriched


async def _executor_structured(
    data_path: Path,
    execution_plan: list[dict],
    game_id: str,
    retry_count: int,
) -> dict[str, Any]:
    """3단계 구조화 execution_plan 전용 실행 경로(4단계 엔진).

    이 경로의 역할은 "planner가 준 step들을 올바른 순서로 실행"하고,
    수정 전/후 스냅샷 및 백업을 묶어서 결과(`changes_log`)로 반환하는 것이다.

    **상태 전달**
    - `current_game_state` / `modified_game_state`는 논리 파일명 → **스냅샷 JSON 파일 절대 경로(str)**.
      내용은 `agent.graph.utils.game_state_json.load_snapshot_payload`로 연다 (2·5단계 공용).
    - `modified_file_paths`: 스냅샷과 별도로, 이번 실행에서 **실제 수정이 보고된** `data/*.json` 절대 경로 목록.
    """
    ordered = _topological_sort_steps(execution_plan)
    target_files = sorted(_collect_structured_target_files(execution_plan))
    if not target_files:
        logger.info("[Executor structured] target_files 비어있음, 기본값 Actors.json 사용")
        target_files = ["Actors.json"]

    logger.info(
        "[Executor structured] game_id=%s steps=%d files=%s",
        game_id,
        len(ordered),
        target_files,
    )

    # 위상 정렬 결과 로깅
    ordered_step_ids = [step.get("step_id") for step in ordered if isinstance(step, dict)]
    logger.debug("[Executor structured] 실행 순서: %s", ordered_step_ids)

    # snapshot/backup은 "실패했을 때 롤백"과 "실행 전/후 비교"를 위한 MVP 장치다.
    run_id = uuid.uuid4().hex
    snap_dir = _executor_snapshot_dir(data_path, run_id)
    logger.info("[Executor structured] 스냅샷 준비: run_id=%s, snap_dir=%s", run_id, snap_dir)

    current_game_state = _copy_snapshot_files_to_disk(data_path, target_files, snap_dir, "before")
    backup_targets = _collect_structured_backup_files(execution_plan)
    if retry_count == 0:
        backup_paths = _create_backup(data_path, backup_targets)
    else:
        backup_paths = {}
        logger.info("[Executor structured] retry=%d → 백업 생성 skip (중복 방지)", retry_count)
    logger.info(
        "[Executor structured] before 스냅샷: %d개 파일, 백업: %d개 파일",
        len(current_game_state),
        len(backup_paths),
    )

    changes_log: list[dict[str, Any]] = []
    step_results: dict[int, dict] = {}

    for step in ordered:
        # Planner output이 깨진 경우에도 전체 실행이 터지지 않게 방어한다.
        if not isinstance(step, dict):
            logger.warning("[Executor structured] 비-dict step 건너뜀: %s", type(step))
            continue
        try:
            sid = int(step.get("step_id", -1))
        except (TypeError, ValueError):
            logger.warning(
                "[Executor structured] step_id 파싱 실패 건너뜀: %s", step.get("step_id")
            )
            continue

        # 의존성/조건 기반으로 "실행할지 말지" 먼저 판정
        should_run, skip_reason = _should_execute_structured_step(step, step_results)
        if not should_run:
            logger.info("[Executor structured] step %d 스킵: %s", sid, skip_reason)
            # 스킵은 "에러"가 아니라 "조건 만족(예: 이미 존재)"인 케이스로 취급한다.
            step_results[sid] = {
                "skipped": True,
                "success": True,
                "reason": skip_reason,
                "step_id": sid,
            }
            changes_log.append(
                {
                    "step_id": sid,
                    "tool_name": f"structured_skip_{step.get('action_type', '')}",
                    "success": True,
                    "skipped": True,
                    "skip_reason": skip_reason,
                    "structured": True,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            changes_log[-1] = _enrich_changes_log_entry(
                step,
                changes_log[-1],
                step_results.get(sid),
                step_results,
            )
            step_results[sid] = {**step_results.get(sid, {}), **changes_log[-1]}
            continue

        # 스텝 실행 시작
        target_file = step.get("target_file", "")
        action_type = step.get("action_type", "")
        logger.info("[Executor structured] step %d 실행 시작: %s.%s", sid, target_file, action_type)

        entry = await _execute_one_structured_step(step, data_path, step_results, game_id)
        entry = _enrich_changes_log_entry(step, entry, step_results.get(sid), step_results)
        step_results[sid] = {**step_results.get(sid, {}), **entry}
        logger.info(
            "[Executor structured] step %d 완료: success=%s, tool=%s",
            sid,
            entry.get("success"),
            entry.get("tool_name"),
        )
        changes_log.append(entry)

    modified_game_state = _copy_snapshot_files_to_disk(data_path, target_files, snap_dir, "after")

    # 실행 요약
    success_count = sum(1 for entry in changes_log if entry.get("success"))
    logger.info(
        "[Executor structured] 전체 완료: %d/%d 성공, after 스냅샷: %d개 파일",
        success_count,
        len(changes_log),
        len(modified_game_state),
    )

    modified_file_paths = _collect_modified_file_paths_from_changes_log(data_path, changes_log)
    result = {
        "modified_game_state": modified_game_state,
        "current_game_state": current_game_state,
        "changes_log": changes_log,
        "tool_results": changes_log,  # progress.md 호환성을 위해 changes_log와 동일하게 설정
        "modified_file_paths": modified_file_paths,
        "backup_paths": backup_paths,
    }
    return result


async def executor(state: AgentState) -> dict:
    """MVP 버전 Executor"""

    execution_plan = state.get("execution_plan", [])
    game_id = state.get("game_id", "game_001")
    retry_count = state.get("retry_count", 0)
    user_input = state.get("user_input", "")
    _t0 = time.perf_counter()

    logger.info("─── 🛠️ Executor START ───────────────────────────────")

    def _finish(result: dict[str, Any], *, mode: str, icon: str | None = None) -> dict[str, Any]:
        changes_log = result.get("changes_log", [])
        if not isinstance(changes_log, list):
            changes_log = []

        modified_file_paths = result.get("modified_file_paths", [])
        if not isinstance(modified_file_paths, list):
            modified_file_paths = []

        backup_paths = result.get("backup_paths", {})
        if not isinstance(backup_paths, dict):
            backup_paths = {}

        failed = sum(1 for entry in changes_log if not entry.get("success"))
        ok = sum(1 for entry in changes_log if entry.get("success"))
        logger.info(
            "─── %s Executor END (elapsed=%.2fs, mode=%s, steps=%d, ok=%d, failed=%d, files=%d) ──",
            icon or ("⚠️" if failed else "✅"),
            time.perf_counter() - _t0,
            mode,
            len(changes_log),
            ok,
            failed,
            len(modified_file_paths),
        )
        return {
            **result,
            "changes_log": changes_log,
            "modified_file_paths": modified_file_paths,
            "backup_paths": backup_paths,
        }

    logger.info("[Executor MVP] 시작: game_id=%s, retry=%d", game_id, retry_count)

    # 맥락 검증을 위해 원본 user_input을 전역에 저장
    _execute_one_structured_step._current_user_input = user_input

    # ── Step 1: 입력 검증 ─────────────────────────────────────
    if retry_count >= 2:
        logger.warning("최대 재시도 초과")
        result = {
            "changes_log": [
                {
                    "step_id": -1,
                    "tool_name": "guard_error",
                    "target_file": "",
                    "action": "guard",
                    "success": False,
                    "error": "최대 재시도(2) 초과. 수행 불가.",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "tool_results": [],
            "modified_file_paths": [],
        }
        return _finish(result, mode="guard", icon="\u26a0\ufe0f")

    if not execution_plan:
        logger.warning("execution_plan이 비어있음")
        result = {
            "changes_log": [
                {
                    "step_id": -1,
                    "tool_name": "guard_error",
                    "target_file": "",
                    "action": "guard",
                    "success": False,
                    "error": "execution_plan이 비어있습니다.",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "tool_results": [],
            "modified_file_paths": [],
        }
        return _finish(result, mode="guard", icon="\u26a0\ufe0f")

    try:
        ep_json = json.dumps(execution_plan, ensure_ascii=False, default=str)
        max_len = 16000
        if len(ep_json) > max_len:
            ep_json = ep_json[:max_len] + f"... (truncated, full_len={len(ep_json)})"
        logger.info(
            "[Executor] 입력 execution_plan (%d steps) JSON: %s",
            len(execution_plan),
            ep_json,
        )

        # 액터 관련 요청인지 확인하고 디버그 정보 추가
        has_actors = any(
            step.get("target_file") == "Actors.json"
            for step in execution_plan
            if isinstance(step, dict)
        )
        if has_actors:
            logger.info("[Executor] 액터 관련 요청 감지 - 추가 디버깅 활성화")
            for i, step in enumerate(execution_plan):
                if isinstance(step, dict) and step.get("target_file") == "Actors.json":
                    logger.info(
                        "[Executor] 액터 스텝 %d: action=%s target_info=%s",
                        i + 1,
                        step.get("action_type"),
                        json.dumps(step.get("target_info", {}), ensure_ascii=False),
                    )

    except (TypeError, ValueError) as je:
        logger.warning("[Executor] execution_plan JSON 로깅 실패: %s", je)

    # ── Step 2: 경로 설정 ─────────────────────────────────────
    data_path = _get_data_path(game_id)

    logger.info("[Executor MVP] 데이터 경로: %s", data_path)

    # ── 3단계 구조화 플랜 (action_type / step_id / target_file) ──
    # 이 포맷이면 LLM 번역 단계(레거시) 없이 곧바로 4단계 구조화 엔진으로 분기한다.
    if _is_structured_execution_plan(execution_plan):
        logger.info("[Executor] 구조화 플랜 분기: %d개 step", len(execution_plan))
        mods = state.get("modifications")
        plan_for_run = _enrich_execution_plan_items_from_modifications(
            execution_plan,
            mods if isinstance(mods, list) else None,
        )
        result = await _executor_structured(data_path, plan_for_run, game_id, retry_count)

        # 액터 관련 요청에서 실패가 있었는지 확인
        changes_log = result.get("changes_log", [])
        failed_steps = [log for log in changes_log if not log.get("success")]
        if failed_steps:
            logger.error(
                "[Executor] 실패한 스텝들: %s",
                [f"step_{s.get('step_id')}:{s.get('tool_name')}" for s in failed_steps],
            )
            for failed in failed_steps:
                if "UNSUPPORTED" in str(failed.get("tool_name", "")):
                    logger.error("[Executor] CRITICAL 실패: %s", failed.get("stderr"))

        return _finish(result, mode="structured")

    logger.warning("[Executor] 비구조화(번역) 경로는 제거된 json_modify_tools에 의존해 비활성화됨")
    result = {
        "changes_log": [
            {
                "success": False,
                "error": (
                    "비구조화 executor 경로는 제거된 legacy json_modify_tools 경로에 "
                    "의존해 더 이상 지원되지 않습니다. 구조화 execution_plan을 사용하세요."
                ),
                "timestamp": datetime.now().isoformat(),
            }
        ],
        "tool_results": [],
        "modified_file_paths": [],
    }
    return _finish(result, mode="legacy_removed", icon="⚠️")


# ────────────────────────────────────────────────────────────
# MVP 헬퍼 함수들
# ────────────────────────────────────────────────────────────


def _get_data_path(game_id: str) -> Path:
    """게임 `data/` 경로. `STORAGE_PATH` 설정과 동일(로컬 개발 vs EC2+S3 동기화 경로)."""
    return get_game_data_path(game_id)


def _collect_modified_file_paths_from_changes_log(
    data_path: Path, changes_log: list[dict[str, Any]]
) -> list[str]:
    """성공 스텝의 `modified_files`를 게임 `data/` 기준 절대 경로 리스트로 모은다.

    - **역할**: `current_game_state` / `modified_game_state`는 스냅샷 파일 경로이고,
      이 필드는 "실제로 쓰인 RPG Maker 데이터 JSON" 경로를 한 줄로 요약해 준다 (보고·추적·테스트).
    - **출처**: MCP `call_mcp_tool` 결과의 `modified_files`, 또는 매니저가 `changes_log` 항목에 넣은 동일 키.
    - 조회 전용 스텝은 보통 `modified_files`가 비어 있거나 생략된다.
    """
    seen: set[str] = set()
    out: list[str] = []
    for entry in changes_log:
        if not entry.get("success"):
            continue
        if entry.get("skipped"):
            continue
        names = entry.get("modified_files")
        if not names:
            continue
        if not isinstance(names, (list, tuple)):
            continue
        for raw in names:
            if not isinstance(raw, str) or not raw.strip():
                continue
            logical = Path(raw).name
            if not logical.endswith(".json"):
                continue
            resolved = str((data_path / logical).resolve())
            if resolved not in seen:
                seen.add(resolved)
                out.append(resolved)
    out.sort()
    return out


def _executor_snapshot_dir(data_path: Path, run_id: str) -> Path:
    """실행 전/후 JSON 사본을 두는 디렉터리 (`data/.executor_snapshots/<run_id>/`)."""
    d = data_path / ".executor_snapshots" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy_snapshot_files_to_disk(
    data_path: Path, target_files: list[str], dest_dir: Path, prefix: str
) -> dict[str, str]:
    """각 대상 파일을 `dest_dir`에 `prefix_<파일명>`으로 복사. 반환: 논리 파일명 → 절대 경로."""
    out: dict[str, str] = {}
    for file_name in target_files:
        src = data_path / file_name
        if not src.exists():
            continue
        dst = dest_dir / f"{prefix}_{file_name}"
        try:
            shutil.copy2(src, dst)
            out[file_name] = str(dst.resolve())
        except OSError as e:
            logger.warning("스냅샷 파일 복사 실패: %s - %s", file_name, e)
    return out


def _create_backup(data_path: Path, target_files: list[str]) -> dict[str, str]:
    """백업 파일 생성 (MVP: 동기 방식)"""
    backup_dir = data_path.parent / "backup"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_paths = {}

    for file_name in target_files:
        src_path = data_path / file_name
        if src_path.exists():
            backup_name = f"{file_name}.{timestamp}.bak"
            backup_path = backup_dir / backup_name

            try:
                shutil.copy2(src_path, backup_path)
                backup_paths[file_name] = str(backup_path)
                logger.debug("백업 생성: %s → %s", file_name, backup_name)
            except Exception as e:
                logger.warning("백업 실패: %s - %s", file_name, e)

    return backup_paths


# ────────────────────────────────────────────────────────────
# MVP 백업/롤백 시스템
# ────────────────────────────────────────────────────────────


def execute_rollback(backup_paths: dict[str, str], data_path: Path) -> list[str]:
    """MVP: 백업 파일로 원상복구"""

    rollback_results = []

    for file_name, backup_path in backup_paths.items():
        target_path = data_path / file_name

        if not Path(backup_path).exists():
            rollback_results.append(f"❌ {file_name}: 백업 파일 없음")
            continue

        try:
            shutil.copy2(backup_path, target_path)
            rollback_results.append(f"✅ {file_name}: 롤백 완료")
            logger.info("롤백 성공: %s ← %s", file_name, backup_path)

        except Exception as e:
            rollback_results.append(f"❌ {file_name}: 롤백 실패 - {e}")
            logger.error("롤백 실패: %s - %s", file_name, e)

    return rollback_results


def cleanup_old_backups(data_path: Path, days_to_keep: int = 3) -> int:
    """MVP: 오래된 백업 파일 정리"""

    backup_dir = data_path.parent / "backup"
    if not backup_dir.exists():
        return 0

    cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
    cleaned_count = 0

    for backup_file in backup_dir.glob("*.bak"):
        if backup_file.stat().st_mtime < cutoff_time:
            try:
                backup_file.unlink()
                cleaned_count += 1
                logger.debug("오래된 백업 삭제: %s", backup_file.name)
            except Exception as e:
                logger.warning("백업 삭제 실패: %s - %s", backup_file.name, e)

    return cleaned_count


# ────────────────────────────────────────────────────────────
# MVP 에러 복구 훅 (Validator 실패시 사용)
# ────────────────────────────────────────────────────────────


async def handle_validation_failure(state: AgentState) -> dict:
    """검증 실패시 롤백 처리 (5단계에서 호출용)"""

    backup_paths = state.get("backup_paths", {})
    game_id = state.get("game_id", "game_001")
    data_path = _get_data_path(game_id)

    if backup_paths:
        logger.warning("검증 실패 감지 - 롤백 실행")
        rollback_results = execute_rollback(backup_paths, data_path)

        return {
            "rollback_executed": True,
            "rollback_results": rollback_results,
            "timestamp": datetime.now().isoformat(),
        }
    else:
        logger.error("롤백 필요하지만 백업 경로 없음")
        return {
            "rollback_executed": False,
            "error": "백업 경로 없음",
            "timestamp": datetime.now().isoformat(),
        }
