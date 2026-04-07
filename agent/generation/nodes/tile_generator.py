"""E 노드 — tile_generator: MapSpec[] → map_tiles + connection_info (코드, 맵별 병렬).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.E
canonical: docs/The_world/map_generation.md §E
"""

import asyncio
import logging
from typing import Any

from agent.generation.mapgen import extract_connection_info, generate_map
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def _generate_single_map(
    spec: MapSpec,
    seed: int,
) -> tuple[int, list[int], MapConnectionInfo]:
    """단일 맵 타일 + 연결 정보 생성 (CPU-bound, asyncio로 감싸기)."""
    loop = asyncio.get_event_loop()
    # CPU-bound 알고리즘이므로 스레드풀에서 실행
    data = await loop.run_in_executor(None, generate_map, spec, seed)
    conn_info = extract_connection_info(spec, data)
    return spec.map_id, data, conn_info


async def tile_generator(state: GenerationState) -> dict:
    """E 노드: 모든 MapSpec을 병렬로 타일 배열 생성."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs", [])

    if not map_specs:
        logger.warning("tile_generator: map_specs 없음, 건너뜀")
        return {}

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "tile_generation",
            "progress": 56,
            "message": f"{len(map_specs)}개 맵 타일 생성 중...",
        },
    )

    # 맵별 병렬 생성
    tasks = [_generate_single_map(spec, seed=spec.map_id) for spec in map_specs]
    results: list[Any] = await asyncio.gather(*tasks, return_exceptions=True)

    map_tiles: dict[int, list[int]] = {}
    connection_info: dict[int, MapConnectionInfo] = {}

    for spec, result in zip(map_specs, results):
        if isinstance(result, Exception):
            logger.error("tile_generator: 맵 '%s' 생성 실패: %s", spec.name, result)
            # 폴백: 빈 타일 데이터
            map_tiles[spec.map_id] = [0] * (spec.width * spec.height * 6)
            connection_info[spec.map_id] = MapConnectionInfo(
                map_id=spec.map_id, exit_tiles=[], entry_tiles=[]
            )
        else:
            map_id, data, conn = result
            map_tiles[map_id] = data
            connection_info[map_id] = conn

    logger.info("tile_generator 완료: %d개 맵 타일 생성", len(map_tiles))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "tile_generation",
            "summary": f"{len(map_tiles)}개 맵 타일 생성 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("tile_generation")
    return {
        "map_tiles": map_tiles,
        "connection_info": connection_info,
        "completed_phases": completed,
    }
