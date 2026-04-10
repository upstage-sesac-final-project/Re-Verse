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
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_SAMPLEMAPS_DIR = Path(__file__).parents[2] / "rag" / "data" / "samplemaps"
_METADATA_PATH = Path(__file__).parents[2] / "generation" / "mapgen" / "data" / "map_metadata.json"


_MAP_TYPE_BY_TILESET = {
    1: "field",  # 월드맵
    2: "town",  # 자연/야외 (마을 다수)
    3: "town",  # 건물 실내
    4: "dungeon",  # 던전/지하
    5: "town",  # 현대 야외
    6: "town",  # SF/현대 실내
}


def _load_metadata_index() -> dict[str, dict[str, Any]]:
    raw = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
    return {e["file_name"]: e for e in raw}


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

    # 선택할 맵 개수 — 일단 3개 고정 (추후 GenerationOptions로 노출)
    n_maps = 3
    file_names = await select_maps(user_input, n_maps=n_maps)
    logger.info("sample_map_selector: 선택된 맵 %s", file_names)

    metadata_index = _load_metadata_index()

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
            spawn_point=(width // 2, height // 2),
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
