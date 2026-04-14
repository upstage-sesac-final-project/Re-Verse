"""D+E 대체 노드 — sample_map_selector.

사용자 쿼리로 샘플맵을 고르고 실제 MapXXX.json을 읽어 state에 주입한다.
algorithmic 생성(D+E)을 건너뛰고 바로 integrator로 연결된다.

- tile 데이터는 원본 MapXXX.json의 "data" 배열을 그대로 사용.
- 원본 맵의 events도 그대로 유지 → integrator에서 ID 번역됨.
- connection_info는 비워둠 (이벤트 담당 범위 밖).
"""

import json
import logging
from pathlib import Path
from typing import Any

from agent.generation.mapgen.sample_selector import select_maps
from agent.generation.mapgen.tile_checker import find_nearest_safe_coord
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState
from app.backend.core.config import settings

logger = logging.getLogger(__name__)

_SAMPLEMAPS_DIR = Path(settings.BASE_GAME_PATH) / "samplemaps"
_METADATA_PATH = Path(__file__).parents[2] / "generation" / "mapgen" / "data" / "map_metadata.json"
_BASE_TILESETS_PATH = Path(settings.BASE_GAME_PATH) / "data" / "Tilesets.json"


def _load_metadata_index() -> dict[str, dict[str, Any]]:
    if not _METADATA_PATH.exists():
        logger.warning("map_metadata.json 없음: %s", _METADATA_PATH)
        return {}
    raw = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
    return {e["file_name"]: e for e in raw}


def _load_tileset_flags() -> dict[int, list[int]]:
    """base_game Tilesets.json에서 tileset_id → flags 매핑 로드."""
    if not _BASE_TILESETS_PATH.exists():
        logger.warning("Tilesets.json 없음: %s", _BASE_TILESETS_PATH)
        return {}
    try:
        tilesets = json.loads(_BASE_TILESETS_PATH.read_text(encoding="utf-8"))
        # Tilesets.json은 배열이며 각 요소는 {"id": int, "flags": [...]} 구조
        return {
            ts["id"]: ts.get("flags", [])
            for ts in tilesets
            if ts and isinstance(ts, dict) and "id" in ts
        }
    except Exception:
        logger.exception("Tilesets.json 로드 실패")
        return {}


async def sample_map_selector(state: GenerationState) -> dict:
    """사용자 쿼리 → 샘플맵 N개를 골라 state에 주입."""
    gen_id = state["generation_id"]
    user_input = state["user_input"]

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "sample_map_select",
            "progress": 55,
            "message": "샘플맵 선택 중...",
        },
    )

    # 1. 맵 개수 결정 (기획서 우선, 없으면 플레이타임 기반)
    game_spec = state.get("game_spec")
    if game_spec and game_spec.maps:
        n_maps = len(game_spec.maps)
        logger.info("기획서 기반 맵 개수 설정: n_maps=%d", n_maps)
    elif game_spec and hasattr(game_spec, "playtime_minutes"):
        pt = getattr(game_spec, "playtime_minutes", 10)
        n_maps = max(2, pt * 3 // 5)
        logger.info("playtime %d분 → n_maps=%d (기획서 미존재 시 계산)", pt, n_maps)
    else:
        n_maps = 3
        logger.info("기본 맵 개수 설정: n_maps=3")

    # 2. 벡터 DB 검색
    result = await select_maps(user_input, n_maps=n_maps)
    file_names = result["chosen"]
    ranked_candidates = result["candidates"]
    logger.info(
        "sample_map_selector: 선택된 맵 %s, 후보군 %d개", file_names, len(ranked_candidates)
    )

    metadata_index = _load_metadata_index()
    tileset_flags_map = _load_tileset_flags()

    # tile_checker 호환을 위해 list[dict] 형태로 변환 (flags만 포함)
    max_tid = max(tileset_flags_map.keys(), default=0)
    tilesets_list: list[Any] = [None] * (max_tid + 1)
    for tid, flags in tileset_flags_map.items():
        tilesets_list[tid] = {"flags": flags}

    map_specs: list[MapSpec] = []
    map_tiles: dict[int, list[int]] = {}
    compiled_events: dict[int, list[dict]] = {}
    connection_info: dict[int, MapConnectionInfo] = {}

    # 3. 각 맵 로드 및 Spec 생성
    for idx, fname in enumerate(file_names, start=1):
        path = _SAMPLEMAPS_DIR / fname
        if not path.exists():
            logger.error("샘플맵 파일 없음: %s", path)
            continue

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            meta = metadata_index.get(fname, {})

            # 메타데이터 정보 추출
            display_name = meta.get("display_name", fname)
            map_type = meta.get("map_type", "town")
            width = raw.get("width", 20)
            height = raw.get("height", 20)
            tileset_id = raw.get("tilesetId", 1)
            bgm_name = raw.get("bgm", {}).get("name", "")
            tags = meta.get("tags", [])

            # Tilesets.json flags 기반 안전한 시작 좌표 계산 (플레이어 스폰 포인트)
            tile_data = raw.get("data", [])
            if tile_data and tilesets_list:
                cx, cy = width // 2, height // 2
                spawn = find_nearest_safe_coord(
                    tile_data, cx, cy, width, height, tileset_id, tilesets_list
                )
            else:
                spawn = (width // 2, height // 2)

            spec = MapSpec(
                map_id=idx,
                name=display_name,
                map_type=map_type,  # type: ignore[arg-type]
                width=width,
                height=height,
                tileset_id=tileset_id,
                bgm=bgm_name,
                atmosphere=", ".join(tags) if tags else meta.get("description", ""),
                landmarks=[],
                exits=[],
                spawn_point=spawn,
                original_file_name=fname,
            )
            map_specs.append(spec)
            map_tiles[idx] = tile_data

            # 4. 이벤트 로드 (events[0]은 RPG Maker MZ 규칙상 null → 제거)
            raw_events = raw.get("events") or []
            events_list = [e for e in raw_events if e]
            compiled_events[idx] = events_list

            # 5. 연결 정보 초기화 (샘플맵은 기본적으로 내부 연결이 없으므로 빈 값)
            connection_info[idx] = MapConnectionInfo(
                map_id=idx,
                exit_tiles=[],
                entry_tiles=[{"from_spawn": True, "x": spawn[0], "y": spawn[1]}],
            )

        except Exception:
            logger.exception("샘플맵 로드 실패: %s", fname)

    logger.info(
        "sample_map_selector 완료: %d개 맵 로드 (tiles %d)",
        len(map_specs),
        sum(len(v) for v in map_tiles.values()),
    )

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "sample_map_select",
            "summary": f"{len(map_specs)}개 샘플맵 선택: {', '.join(m.name for m in map_specs)}",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("sample_map_select")

    return {
        "map_specs": map_specs,
        "map_tiles": map_tiles,
        "compiled_events": compiled_events,
        "connection_info": connection_info,
        "ranked_map_candidates": ranked_candidates,
        "completed_phases": completed,
    }
