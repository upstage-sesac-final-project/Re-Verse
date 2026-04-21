"""Events handler — Map / Common / Troop 이벤트 3 종 통합.

Phase I (Task 7) 5 base case 본체 구현:
    1. NPC 대사 (npc_talk)    — code 101 + 401 + 0
    2. 상점    (shop)          — code 302 (+ 605 추가 상품) + 0
    3. 장소 이동 (teleport)    — code 201 + 0
    4. 스위치 트리거 (switch_trigger) — code 121 + 0
    5. 전투 시작 (battle)      — code 301 + 0

Handler 계약 (다른 handler 와 동일):
    execute_events_step(data_path, action, target_file, target_info) -> dict
    return: {"success": bool, "data": Any, "modified_files": list[str], "error": str?, "entity_id": int?}

지원 action:
    - create_common_event / update_common_event / delete_common_event
    - create_troop / update_troop / delete_troop (pages / members)
    - create_map_event / update_map_event  — 특정 MapNNN.json 의 events[] 조작
    - create_event_from_template          — 5 base case template 으로 생성

target_info 예시 (template):
    {
      "template": "npc_talk" | "shop" | "teleport" | "switch_trigger" | "battle",
      "scope": "common" | "map" | "troop",
      "map_id": int,         # scope=map 일 때
      "x": int, "y": int,    # scope=map 일 때
      "name": str,
      "trigger": int,        # common: 1 (자동), 2 (병렬), 0 (없음)
      "config": {...}        # template 별 상세. 아래 _build_* 함수 참조
    }
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAP_FILE_RE = re.compile(r"^Map(\d{3})\.json$", re.IGNORECASE)

EVENT_FILES: frozenset[str] = frozenset({"CommonEvents.json", "Troops.json"})

EVENT_MAP_ACTIONS: frozenset[str] = frozenset(
    {
        "create_event",
        "update_event",
        "add_event_command",
        "create_map_event",
        "update_map_event",
        "create_event_from_template",
    }
)

# ── 외부 계약 ─────────────────────────────────────────────────────────────


def is_event_target(target_file: str, action: str) -> bool:
    """dispatch.py 가 이 handler 로 라우팅할지 결정."""
    if target_file in EVENT_FILES:
        return True
    if _MAP_FILE_RE.match(target_file) and action in EVENT_MAP_ACTIONS:
        return True
    return False


def execute_events_step(
    data_path: Path,
    action: str,
    target_file: str,
    target_info: dict[str, Any],
) -> dict[str, Any]:
    """이벤트 관련 step 실행."""
    try:
        # ── CommonEvents.json ──
        if target_file == "CommonEvents.json":
            if action == "create_common_event":
                return _create_common_event(data_path, target_info)
            if action == "update_common_event":
                return _update_common_event(data_path, target_info)
            if action == "delete_common_event":
                return _delete_common_event(data_path, target_info)
            return _err(f"CommonEvents.json 미지원 action: {action}")

        # ── Troops.json ──
        if target_file == "Troops.json":
            if action == "create_troop":
                return _create_troop(data_path, target_info)
            if action == "add_troop_event_command":
                return _add_troop_event_command(data_path, target_info)
            return _err(f"Troops.json 미지원 action: {action}")

        # ── MapNNN.json ──
        m = _MAP_FILE_RE.match(target_file)
        if m:
            map_id = int(m.group(1))
            if action == "create_event_from_template":
                return _create_event_from_template(data_path, map_id, target_info)
            if action in {"create_event", "create_map_event"}:
                return _create_map_event(data_path, map_id, target_info)
            if action in {"update_event", "update_map_event"}:
                return _update_map_event(data_path, map_id, target_info)
            if action == "add_event_command":
                return _add_event_command(data_path, map_id, target_info)
            return _err(f"MapNNN.json 미지원 action: {action}")

        return _err(f"알 수 없는 target_file: {target_file}")
    except FileNotFoundError as e:
        return _err(f"파일 없음: {e}")
    except json.JSONDecodeError as e:
        return _err(f"JSON 파싱 실패: {e}")
    except Exception as e:  # pragma: no cover
        logger.exception("[events] 예기치 못한 오류")
        return _err(f"예외: {e}")


# ── 5 base case 템플릿 빌더 ───────────────────────────────────────────────


def _cmd(code: int, indent: int = 0, *parameters: Any) -> dict:
    """EventCommand dict 생성. schemas/events.py 의 EventCommand 와 호환."""
    return {"code": code, "indent": indent, "parameters": list(parameters)}


def _terminator(indent: int = 0) -> dict:
    return {"code": 0, "indent": indent, "parameters": []}


def build_npc_talk_commands(
    text: str,
    *,
    face_name: str = "",
    face_index: int = 0,
    background: int = 0,
    position: int = 2,
) -> list[dict]:
    """NPC 대사 commands — code 101 (얼굴·배경·위치) + 401 (실제 텍스트) + 0 (종결)."""
    lines = (text or "").split("\n")
    out: list[dict] = [_cmd(101, 0, face_name, face_index, background, position)]
    for line in lines:
        out.append(_cmd(401, 0, line))
    out.append(_terminator(0))
    return out


def build_shop_commands(
    items: list[dict],
    *,
    purchase_only: bool = False,
) -> list[dict]:
    """상점 commands — code 302 (첫 상품) + 605 (추가 상품 N-1 개) + 0.

    items: [{"kind": 0|1|2, "id": int, "price_type": 0|1, "price": int}]
        kind: 0=아이템, 1=무기, 2=방어구
        price_type: 0=표준가, 1=지정가
    """
    if not items:
        return [_terminator(0)]

    out: list[dict] = []
    first, rest = items[0], items[1:]
    out.append(
        _cmd(
            302,
            0,
            int(first.get("kind", 0)),
            int(first.get("id", 1)),
            int(first.get("price_type", 0)),
            int(first.get("price", 0)),
            bool(purchase_only),
        )
    )
    for item in rest:
        out.append(
            _cmd(
                605,
                0,
                int(item.get("kind", 0)),
                int(item.get("id", 1)),
                int(item.get("price_type", 0)),
                int(item.get("price", 0)),
            )
        )
    out.append(_terminator(0))
    return out


def build_teleport_commands(
    map_id: int,
    x: int,
    y: int,
    *,
    direction: int = 0,
    fade: int = 0,
) -> list[dict]:
    """장소 이동 commands — code 201 + 0.

    parameters: [mode, mapId, x, y, direction, fade]
        mode: 0=직접 지정, 1=변수 지정 (여기선 0 고정)
        direction: 0=유지, 2/4/6/8
        fade: 0=검정, 1=흰색, 2=없음
    """
    return [
        _cmd(201, 0, 0, int(map_id), int(x), int(y), int(direction), int(fade)),
        _terminator(0),
    ]


def build_switch_trigger_commands(
    switch_id: int,
    *,
    value: int = 0,
    end_id: int | None = None,
) -> list[dict]:
    """스위치 트리거 commands — code 121 (switch on/off) + 0.

    parameters: [startId, endId, value]
        value: 0=ON, 1=OFF
    """
    end = end_id if end_id is not None else switch_id
    return [
        _cmd(121, 0, int(switch_id), int(end), int(value)),
        _terminator(0),
    ]


def build_battle_commands(
    troop_id: int,
    *,
    can_escape: bool = True,
    can_lose: bool = False,
) -> list[dict]:
    """전투 시작 commands — code 301 + 0.

    parameters: [mode, troopId, canEscape, canLose]
        mode: 0=직접 지정, 1=변수, 2=같은 이름 적
    """
    return [
        _cmd(301, 0, 0, int(troop_id), bool(can_escape), bool(can_lose)),
        _terminator(0),
    ]


_TEMPLATE_BUILDERS = {
    "npc_talk": build_npc_talk_commands,
    "shop": build_shop_commands,
    "teleport": build_teleport_commands,
    "switch_trigger": build_switch_trigger_commands,
    "battle": build_battle_commands,
}


def build_commands_for_template(template: str, config: dict) -> list[dict]:
    """template + config → commands list. 키 누락은 기본값으로 보완."""
    t = (template or "").lower()
    cfg = dict(config or {})
    if t == "npc_talk":
        return build_npc_talk_commands(
            str(cfg.get("text", "")),
            face_name=str(cfg.get("face_name", "")),
            face_index=int(cfg.get("face_index", 0)),
            background=int(cfg.get("background", 0)),
            position=int(cfg.get("position", 2)),
        )
    if t == "shop":
        return build_shop_commands(
            list(cfg.get("items", [])),
            purchase_only=bool(cfg.get("purchase_only", False)),
        )
    if t == "teleport":
        return build_teleport_commands(
            int(cfg.get("map_id", 1)),
            int(cfg.get("x", 0)),
            int(cfg.get("y", 0)),
            direction=int(cfg.get("direction", 0)),
            fade=int(cfg.get("fade", 0)),
        )
    if t == "switch_trigger":
        return build_switch_trigger_commands(
            int(cfg.get("switch_id", 1)),
            value=int(cfg.get("value", 0)),
            end_id=cfg.get("end_id"),
        )
    if t == "battle":
        return build_battle_commands(
            int(cfg.get("troop_id", 1)),
            can_escape=bool(cfg.get("can_escape", True)),
            can_lose=bool(cfg.get("can_lose", False)),
        )
    raise ValueError(f"알 수 없는 template: {template!r}")


# ── CommonEvents CRUD ─────────────────────────────────────────────────────


def _default_common_event(event_id: int, name: str, trigger: int, commands: list[dict]) -> dict:
    """CommonEvent 엔트리 기본값."""
    return {
        "id": int(event_id),
        "list": (commands or []) + ([_terminator(0)] if not commands else []),
        "name": str(name or ""),
        "switchId": 1,
        "trigger": int(trigger),  # 0=없음, 1=자동 실행, 2=병렬 처리
    }


def _create_common_event(data_path: Path, info: dict) -> dict:
    fp = data_path / "CommonEvents.json"
    data = _load_json(fp) or [None]
    if not isinstance(data, list):
        return _err("CommonEvents.json 이 list 형태가 아님")

    # 템플릿 기반 commands 생성 옵션
    if info.get("template"):
        commands = build_commands_for_template(info["template"], info.get("config", {}))
    else:
        commands = info.get("commands") or [_terminator(0)]

    # 새 id = 배열 길이 (null 포함)
    new_id = info.get("id")
    if new_id is None:
        new_id = len(data)

    entry = _default_common_event(
        event_id=new_id,
        name=info.get("name", ""),
        trigger=int(info.get("trigger", 0)),
        commands=commands,
    )

    # 배열 길이 맞추기
    while len(data) <= new_id:
        data.append(None)
    data[new_id] = entry

    _save_json(fp, data)
    return {
        "success": True,
        "data": entry,
        "modified_files": [str(fp)],
        "entity_id": new_id,
    }


def _update_common_event(data_path: Path, info: dict) -> dict:
    fp = data_path / "CommonEvents.json"
    data = _load_json(fp)
    if not isinstance(data, list):
        return _err("CommonEvents.json 이 list 형태가 아님")

    eid = info.get("id") or info.get("common_event_id")
    if eid is None:
        return _err("update_common_event 에 id 가 없음")
    eid = int(eid)
    if not (0 < eid < len(data)):
        return _err(f"common_event id={eid} 범위 밖")
    entry = data[eid]
    if not isinstance(entry, dict):
        return _err(f"common_event id={eid} 엔트리 없음")

    updates = info.get("updates") or {}
    if "name" in updates:
        entry["name"] = str(updates["name"])
    if "trigger" in updates:
        entry["trigger"] = int(updates["trigger"])
    if "switchId" in updates:
        entry["switchId"] = int(updates["switchId"])
    if "template" in updates:
        commands = build_commands_for_template(updates["template"], updates.get("config", {}))
        entry["list"] = commands
    elif "commands" in updates:
        entry["list"] = updates["commands"]

    _save_json(fp, data)
    return {
        "success": True,
        "data": entry,
        "modified_files": [str(fp)],
        "entity_id": eid,
    }


def _delete_common_event(data_path: Path, info: dict) -> dict:
    fp = data_path / "CommonEvents.json"
    data = _load_json(fp)
    if not isinstance(data, list):
        return _err("CommonEvents.json 이 list 형태가 아님")
    eid = info.get("id")
    if eid is None:
        return _err("delete_common_event 에 id 가 없음")
    eid = int(eid)
    if not (0 < eid < len(data)):
        return _err(f"common_event id={eid} 범위 밖")
    data[eid] = None
    _save_json(fp, data)
    return {
        "success": True,
        "data": None,
        "modified_files": [str(fp)],
        "entity_id": eid,
    }


# ── Troops CRUD ──────────────────────────────────────────────────────────


def _default_troop_page() -> dict:
    return {
        "conditions": {
            "turnEnding": False,
            "turnValid": False,
            "turnA": 0,
            "turnB": 0,
            "enemyValid": False,
            "enemyIndex": 0,
            "enemyHp": 50,
            "actorValid": False,
            "actorId": 1,
            "actorHp": 50,
            "switchValid": False,
            "switchId": 1,
        },
        "list": [_terminator(0)],
        "span": 0,
    }


def _create_troop(data_path: Path, info: dict) -> dict:
    fp = data_path / "Troops.json"
    data = _load_json(fp) or [None]
    if not isinstance(data, list):
        return _err("Troops.json 이 list 형태가 아님")

    new_id = info.get("id")
    if new_id is None:
        new_id = len(data)

    members = info.get("members") or []
    pages = info.get("pages") or [_default_troop_page()]

    entry = {
        "id": int(new_id),
        "name": str(info.get("name", "")),
        "members": members,
        "pages": pages,
    }
    while len(data) <= new_id:
        data.append(None)
    data[new_id] = entry
    _save_json(fp, data)
    return {
        "success": True,
        "data": entry,
        "modified_files": [str(fp)],
        "entity_id": new_id,
    }


def _add_troop_event_command(data_path: Path, info: dict) -> dict:
    """troop 의 특정 page 에 commands 추가."""
    fp = data_path / "Troops.json"
    data = _load_json(fp)
    if not isinstance(data, list):
        return _err("Troops.json 이 list 형태가 아님")

    tid = info.get("troop_id")
    if tid is None:
        return _err("add_troop_event_command 에 troop_id 가 없음")
    tid = int(tid)
    if not (0 < tid < len(data)) or not isinstance(data[tid], dict):
        return _err(f"troop id={tid} 미존재")
    page_index = int(info.get("page_index", 0))
    pages = data[tid].setdefault("pages", [_default_troop_page()])
    while len(pages) <= page_index:
        pages.append(_default_troop_page())

    if info.get("template"):
        commands = build_commands_for_template(info["template"], info.get("config", {}))
    else:
        commands = info.get("commands") or []

    # 기존 list 의 마지막 terminator(code=0) 앞에 삽입
    plist = pages[page_index].setdefault("list", [_terminator(0)])
    if plist and plist[-1].get("code") == 0:
        plist[-1:-1] = commands
    else:
        plist.extend(commands)
        plist.append(_terminator(0))

    _save_json(fp, data)
    return {
        "success": True,
        "data": data[tid],
        "modified_files": [str(fp)],
        "entity_id": tid,
    }


# ── MapNNN events CRUD ───────────────────────────────────────────────────


def _default_map_event_page(commands: list[dict] | None, image: dict | None = None) -> dict:
    return {
        "conditions": {
            "actorId": 1,
            "actorValid": False,
            "itemId": 1,
            "itemValid": False,
            "selfSwitchCh": "A",
            "selfSwitchValid": False,
            "switch1Id": 1,
            "switch1Valid": False,
            "switch2Id": 1,
            "switch2Valid": False,
            "variableId": 1,
            "variableValid": False,
            "variableValue": 0,
        },
        "directionFix": False,
        "image": image
        or {
            "characterIndex": 0,
            "characterName": "",
            "direction": 2,
            "pattern": 0,
            "tileId": 0,
        },
        "list": (commands or []) + ([_terminator(0)] if not commands else []),
        "moveFrequency": 3,
        "moveRoute": {"repeat": False, "skippable": False, "wait": False, "list": []},
        "moveSpeed": 3,
        "moveType": 0,
        "priorityType": 0,
        "stepAnime": False,
        "through": False,
        "trigger": 0,
        "walkAnime": True,
    }


def _create_map_event(data_path: Path, map_id: int, info: dict) -> dict:
    """Map 파일의 events dict 에 새 이벤트 삽입."""
    fp = data_path / f"Map{map_id:03d}.json"
    map_data = _load_json(fp)
    if not isinstance(map_data, dict):
        return _err(f"Map{map_id:03d}.json 이 dict 형태가 아님")
    events = map_data.setdefault("events", [None])
    if not isinstance(events, list):
        return _err(f"Map{map_id:03d}.json 의 events 가 list 가 아님")

    new_id = info.get("id")
    if new_id is None:
        new_id = len(events)
    new_id = int(new_id)

    if info.get("template"):
        commands = build_commands_for_template(info["template"], info.get("config", {}))
    else:
        commands = info.get("commands") or [_terminator(0)]

    page = _default_map_event_page(commands, info.get("image"))
    entry = {
        "id": new_id,
        "name": str(info.get("name", f"EV{new_id:03d}")),
        "note": str(info.get("note", "")),
        "pages": [page],
        "x": int(info.get("x", 0)),
        "y": int(info.get("y", 0)),
    }
    while len(events) <= new_id:
        events.append(None)
    events[new_id] = entry

    _save_json(fp, map_data)
    return {
        "success": True,
        "data": entry,
        "modified_files": [str(fp)],
        "entity_id": new_id,
    }


def _update_map_event(data_path: Path, map_id: int, info: dict) -> dict:
    fp = data_path / f"Map{map_id:03d}.json"
    map_data = _load_json(fp)
    if not isinstance(map_data, dict):
        return _err(f"Map{map_id:03d}.json 이 dict 형태가 아님")
    events = map_data.get("events", [])
    if not isinstance(events, list):
        return _err(f"Map{map_id:03d}.json 의 events 가 list 가 아님")

    eid = info.get("id") or info.get("event_id")
    if eid is None:
        return _err("update_map_event 에 id 가 없음")
    eid = int(eid)
    if not (0 < eid < len(events)) or not isinstance(events[eid], dict):
        return _err(f"Map{map_id:03d} event id={eid} 미존재")
    entry = events[eid]
    updates = info.get("updates") or {}
    for k in ("name", "note", "x", "y"):
        if k in updates:
            entry[k] = updates[k]
    if "template" in updates:
        commands = build_commands_for_template(updates["template"], updates.get("config", {}))
        if entry.get("pages"):
            entry["pages"][0]["list"] = commands
    _save_json(fp, map_data)
    return {
        "success": True,
        "data": entry,
        "modified_files": [str(fp)],
        "entity_id": eid,
    }


def _add_event_command(data_path: Path, map_id: int, info: dict) -> dict:
    """MapNNN 의 특정 event 의 page list 에 commands 추가."""
    fp = data_path / f"Map{map_id:03d}.json"
    map_data = _load_json(fp)
    if not isinstance(map_data, dict):
        return _err(f"Map{map_id:03d}.json 이 dict 형태가 아님")
    events = map_data.get("events", [])
    if not isinstance(events, list):
        return _err(f"Map{map_id:03d}.json 의 events 가 list 가 아님")

    eid = info.get("event_id") or info.get("id")
    if eid is None:
        return _err("add_event_command 에 event_id 가 없음")
    eid = int(eid)
    if not (0 < eid < len(events)) or not isinstance(events[eid], dict):
        return _err(f"Map{map_id:03d} event id={eid} 미존재")
    page_index = int(info.get("page_index", 0))
    pages = events[eid].setdefault("pages", [_default_map_event_page(None)])
    while len(pages) <= page_index:
        pages.append(_default_map_event_page(None))

    if info.get("template"):
        commands = build_commands_for_template(info["template"], info.get("config", {}))
    else:
        commands = info.get("commands") or []

    plist = pages[page_index].setdefault("list", [_terminator(0)])
    if plist and plist[-1].get("code") == 0:
        plist[-1:-1] = commands
    else:
        plist.extend(commands)
        plist.append(_terminator(0))

    _save_json(fp, map_data)
    return {
        "success": True,
        "data": events[eid],
        "modified_files": [str(fp)],
        "entity_id": eid,
    }


def _create_event_from_template(data_path: Path, map_id: int, info: dict) -> dict:
    """5 base case 엔트리포인트 — template 을 받아 해당 Map 에 이벤트 생성."""
    return _create_map_event(data_path, map_id, info)


# ── util ─────────────────────────────────────────────────────────────────


def _load_json(fp: Path) -> Any:
    if not fp.exists():
        raise FileNotFoundError(fp)
    return json.loads(fp.read_text(encoding="utf-8"))


def _save_json(fp: Path, data: Any) -> None:
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _err(msg: str) -> dict:
    return {
        "success": False,
        "data": None,
        "modified_files": [],
        "error": msg,
        "entity_id": None,
    }
