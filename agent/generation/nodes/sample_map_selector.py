"""D+E 대체 노드 — sample_map_selector.

사용자 쿼리로 샘플맵을 고르고 실제 MapXXX.json을 읽어 state에 주입한다.
algorithmic 생성(D+E)을 건너뛰고 바로 integrator로 연결된다.

- tile 데이터는 원본 MapXXX.json의 "data" 배열을 그대로 사용.
- 원본 맵의 events도 그대로 유지 → integrator에서 ID 번역됨.
- connection_info는 비워둠 (이벤트 담당 범위 밖).
"""

import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

from agent.generation.mapgen.sample_selector import select_maps
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_SAMPLEMAPS_DIR = Path(__file__).parents[3] / "storage" / "games" / "base_game" / "samplemaps"
_METADATA_PATH = Path(__file__).parents[2] / "generation" / "mapgen" / "data" / "map_metadata.json"
_BASE_TILESETS_PATH = (
    Path(__file__).parents[3] / "storage" / "games" / "base_game" / "data" / "Tilesets.json"
)


_MAP_TYPE_BY_TILESET = {
    1: "field",  # 월드맵
    2: "town",  # 자연/야외 (마을 다수)
    3: "town",  # 건물 실내
    4: "dungeon",  # 던전/지하
    5: "town",  # 현대 야외
    6: "town",  # SF/현대 실내
}

# RPG Maker MZ flag bits
_FLAG_PASSABLE_MASK = 0x0F  # bits 0-3: 방향별 통행 (0=가능, 1=불가)
_FLAG_DAMAGE_FLOOR = 0x0100  # bit 8: 데미지 바닥


def _load_metadata_index() -> dict[str, dict[str, Any]]:
    raw = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
    return {e["file_name"]: e for e in raw}


def _load_tileset_flags() -> dict[int, list[int]]:
    """base_game Tilesets.json에서 tileset_id → flags 매핑 로드."""
    if not _BASE_TILESETS_PATH.exists():
        logger.warning("Tilesets.json 없음: %s", _BASE_TILESETS_PATH)
        return {}
    try:
        tilesets = json.loads(_BASE_TILESETS_PATH.read_text(encoding="utf-8"))
        return {
            ts["id"]: ts.get("flags", [])
            for ts in tilesets
            if ts and isinstance(ts, dict) and "id" in ts
        }
    except Exception:
        logger.exception("Tilesets.json 로드 실패")
        return {}


def _find_safe_spawn(
    tile_data: list[int],
    width: int,
    height: int,
    flags: list[int],
) -> tuple[int, int]:
    """Tilesets.json flags 기반 BFS로 안전한 시작 좌표를 찾는다.

    중앙에서 출발해 통행 가능 + 데미지 아닌 첫 번째 타일 반환.
    """
    cx, cy = width // 2, height // 2

    def is_safe(x: int, y: int) -> bool:
        # 레이어 0~3 검사: 어느 레이어든 불통과 or 데미지면 unsafe
        for layer in range(4):
            idx = layer * width * height + y * width + x
            if idx >= len(tile_data):
                return False
            tile_id = tile_data[idx]
            if tile_id == 0:
                continue  # 빈 타일 (투과)
            if tile_id >= len(flags):
                continue  # 플래그 범위 밖 → 안전하다고 가정
            f = flags[tile_id]
            if f & _FLAG_DAMAGE_FLOOR:
                return False
            # 0x10 비트 = star tile (위로 지나감) → 통행 판정에서 제외
            if f & 0x10:
                continue
            if (f & _FLAG_PASSABLE_MASK) == _FLAG_PASSABLE_MASK:
                return False
        return True

    if is_safe(cx, cy):
        return cx, cy

    visited = {(cx, cy)}
    q: deque[tuple[int, int]] = deque([(cx, cy)])
    while q:
        x, y = q.popleft()
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited and 0 <= nx < width and 0 <= ny < height:
                visited.add((nx, ny))
                if is_safe(nx, ny):
                    return nx, ny
                q.append((nx, ny))

    return cx, cy  # 모든 타일이 unsafe면 중앙 반환


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

    # 맵 개수 결정: 기획서(game_spec)에 정의된 맵 개수를 우선함
    game_spec = state.get("game_spec")
    if game_spec and game_spec.maps:
        n_maps = len(game_spec.maps)
        logger.info("기획서 기반 맵 개수 설정: n_maps=%d", n_maps)
    elif game_spec and hasattr(game_spec, "playtime_minutes"):
        pt = game_spec.playtime_minutes
        # 5분→3개, 10분→6개, 15분→9개 (선형 비례)
        n_maps = pt * 3 // 5
        logger.info("playtime %d분 → n_maps=%d (기획서 미존재 시 계산)", pt, n_maps)
    else:
        n_maps = 3
        logger.info("기본 맵 개수 설정: n_maps=3")

    file_names = await select_maps(user_input, n_maps=n_maps)
    logger.info("sample_map_selector: 선택된 맵 %s", file_names)

    metadata_index = _load_metadata_index()
    tileset_flags_map = _load_tileset_flags()

    map_specs: list[MapSpec] = []
    map_tiles: dict[int, list[int]] = {}
    compiled_events: dict[int, list[dict]] = {}
    connection_info: dict[int, MapConnectionInfo] = {}

    for idx, fname in enumerate(file_names, start=1):
        path = _SAMPLEMAPS_DIR / fname
        if not path.exists():
            logger.warning("샘플맵 파일 없음: %s", fname)
            continue

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("샘플맵 파싱 실패: %s", fname)
            continue

        meta = metadata_index.get(fname, {})
        display_name = (
            meta.get("display_name") or raw.get("displayName") or fname.replace(".json", "")
        )
        tileset_id = raw.get("tilesetId", 1)
        width = raw.get("width", 30)
        height = raw.get("height", 30)
        bgm_name = (raw.get("bgm") or {}).get("name", "")
        map_type = _MAP_TYPE_BY_TILESET.get(tileset_id, "town")
        tags = meta.get("tags", [])

        # Tilesets.json flags 기반 안전한 시작 좌표 계산
        tile_data = raw.get("data", [])
        ts_flags = tileset_flags_map.get(tileset_id, [])
        if ts_flags and tile_data:
            spawn = _find_safe_spawn(tile_data, width, height, ts_flags)
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
        map_tiles[idx] = raw.get("data", [])

        # events[0]은 RPG Maker MZ 규칙상 null → 제거
        raw_events = raw.get("events") or []
        events_list = [e for e in raw_events if e]
        compiled_events[idx] = events_list

        connection_info[idx] = MapConnectionInfo(map_id=idx, exit_tiles=[], entry_tiles=[])

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
        "completed_phases": completed,
    }
