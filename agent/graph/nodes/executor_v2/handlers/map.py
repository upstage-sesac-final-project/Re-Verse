"""Map handler — L1 메타데이터 작업 + L4 content stub.

MVP scope:
  L1: MapInfos.json 메타데이터 (이름, 부모, 생성, 삭제)
  L4: 타일맵 content 생성 — 팀의 타일/이벤트 배치 작업 완료 후 접합

Map00x.json 의 구조:
  autoplayBgm, bgm, bgs, height, width, data(tile 배열), events, encounterList, ...
MapInfos.json 의 구조:
  [null, {"id":1, "name":"MAP001", "parentId":0, "order":1, ...}, ...]
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from agent.generation.mapgen.tile_checker import (
    find_nearest_safe_coord,
    get_all_safe_coords,
    get_reachable_coords,
)
from app.backend.core.config import settings

logger = logging.getLogger(__name__)

_SAMPLEMAPS_DIR = Path(settings.BASE_GAME_PATH) / "samplemaps"
_TILESETS_PATH = Path(settings.BASE_GAME_PATH) / "data" / "Tilesets.json"


def _load_tilesets() -> list | None:
    """base_game의 Tilesets.json을 로드해 list 형태로 반환한다."""
    try:
        raw = json.loads(_TILESETS_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return None
        max_id = max(
            (ts["id"] for ts in raw if ts and isinstance(ts, dict) and "id" in ts), default=0
        )
        result: list = [None] * (max_id + 1)
        for ts in raw:
            if ts and isinstance(ts, dict) and "id" in ts:
                result[ts["id"]] = ts
        return result
    except Exception as e:
        logger.warning("[map] Tilesets.json 로드 실패: %s", e)
        return None


def execute_map_step(
    data_path: Path,
    action: str,
    target_file: str,
    target_info: dict[str, Any],
) -> dict[str, Any]:
    """Map 관련 step 실행.

    target_file: "MapInfos.json" | "Map00x.json" | "Map"(가상)
    """
    action = action.strip().lower()

    # L1 metadata 작업 라우팅
    if action == "create_map":
        return _create_map(data_path, target_info)
    if action == "rename_map":
        return _rename_map(data_path, target_info)
    if action == "delete_map":
        return _delete_map(data_path, target_info)
    if action == "reparent_map":
        return _reparent_map(data_path, target_info)
    if action in ("get_map_info", "get"):
        return _get_map_info(data_path, target_info)
    if action == "list_maps":
        return _list_maps(data_path)

    # L4 stub
    if action in ("edit_tiles", "place_event", "edit_encounters"):
        return content_ops(data_path, action, target_info)

    return _fail(f"Map handler: 지원하지 않는 action '{action}'")


# ──────────────────────────────────────────────
# L1 metadata_ops 구현
# ──────────────────────────────────────────────


def _load_map_infos(data_path: Path) -> list:
    fp = data_path / "MapInfos.json"
    return json.loads(fp.read_text(encoding="utf-8"))


def _save_map_infos(data_path: Path, data: list) -> None:
    fp = data_path / "MapInfos.json"
    fp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _create_map(data_path: Path, info: dict) -> dict[str, Any]:
    """빈 맵 생성 또는 샘플맵 복제. MapInfos + Map00x.json 파일 생성.
    생성 후 기존 맵(parentId 또는 Map 1)과 양방향 워프를 생성한다.
    """
    infos = _load_map_infos(data_path)
    max_id = max(
        (e.get("id", 0) for e in infos if isinstance(e, dict)),
        default=0,
    )
    new_id = max_id + 1
    name = info.get("name", f"Map{new_id:03d}")
    parent_id = info.get("parentId", 0)
    original_file_name = info.get("original_file_name")

    new_entry = {
        "id": new_id,
        "expanded": False,
        "name": name,
        "order": new_id,
        "parentId": parent_id,
        "scrollX": 0,
        "scrollY": 0,
        "quick": False,
    }

    # MapInfos.json 에 추가
    while len(infos) <= new_id:
        infos.append(None)
    infos[new_id] = new_entry
    _save_map_infos(data_path, infos)

    # Map 파일 생성
    map_file = f"Map{new_id:03d}.json"
    map_fp = data_path / map_file
    modified_files = ["MapInfos.json", map_file]

    if original_file_name:
        # 샘플맵 복제
        src_path = _SAMPLEMAPS_DIR / original_file_name
        if src_path.exists():
            try:
                # 파일 복사
                shutil.copy2(src_path, map_fp)
                # 복사된 파일의 displayName 수정
                map_data = json.loads(map_fp.read_text(encoding="utf-8"))
                map_data["displayName"] = name
                map_fp.write_text(
                    json.dumps(map_data, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                logger.info("[map] cloned sample map '%s' to id=%d", original_file_name, new_id)
            except Exception as e:
                logger.error("[map] sample map clone failed: %s", e)
                return _fail(f"샘플맵 복제 실패: {e}")
        else:
            logger.warning("[map] sample map not found: %s", src_path)
            return _fail(f"샘플맵 파일을 찾을 수 없습니다: {original_file_name}")
    else:
        # 빈 Map 파일 생성
        empty_map = {
            "autoplayBgm": False,
            "autoplayBgs": False,
            "battleback1Name": "",
            "battleback2Name": "",
            "bgm": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
            "bgs": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
            "disableDashing": False,
            "displayName": name,
            "encounterList": [],
            "encounterStep": 30,
            "height": 13,
            "note": "",
            "parallaxLoopX": False,
            "parallaxLoopY": False,
            "parallaxName": "",
            "parallaxShow": True,
            "parallaxSx": 0,
            "parallaxSy": 0,
            "scrollType": 0,
            "specifyBattleback": False,
            "tilesetId": 1,
            "width": 17,
            "data": [0] * (17 * 13 * 6),  # 6 layers
            "events": [None],
        }
        map_fp.write_text(
            json.dumps(empty_map, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        logger.info("[map] create empty map id=%d name='%s'", new_id, name)

    # ── 양방향 워프 생성 ──
    # 연결 대상 결정 (parentId가 있으면 우선, 없으면 Map 1)
    source_map_id = parent_id if parent_id > 0 else 1
    if source_map_id != new_id:
        source_map_file = f"Map{source_map_id:03d}.json"
        if (data_path / source_map_file).exists():
            try:
                tilesets = _load_tilesets()
                # 새 맵 도착 좌표: 통행 가능한 빈 자리 탐색
                new_map_spawn = _find_spawn_in_map(data_path, new_id, tilesets)
                # 기존 맵 도착 좌표: 통행 가능한 빈 자리 탐색
                src_map_spawn = _find_spawn_in_map(data_path, source_map_id, tilesets)

                # 1. 기존 맵 -> 새 맵 워프
                _add_warp_event_to_map_file(
                    data_path,
                    source_map_id,
                    new_id,
                    to_x=new_map_spawn[0],
                    to_y=new_map_spawn[1],
                    event_name=f"To {name}",
                )
                if source_map_file not in modified_files:
                    modified_files.append(source_map_file)

                # 2. 새 맵 -> 기존 맵 워프
                _add_warp_event_to_map_file(
                    data_path,
                    new_id,
                    source_map_id,
                    to_x=src_map_spawn[0],
                    to_y=src_map_spawn[1],
                    event_name=f"Back to Map{source_map_id:03d}",
                )
                logger.info(
                    "[map] bidirectional warp: Map%d↔Map%d (src_spawn=%s, new_spawn=%s)",
                    source_map_id,
                    new_id,
                    src_map_spawn,
                    new_map_spawn,
                )
            except Exception as warp_err:
                logger.warning("[map] 워프 생성 실패 (맵은 생성됨): %s", warp_err, exc_info=True)

    return _ok(new_entry, modified_files, entity_id=new_id)


def _find_spawn_in_map(
    data_path: Path, map_id: int, tilesets: list | None = None
) -> tuple[int, int]:
    """맵에서 통행 가능하고 이벤트가 없는 좌표를 반환한다.

    Tilesets.json flags 비트 연산 기반 `find_nearest_safe_coord`를 사용하며,
    고립되지 않은(가장 큰 도달 가능 영역) 구역을 우선순위로 둡니다.
    """
    fp = data_path / f"Map{map_id:03d}.json"
    if not fp.exists():
        return (1, 1)
    try:
        map_data = json.loads(fp.read_text(encoding="utf-8"))
        width = map_data.get("width", 17)
        height = map_data.get("height", 13)
        tile_data = map_data.get("data") or []
        tileset_id = map_data.get("tilesetId", 1)
        events = map_data.get("events") or []

        # 이미 이벤트가 점유한 좌표
        used_coords: set[tuple[int, int]] = {
            (e["x"], e["y"]) for e in events if e and isinstance(e, dict) and "x" in e and "y" in e
        }

        if tilesets is None:
            tilesets = _load_tilesets()

        # 1. 모든 안전한 좌표 가져오기
        all_safe = get_all_safe_coords(
            tile_data, width, height, tileset_id, tilesets, used_coords=used_coords
        )

        if not all_safe:
            # 안전한 타일이 하나도 없다면 (벽으로 가득 찬 맵 등)
            # 중앙 근처의 빈 자리를 찾거나 최악의 경우 (1,1)
            cx, cy = width // 2, height // 2
            return (cx, cy)

        # 2. 도달 가능한 영역 그룹화 (고립 지역 방지)
        visited = set()
        regions = []
        for sx, sy in all_safe:
            if (sx, sy) not in visited:
                region = get_reachable_coords(
                    tile_data, sx, sy, width, height, tileset_id, tilesets, used_coords=used_coords
                )
                regions.append(region)
                for rx, ry in region:
                    visited.add((rx, ry))

        # 가장 큰 영역 선택
        if regions:
            best_region = max(regions, key=len)
            # 그 영역 내에서 중앙에 가장 가까운 좌표 선택
            cx, cy = width // 2, height // 2
            best_coord = min(best_region, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
            return best_coord

        # 폴백: 중앙에서 BFS
        cx, cy = max(1, width // 2), max(1, height // 2)
        return find_nearest_safe_coord(
            tile_data,
            cx,
            cy,
            width,
            height,
            tileset_id,
            tilesets,
            used_coords=used_coords,
        )
    except Exception as e:
        logger.warning("[map] spawn 좌표 탐색 실패 (Map%03d): %s", map_id, e)
        return (1, 1)


def _add_warp_event_to_map_file(
    data_path: Path,
    map_id: int,
    to_map_id: int,
    to_x: int,
    to_y: int,
    x: int | None = None,
    y: int | None = None,
    event_name: str = "Warp",
) -> None:
    """특정 맵 파일에 워프 이벤트를 추가한다."""
    map_file = f"Map{map_id:03d}.json"
    fp = data_path / map_file
    if not fp.exists():
        logger.warning("[map] 워프 대상 파일 없음: %s", fp)
        return

    map_data = json.loads(fp.read_text(encoding="utf-8"))
    events = map_data.get("events") or [None]
    if not isinstance(events, list):
        events = [None]

    # 배치 좌표 결정 (미지정 시 통행 가능한 빈 자리 탐색)
    if x is None or y is None:
        tilesets = _load_tilesets()
        x, y = _find_spawn_in_map(data_path, map_id, tilesets)

    # 빈 슬롯(None)이 있으면 재사용, 없으면 append
    new_event_id = len(events)
    for i, e in enumerate(events):
        if i > 0 and e is None:
            new_event_id = i
            break

    warp_event = _create_warp_event_json(new_event_id, to_map_id, to_x, to_y, x, y, event_name)

    if new_event_id < len(events):
        events[new_event_id] = warp_event
    else:
        events.append(warp_event)

    map_data["events"] = events
    fp.write_text(json.dumps(map_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    logger.info(
        "[map] warp event 추가: Map%d id=%d pos=(%d,%d) → Map%d (%d,%d)",
        map_id,
        new_event_id,
        x,
        y,
        to_map_id,
        to_x,
        to_y,
    )


def _create_warp_event_json(
    event_id: int,
    to_map_id: int,
    to_x: int,
    to_y: int,
    x: int,
    y: int,
    name: str,
) -> dict[str, Any]:
    """RPG Maker MZ 표준 워프 이벤트 JSON 생성."""
    return {
        "id": event_id,
        "name": name,
        "note": "",
        "pages": [
            {
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
                "image": {
                    "tileId": 0,
                    "characterName": "!Crystal",
                    "direction": 2,
                    "pattern": 0,
                    "characterIndex": 5,
                },
                "list": [
                    {"code": 201, "indent": 0, "parameters": [0, to_map_id, to_x, to_y, 0, 0]},
                    {"code": 0, "indent": 0, "parameters": []},
                ],
                "moveFrequency": 3,
                "moveRoute": {
                    "list": [{"code": 0, "parameters": []}],
                    "repeat": True,
                    "skippable": False,
                    "wait": False,
                },
                "moveSpeed": 3,
                "moveType": 0,
                "priorityType": 1,
                "stepAnime": False,
                "through": False,
                "trigger": 1,
                "walkAnime": True,
            }
        ],
        "x": x,
        "y": y,
    }


def _rename_map(data_path: Path, info: dict) -> dict[str, Any]:
    map_id = info.get("map_id") or info.get("id")
    new_name = info.get("name", "")
    if map_id is None or not new_name:
        return _fail("rename_map: map_id 와 name 필요")
    map_id = int(map_id)
    infos = _load_map_infos(data_path)
    if map_id >= len(infos) or not isinstance(infos[map_id], dict):
        return _fail(f"MapInfos: id={map_id} 없음")
    infos[map_id]["name"] = new_name
    _save_map_infos(data_path, infos)
    logger.info("[map] rename map id=%d → '%s'", map_id, new_name)
    return _ok(infos[map_id], ["MapInfos.json"], entity_id=map_id)


def _delete_map(data_path: Path, info: dict) -> dict[str, Any]:
    map_id = info.get("map_id") or info.get("id")
    if map_id is None:
        return _fail("delete_map: map_id 필요")
    map_id = int(map_id)
    infos = _load_map_infos(data_path)
    if map_id >= len(infos) or not isinstance(infos[map_id], dict):
        return _fail(f"MapInfos: id={map_id} 없음")
    infos[map_id] = None
    _save_map_infos(data_path, infos)
    # Map 파일도 삭제
    map_file = data_path / f"Map{map_id:03d}.json"
    modified = ["MapInfos.json"]
    if map_file.exists():
        map_file.unlink()
        modified.append(map_file.name)
    logger.info("[map] delete map id=%d", map_id)
    return _ok({"deleted_id": map_id}, modified, entity_id=map_id)


def _reparent_map(data_path: Path, info: dict) -> dict[str, Any]:
    map_id = info.get("map_id") or info.get("id")
    new_parent = info.get("parentId", 0)
    if map_id is None:
        return _fail("reparent_map: map_id 필요")
    map_id = int(map_id)
    infos = _load_map_infos(data_path)
    if map_id >= len(infos) or not isinstance(infos[map_id], dict):
        return _fail(f"MapInfos: id={map_id} 없음")
    infos[map_id]["parentId"] = int(new_parent)
    _save_map_infos(data_path, infos)
    return _ok(infos[map_id], ["MapInfos.json"], entity_id=map_id)


def _get_map_info(data_path: Path, info: dict) -> dict[str, Any]:
    map_id = info.get("map_id") or info.get("id")
    if map_id is None:
        return _fail("get_map_info: map_id 필요")
    map_id = int(map_id)
    infos = _load_map_infos(data_path)
    if map_id >= len(infos) or not isinstance(infos[map_id], dict):
        return _fail(f"MapInfos: id={map_id} 없음")
    return {
        "success": True,
        "data": infos[map_id],
        "modified_files": [],
        "error": None,
        "exists": True,
        "entity_id": map_id,
    }


def _list_maps(data_path: Path) -> dict[str, Any]:
    infos = _load_map_infos(data_path)
    maps = [e for e in infos if isinstance(e, dict)]
    return {
        "success": True,
        "data": maps,
        "modified_files": [],
        "error": None,
        "exists": len(maps) > 0,
    }


# ──────────────────────────────────────────────
# L4 content_ops stub
# ──────────────────────────────────────────────


def content_ops(
    data_path: Path,
    action: str,
    target_info: dict[str, Any],
) -> dict[str, Any]:
    """L4 타일맵/이벤트/인카운터 편집.

    현재는 stub — 팀의 초기 게임 생성 타일셋 배치 작업 완료 후 구현.
    """
    raise NotImplementedError(
        f"Map content_ops (L4) 는 아직 구현되지 않았습니다. action='{action}'"
    )


# ──────────────────────────────────────────────
# 공통 util
# ──────────────────────────────────────────────


def _ok(data: Any, modified_files: list[str], *, entity_id: int | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "modified_files": modified_files,
        "error": None,
        "entity_id": entity_id,
    }


def _fail(error: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "modified_files": [],
        "error": error,
        "entity_id": None,
    }
