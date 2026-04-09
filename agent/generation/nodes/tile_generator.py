"""E 노드 — tile_generator: MapSpec[] → map_tiles + connection_info (코드, 맵별 병렬).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.E
canonical: docs/The_world/map_generation.md §E
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from agent.generation.mapgen import extract_connection_info, generate_map
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

# 샘플 맵 저장 경로
SAMPLE_MAPS_DIR = Path("agent/rag/data/samplemaps")


async def _load_or_generate_map(
    spec: MapSpec,
    seed: int,
) -> tuple[int, list[int], MapConnectionInfo]:
    """샘플이 있으면 로드, 없으면 생성."""
    loop = asyncio.get_event_loop()

    # 1. 샘플 맵 로드 시도
    if spec.original_file_name:
        sample_path = SAMPLE_MAPS_DIR / spec.original_file_name
        if sample_path.exists():
            try:
                with open(sample_path, encoding="utf-8") as f:
                    map_data = json.load(f)
                    tile_data = map_data.get("data", [])
                    if tile_data:
                        logger.info("샘플 맵 타일 로드 성공: %s", spec.original_file_name)
                        # 샘플 맵의 연결 정보 추출 (exits 기준)
                        conn_info = extract_connection_info(spec, tile_data)
                        return spec.map_id, tile_data, conn_info
            except Exception as e:
                logger.error("샘플 맵 로드 중 에러 (%s): %s", spec.original_file_name, e)

    # 2. 샘플이 없거나 로드 실패 시 기존 AI 생성 로직 실행
    data = await loop.run_in_executor(None, generate_map, spec, seed)
    conn_info = extract_connection_info(spec, data)
    return spec.map_id, data, conn_info


async def tile_generator(state: GenerationState) -> dict:
    """E 노드: 모든 MapSpec을 병렬로 타일 배열 생성 또는 로드."""
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
            "message": f"{len(map_specs)}개 맵 타일 준비 중...",
        },
    )

    # 맵별 병렬 처리
    tasks = [_load_or_generate_map(spec, seed=spec.map_id) for spec in map_specs]
    results: list[Any] = await asyncio.gather(*tasks, return_exceptions=True)

    map_tiles: dict[int, list[int]] = {}
    connection_info: dict[int, MapConnectionInfo] = {}

    for spec, result in zip(map_specs, results):
        if isinstance(result, Exception):
            logger.error("tile_generator: 맵 '%s' 준비 실패: %s", spec.name, result)
            map_tiles[spec.map_id] = [0] * (spec.width * spec.height * 6)
            connection_info[spec.map_id] = MapConnectionInfo(
                map_id=spec.map_id, exit_tiles=[], entry_tiles=[]
            )
        else:
            map_id, data, conn = result
            map_tiles[map_id] = data
            connection_info[map_id] = conn

    logger.info("tile_generator 완료: %d개 맵 데이터 준비", len(map_tiles))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "tile_generation",
            "summary": f"{len(map_tiles)}개 맵 데이터 준비 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("tile_generation")
    return {
        "map_tiles": map_tiles,
        "connection_info": connection_info,
        "completed_phases": completed,
    }
