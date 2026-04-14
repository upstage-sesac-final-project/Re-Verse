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

from app.backend.core.config import settings

logger = logging.getLogger(__name__)

_SAMPLEMAPS_DIR = Path(settings.BASE_GAME_PATH) / "samplemaps"


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
    """빈 맵 생성 또는 샘플맵 복제. MapInfos + Map00x.json 파일 생성."""
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

    if original_file_name:
        # 샘플맵 복제
        src_path = _SAMPLEMAPS_DIR / original_file_name
        if src_path.exists():
            try:
                # 파일 복사
                shutil.copy2(src_path, map_fp)
                # 복사된 파일의 displayName 수정 (선택 사항)
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
            # 폴백: 빈 맵 생성 (또는 에러 반환)
            return _fail(f"샘플맵 파일을 찾을 수 없습니다: {original_file_name}")
    else:
        # 빈 Map 파일 생성 (기존 로직)
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

    return _ok(new_entry, ["MapInfos.json", map_file], entity_id=new_id)


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
