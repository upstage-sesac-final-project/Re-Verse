"""맵 생성/복제 연산."""

import copy
from typing import Any

from agent.map_editor.loader import (
    load_map,
    load_map_infos,
    next_map_id,
    save_map,
    save_map_infos,
)
from agent.map_editor.tile_ops import THEME_TILESET, fill_map_layer

_DEFAULT_MAP_INFO: dict[str, Any] = {
    "expanded": False,
    "name": "New Map",
    "order": 0,
    "parentId": 0,
    "scrollX": 0,
    "scrollY": 0,
}


def _make_blank_map(width: int, height: int, tileset_id: int = 1) -> dict[str, Any]:
    """빈 RPG Maker MZ 맵 데이터를 생성한다. 레이어 6개 = data 길이 6*w*h."""
    size = width * height * 6
    return {
        "autoplayBgm": False,
        "autoplayBgs": False,
        "battleback1Name": "",
        "battleback2Name": "",
        "bgm": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
        "bgs": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
        "data": [0] * size,
        "disableDashing": False,
        "displayName": "",
        "encounterList": [],
        "encounterStep": 30,
        "events": [None],
        "height": height,
        "note": "",
        "parallaxLoopX": False,
        "parallaxLoopY": False,
        "parallaxName": "",
        "parallaxShow": False,
        "parallaxSx": 0,
        "parallaxSy": 0,
        "scrollType": 0,
        "specifyBattleback": False,
        "tilesetId": tileset_id,
        "width": width,
    }


def create_map(game_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """새 맵을 생성하고 MapInfos에 등록한다.

    params:
        name (str): 맵 이름 (기본: "New Map")
        width (int): 맵 너비 (기본: 17)
        height (int): 맵 높이 (기본: 13)
        theme (str): "field"|"town"|"dungeon"|"indoor"|"desert" — 레이어 0을 테마 타일로 채움
        tileset_id (int): 타일셋 ID (theme 지정 시 자동 설정, 기본: 1)
        base_tile_id (int): 레이어 0 채울 타일 ID 직접 지정 (theme보다 우선)
        parent_id (int): 부모 맵 ID (기본: 0)

    반환: {"map_id": int, "name": str, "theme": str | None}
    """
    name = params.get("name", "New Map")
    width = params.get("width", 17)
    height = params.get("height", 13)
    parent_id = params.get("parent_id", 0)
    theme = params.get("theme")

    # tileset_id: 직접 지정 > theme 자동 > 기본값 1
    tileset_id = params.get("tileset_id")
    if tileset_id is None:
        tileset_id = THEME_TILESET.get(theme, 1) if theme else 1

    map_id = next_map_id(game_id)
    map_data = _make_blank_map(width, height, tileset_id)
    map_data["displayName"] = name

    # 레이어 0 채우기 (theme 또는 base_tile_id 지정 시)
    base_tile_id = params.get("base_tile_id")
    if theme or base_tile_id is not None:
        fill_map_layer(map_data, {"layer": 0, "theme": theme, "tile_id": base_tile_id})

    save_map(game_id, map_id, map_data)

    # MapInfos 등록
    try:
        infos = load_map_infos(game_id)
    except FileNotFoundError:
        infos = [None]

    entry: dict[str, Any] = {
        "id": map_id,
        "expanded": False,
        "name": name,
        "order": map_id,
        "parentId": parent_id,
        "scrollX": 0,
        "scrollY": 0,
    }

    # 인덱스 맞추기 (map_id = 배열 인덱스)
    while len(infos) <= map_id:
        infos.append(None)
    infos[map_id] = entry
    save_map_infos(game_id, infos)

    return {"map_id": map_id, "name": name, "theme": theme}


def duplicate_map(game_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """기존 맵을 복제해 새 맵을 생성한다.

    params:
        source_map_id (int): 복제 원본 맵 ID
        name (str, 선택): 새 맵 이름 (기본: 원본 이름 + " (복사)")

    반환: {"map_id": int, "name": str, "source_map_id": int}
    """
    source_id = params["source_map_id"]
    source_data = load_map(game_id, source_id)

    new_id = next_map_id(game_id)
    new_data = copy.deepcopy(source_data)

    # 이벤트 ID 보정 (events[0] = None 관례)
    if "events" in new_data:
        for ev in new_data["events"]:
            if ev is not None:
                ev["id"] = new_data["events"].index(ev)

    default_name = (source_data.get("displayName") or f"Map{source_id:03d}") + " (복사)"
    name = params.get("name", default_name)
    new_data["displayName"] = name

    save_map(game_id, new_id, new_data)

    # MapInfos 등록
    try:
        infos = load_map_infos(game_id)
    except FileNotFoundError:
        infos = [None]

    # 원본 info 복사
    source_info: dict[str, Any] = {}
    if source_id < len(infos) and infos[source_id]:
        source_info = copy.deepcopy(infos[source_id])

    entry: dict[str, Any] = {
        **source_info,
        "id": new_id,
        "name": name,
        "order": new_id,
    }

    while len(infos) <= new_id:
        infos.append(None)
    infos[new_id] = entry
    save_map_infos(game_id, infos)

    return {"map_id": new_id, "name": name, "source_map_id": source_id}
