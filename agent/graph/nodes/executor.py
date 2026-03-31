"""Executor 노드 — 4단계: 룰베이스 JSON 물리 수정.

MVP 버전: 기존 dispatcher 재활용 + 기본 LLM 번역 + 백업/롤백

구현 단계:
1. 수도코드 LLM 번역 (간단한 키워드 매칭)
2. 기존 dispatcher 함수 호출
3. 백업/롤백 기본 기능
4. changes_log 생성

흐름:
    3단계 수도코드 → LLM 번역 → dispatcher 호출 → 결과 반환
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.mcp_toolbox import build_stdio_server_parameters, call_mcp_tool, is_mcp_enabled
from app.backend.core.game_paths import get_game_data_path
from app.backend.services.json_modify_tools.dispatcher import (
    run_enemies,
    run_items,
    run_levels,
    run_map_villager,
    run_skills,
)
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
# 없는 것: Classes.json / Enemies.json 등 — 이 MCP 리포에 해당 툴이 없음(액터·아이템·스킬·시스템 일부만).
# Actors.json `update`는 레거시(ActorManager 클래스 변경)용이므로 MCP `update_actor`는 action `update_actor`로 구분.
# ────────────────────────────────────────────────────────────
MCP_TOOL_MAP: dict[tuple[str, str], dict[str, Any]] = {
    # Actors.json
    ("Actors.json", "list"): {"tool": "get_actors", "backup_files": []},
    ("Actors.json", "search"): {"tool": "search_actors", "backup_files": []},
    ("Actors.json", "query_by_id"): {"tool": "get_actor", "backup_files": []},
    ("Actors.json", "create"): {"tool": "create_actor", "backup_files": ["Actors.json"]},
    ("Actors.json", "update_actor"): {"tool": "update_actor", "backup_files": ["Actors.json"]},
    # Skills.json
    ("Skills.json", "list"): {"tool": "get_skills", "backup_files": []},
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
    ("Items.json", "list"): {"tool": "get_items", "backup_files": []},
    ("Items.json", "search"): {"tool": "search_items", "backup_files": []},
    ("Items.json", "update"): {"tool": "update_item", "backup_files": ["Items.json"]},
    # Weapons.json / Armors.json (MCP는 조회만 제공)
    ("Weapons.json", "list"): {"tool": "get_weapons", "backup_files": []},
    ("Armors.json", "list"): {"tool": "get_armors", "backup_files": []},
    # System.json (맵 편집 툴 제외, 시작 위치·타이틀·변수·스위치 이름 등)
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
    if target_file == "Items.json" and action == "search":
        return {"searchTerm": _search_term()}

    if target_file == "Items.json" and action == "update":
        iid = out.get("itemId", out.get("item_id"))
        updates = out.get("updates")
        built = {}
        if iid is not None:
            built["itemId"] = _as_int(iid)
        if isinstance(updates, dict):
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
        # 기존 update(클래스 변경)과 MCP update_actor(일반 속성 수정)를 분리.
        if (
            a == "update"
            and "updates" in target_info
            and ("actor_id" in target_info or "actorId" in target_info)
        ):
            return "update_actor"
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

    return a


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


def _supports_legacy_fallback(target_file: str, action: str) -> bool:
    """해당 (target_file, action)이 MCP 실패 시 레거시 매니저로 폴백 가능한지."""
    # 이 세트는 "MCP가 실패하더라도 같은 의미의 Python 레거시 처리가 가능한지"를
    # 액션별로 딱 잘라서 정의한다. (자동 추정 금지)
    # 현재 _execute_one_structured_step 내 레거시 분기와 1:1로 맞춘다.
    legacy_supported = {
        ("Classes.json", "query"),
        ("Classes.json", "create"),
        ("Actors.json", "query"),
        ("Actors.json", "create"),
        ("Actors.json", "update"),
        ("System.json", "update"),
        ("Skills.json", "create"),
    }
    return (target_file, action) in legacy_supported


# ────────────────────────────────────────────────────────────
# MVP 버전: 간단한 툴 매핑
# ────────────────────────────────────────────────────────────

TOOL_MAP = {
    "edit_enemies": run_enemies,
    "edit_items": run_items,
    "edit_skills": run_skills,
    "edit_levels": run_levels,
    "edit_map_villager": run_map_villager,
}

# 대상 파일 매핑 (백업용)
TARGET_FILE_MAP = {
    "edit_enemies": ["Enemies.json"],
    "edit_items": ["Items.json"],
    "edit_skills": ["Skills.json", "Actors.json", "Classes.json", "System.json"],
    "edit_levels": ["Actors.json", "System.json"],
    "edit_map_villager": [],  # 맵 번호에 따라 동적 결정
}


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
    # raw_action은 디버그/에러 메시지에 남기고, 실제 실행 분기는 정규화된 action으로 통일한다.
    raw_action = (step.get("action_type") or "").strip().lower()
    action = _normalize_structured_action(target_file, raw_action, target_info)
    ts = datetime.now().isoformat()

    try:
        # ── MCP 인터셉터: 켜져 있고 (파일, 액션) 매핑이 있으면 stdio MCP 우선 ──
        # 성공 시 즉시 반환. 실패·미설정 시 아래 Class/Actor/System 매니저로 폴백한다.
        if is_mcp_enabled():
            mcp_entry = MCP_TOOL_MAP.get((target_file, action))
            if mcp_entry and build_stdio_server_parameters() is not None:
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
                    )
                if r.get("success"):
                    step_results[sid] = {**r, "step_id": sid}
                    return {
                        "step_id": sid,
                        "tool_name": mcp_entry["tool"],
                        "success": True,
                        "stdout": str(r.get("data", "")),
                        "stderr": r.get("error") or "",
                        "modified_files": r.get("modified_files")
                        or mcp_entry.get("backup_files", [target_file]),
                        "structured": True,
                        "timestamp": ts,
                    }
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
                    step_results[sid] = {"success": False, "error": err, "step_id": sid}
                    return {
                        "step_id": sid,
                        "tool_name": mcp_entry["tool"],
                        "success": False,
                        "stderr": err,
                        "structured": True,
                        "timestamp": ts,
                    }

        # target_file/action_type 조합을 현재 MVP에서 지원하는 매니저 호출로 매핑한다.
        if target_file == "Classes.json" and action == "query":
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

        if target_file == "Actors.json" and action == "query":
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

        if target_file == "Actors.json" and action == "create":
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

        if target_file == "System.json" and action == "update":
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

        if target_file == "Skills.json" and action == "create":
            mgr = SkillManager(data_path, f"struct_{sid}")
            name = (target_info.get("name") or target_info.get("skill_name") or "").strip()
            if not name:
                err = "Skills 스텝 create: name 또는 skill_name 필요"
                step_results[sid] = {"success": False, "error": err, "step_id": sid}
                return {
                    "step_id": sid,
                    "tool_name": "structured_skills_create",
                    "success": False,
                    "stderr": err,
                    "structured": True,
                    "timestamp": ts,
                }
            extra = {k: target_info[k] for k in ("mpCost", "description") if k in target_info}
            r = await mgr.execute("add", name, **extra)
            step_results[sid] = {**r, "step_id": sid}
            return {
                "step_id": sid,
                "tool_name": "structured_skills_create",
                "success": bool(r.get("success")),
                "stdout": r.get("message", ""),
                "stderr": r.get("error") or "",
                "modified_files": r.get("modified_files"),
                "structured": True,
                "timestamp": ts,
            }

        # 위 조건에 없는 target/action 조합은 현재 MVP에서 아직 구현되지 않았다는 뜻이다.
        # (MCP 핸들러 없음 + 레거시 매니저 핸들러 없음)인 "정의되지 않은 액션"이다.
        err = _structured_error(
            "UNSUPPORTED_STRUCTURED_STEP",
            target_file,
            action,
            "no mcp/legacy handler",
            hint=f"raw_action={raw_action}",
        )
        step_results[sid] = {"success": False, "error": err, "step_id": sid}
        return {
            "step_id": sid,
            "tool_name": f"structured_{target_file}_{action}",
            "success": False,
            "stderr": err,
            "structured": True,
            "timestamp": ts,
        }
    except Exception as e:
        logger.exception("[Executor] 구조화 스텝 실행 실패 step_id=%s", sid)
        step_results[sid] = {"success": False, "error": str(e), "step_id": sid}
        return {
            "step_id": sid,
            "tool_name": "structured_error",
            "success": False,
            "stderr": str(e),
            "structured": True,
            "timestamp": ts,
        }


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
    """
    ordered = _topological_sort_steps(execution_plan)
    target_files = sorted(_collect_structured_target_files(execution_plan))
    if not target_files:
        target_files = ["Actors.json"]

    logger.info(
        "[Executor structured] game_id=%s steps=%d files=%s",
        game_id,
        len(ordered),
        target_files,
    )

    # snapshot/backup은 "실패했을 때 롤백"과 "실행 전/후 비교"를 위한 MVP 장치다.
    run_id = uuid.uuid4().hex
    snap_dir = _executor_snapshot_dir(data_path, run_id)
    current_game_state = _copy_snapshot_files_to_disk(data_path, target_files, snap_dir, "before")
    backup_paths = _create_backup(data_path, target_files)

    changes_log: list[dict[str, Any]] = []
    step_results: dict[int, dict] = {}

    for step in ordered:
        # Planner output이 깨진 경우에도 전체 실행이 터지지 않게 방어한다.
        if not isinstance(step, dict):
            continue
        try:
            sid = int(step.get("step_id", -1))
        except (TypeError, ValueError):
            continue

        # 의존성/조건 기반으로 "실행할지 말지" 먼저 판정
        should_run, skip_reason = _should_execute_structured_step(step, step_results)
        if not should_run:
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
            continue

        entry = await _execute_one_structured_step(step, data_path, step_results, game_id)
        changes_log.append(entry)

    modified_game_state = _copy_snapshot_files_to_disk(data_path, target_files, snap_dir, "after")
    return {
        "current_game_state": current_game_state,
        "modified_game_state": modified_game_state,
        "changes_log": changes_log,
        "backup_paths": backup_paths,
        "retry_count": retry_count,
    }


# ────────────────────────────────────────────────────────────
# MVP 버전: 간단한 LLM 번역 스키마
# ────────────────────────────────────────────────────────────


class SimpleToolCall(BaseModel):
    """MVP: 간단한 툴 호출 구조"""

    tool_name: str = Field(
        description="edit_enemies, edit_items, edit_skills, edit_levels, edit_map_villager 중 하나"
    )
    user_input: str = Field(description="해당 툴에 넘길 자연어 입력")
    reasoning: str = Field(default="", description="선택 이유")


class SimplePlan(BaseModel):
    """MVP: LLM이 수도코드를 해석한 결과"""

    tools: list[SimpleToolCall] = Field(description="실행할 툴 목록")
    note: str = Field(default="", description="해석 메모")


async def executor(state: AgentState) -> dict:
    """MVP 버전 Executor"""

    execution_plan = state.get("execution_plan", [])
    game_id = state.get("game_id", "game_001")
    retry_count = state.get("retry_count", 0)

    logger.info("[Executor MVP] 시작: game_id=%s, retry=%d", game_id, retry_count)

    # ── Step 1: 입력 검증 ─────────────────────────────────────
    if retry_count >= 2:
        logger.warning("최대 재시도 초과")
        return {
            "changes_log": [
                {
                    "success": False,
                    "error": "최대 재시도(2) 초과. 수행 불가.",
                    "timestamp": datetime.now().isoformat(),
                }
            ]
        }

    if not execution_plan:
        logger.warning("execution_plan이 비어있음")
        return {
            "changes_log": [
                {
                    "error": "execution_plan이 비어있습니다.",
                    "timestamp": datetime.now().isoformat(),
                }
            ]
        }

    # ── Step 2: 경로 설정 ─────────────────────────────────────
    data_path = _get_data_path(game_id)

    logger.info("[Executor MVP] 데이터 경로: %s", data_path)

    # ── 3단계 구조화 플랜 (action_type / step_id / target_file) ──
    # 이 포맷이면 LLM 번역 단계(레거시) 없이 곧바로 4단계 구조화 엔진으로 분기한다.
    if _is_structured_execution_plan(execution_plan):
        return await _executor_structured(data_path, execution_plan, game_id, retry_count)

    # ── Step 3: LLM 번역 (MVP: 간단한 키워드 기반) ──────────
    try:
        translated_plan = await _translate_execution_plan_mvp(execution_plan)
        logger.info("[Executor MVP] 번역 완료: %d개 툴", len(translated_plan.tools))
    except Exception as e:
        logger.error("[Executor MVP] 번역 실패: %s", e)
        return {
            "changes_log": [
                {
                    "success": False,
                    "error": f"LLM 번역 실패: {e}",
                    "timestamp": datetime.now().isoformat(),
                }
            ]
        }

    # ── Step 4: 대상 파일 수집 및 백업 ────────────────────────
    target_files = set()
    for tool_call in translated_plan.tools:
        target_files.update(TARGET_FILE_MAP.get(tool_call.tool_name, []))

        # 맵 파일 동적 결정
        if tool_call.tool_name == "edit_map_villager":
            import re

            match = re.search(r"(\d+)", tool_call.user_input)
            map_num = int(match.group(1)) if match else 1
            target_files.add(f"Map{map_num:03d}.json")

    tf_list = sorted(target_files)
    run_id = uuid.uuid4().hex
    snap_dir = _executor_snapshot_dir(data_path, run_id)
    current_game_state = _copy_snapshot_files_to_disk(data_path, tf_list, snap_dir, "before")

    # 백업 생성
    backup_paths = _create_backup(data_path, tf_list)

    logger.info("[Executor MVP] 백업 생성: %d개 파일", len(backup_paths))

    # ── Step 5: 툴 순차 실행 ──────────────────────────────────
    changes_log = []

    for i, tool_call in enumerate(translated_plan.tools):
        tool_function = TOOL_MAP.get(tool_call.tool_name)

        if tool_function is None:
            changes_log.append(
                {
                    "step": i + 1,
                    "tool_name": tool_call.tool_name,
                    "success": False,
                    "error": f"지원하지 않는 툴: {tool_call.tool_name}",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            continue

        logger.info(
            "[Executor MVP] 툴 실행: %s('%s')", tool_call.tool_name, tool_call.user_input[:50]
        )

        try:
            # MVP: 스킬은 매니저 사용, 나머지는 기존 dispatcher
            if tool_call.tool_name == "edit_skills":
                # 새로운 스킬 매니저 사용
                skill_manager = SkillManager(data_path, f"mvp_{i}")

                # user_input에서 기본 파라미터 추출
                action = (
                    "add"
                    if any(
                        word in tool_call.user_input.lower() for word in ["추가", "만들", "생성"]
                    )
                    else "update"
                )

                # 스킬 이름 추출 (간단한 매칭)
                skill_names = ["최후의일격", "전체공격", "회복마법", "버프"]
                skill_name = next(
                    (name for name in skill_names if name in tool_call.user_input), "새스킬"
                )

                result = await skill_manager.execute(
                    action=action,
                    target_name=skill_name,
                    mpCost=50,  # MVP: 기본값
                    description=f"{skill_name} 설명",
                )
            else:
                # 기존 dispatcher 함수 호출
                result = await asyncio.to_thread(tool_function, tool_call.user_input)

            changes_log.append(
                {
                    "step": i + 1,
                    "tool_name": tool_call.tool_name,
                    "user_input": tool_call.user_input,
                    "success": result.get("success", False),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "command": result.get("command", ""),
                    "timestamp": result.get("timestamp", datetime.now().isoformat()),
                }
            )

            if result.get("success"):
                logger.info("[Executor MVP] ✅ 성공: %s", result.get("stdout", ""))
            else:
                logger.warning("[Executor MVP] ❌ 실패: %s", result.get("stderr", ""))
                # MVP: 실패해도 다음 툴 계속 실행 (best-effort)

        except Exception as e:
            logger.error("[Executor MVP] 툴 실행 에러: %s", e)
            changes_log.append(
                {
                    "step": i + 1,
                    "tool_name": tool_call.tool_name,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            )

    # ── Step 6: 수정 후 스냅샷 (경로만 state에 반영) ─────────────
    modified_game_state = _copy_snapshot_files_to_disk(data_path, tf_list, snap_dir, "after")

    logger.info(
        "[Executor MVP] 완료: %d개 툴 실행, %d개 파일 수정",
        len(translated_plan.tools),
        len(target_files),
    )

    return {
        "current_game_state": current_game_state,
        "modified_game_state": modified_game_state,
        "changes_log": changes_log,
        "backup_paths": backup_paths,
        "retry_count": retry_count,
    }


# ────────────────────────────────────────────────────────────
# MVP 헬퍼 함수들
# ────────────────────────────────────────────────────────────


def _get_data_path(game_id: str) -> Path:
    """게임 `data/` 경로. `STORAGE_PATH` 설정과 동일(로컬 개발 vs EC2+S3 동기화 경로)."""
    return get_game_data_path(game_id)


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


async def _translate_execution_plan_mvp(execution_plan: list[dict]) -> SimplePlan:
    """MVP: 수도코드를 간단하게 번역"""

    # 수도코드를 문자열로 변환
    plan_text = json.dumps(execution_plan, ensure_ascii=False, indent=2)

    # MVP용 간단한 프롬프트
    system_prompt = """당신은 RPG 게임 수정 명령어 번역기입니다.

## 사용 가능한 툴

| tool_name | 용도 | user_input 예시 |
|-----------|------|-----------------|
| edit_enemies | 몬스터 추가/수정 | "까마귀", "데몬", "슬라임" |
| edit_items | 아이템 추가/수정 | "독약", "회복물약", "마나물약" |
| edit_skills | 스킬 추가/수정 | "최후의일격", "전체공격", "회복마법" |
| edit_levels | 레벨 설정 | "레벨 50으로", "25" |
| edit_map_villager | 맵에 NPC 추가 | "맵 1번에 빌리저", "3번 맵" |

## 규칙
1. 수도코드를 분석해서 위 5개 툴 중 적절한 것 선택
2. user_input은 기존 툴이 이해할 수 있는 한국어 형태로 변환
3. 복수 명령은 tools 배열에 순서대로 나열

## 번역 예시
수도코드: "파이어볼 스킬 추가하고 마나소모 50으로"
→ {"tools": [{"tool_name": "edit_skills", "user_input": "최후의일격"}]}

수도코드: "까마귀 몬스터 추가해줘"
→ {"tools": [{"tool_name": "edit_enemies", "user_input": "까마귀"}]}"""

    user_content = f"다음 수도코드를 번역해주세요:\n\n{plan_text}"

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

    try:
        result = await invoke_llm(messages, structured_output=SimplePlan)
        logger.info("LLM 번역 성공: %d개 툴", len(result.tools))
        return result
    except Exception as e:
        logger.error("LLM 번역 실패: %s", e)
        # MVP: Fallback으로 키워드 기반 번역
        return _fallback_translate(execution_plan)


def _fallback_translate(execution_plan: list[dict]) -> SimplePlan:
    """MVP: LLM 실패시 키워드 기반 번역"""

    logger.warning("Fallback 번역 모드 실행")

    tools = []
    content = json.dumps(execution_plan, ensure_ascii=False).lower()

    # 간단한 키워드 매칭
    if any(word in content for word in ["스킬", "마법", "skill"]):
        tools.append(
            SimpleToolCall(
                tool_name="edit_skills",
                user_input="최후의일격",  # 기본값
                reasoning="스킬 관련 키워드 감지",
            )
        )

    if any(word in content for word in ["몬스터", "적", "enemy", "보스"]):
        tools.append(
            SimpleToolCall(
                tool_name="edit_enemies",
                user_input="슬라임",  # 기본값
                reasoning="몬스터 관련 키워드 감지",
            )
        )

    if any(word in content for word in ["아이템", "템", "item", "포션"]):
        tools.append(
            SimpleToolCall(
                tool_name="edit_items",
                user_input="회복물약",  # 기본값
                reasoning="아이템 관련 키워드 감지",
            )
        )

    if any(word in content for word in ["레벨", "level", "경험치"]):
        # 숫자 추출 시도
        import re

        numbers = re.findall(r"\d+", content)
        level = numbers[0] if numbers else "25"

        tools.append(
            SimpleToolCall(
                tool_name="edit_levels",
                user_input=f"레벨 {level}으로",
                reasoning=f"레벨 관련 키워드 감지, 추출된 숫자: {level}",
            )
        )

    if any(word in content for word in ["맵", "마을", "map", "npc", "빌리저"]):
        # 맵 번호 추출 시도
        import re

        numbers = re.findall(r"\d+", content)
        map_id = numbers[0] if numbers else "1"

        tools.append(
            SimpleToolCall(
                tool_name="edit_map_villager",
                user_input=f"맵 {map_id}번에 빌리저",
                reasoning=f"맵 관련 키워드 감지, 추출된 맵 ID: {map_id}",
            )
        )

    # 아무것도 못 찾으면 기본값
    if not tools:
        tools.append(
            SimpleToolCall(
                tool_name="edit_skills",
                user_input="최후의일격",
                reasoning="키워드 매칭 실패 - 기본 스킬 추가",
            )
        )

    return SimplePlan(tools=tools, note="Fallback 키워드 번역 사용됨")


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
