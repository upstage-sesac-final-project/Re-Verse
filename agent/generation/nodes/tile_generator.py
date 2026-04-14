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
from agent.generation.nodes.integrator import load_base_tilesets
from agent.generation.progress import publish_progress
from agent.generation.state import GenerationState
from app.backend.core.config import settings

logger = logging.getLogger(__name__)


async def _load_or_generate_map(
    spec: MapSpec,
    seed: int,
    tilesets: list | None = None,
) -> tuple[int, list[int], MapConnectionInfo]:
    """샘플이 있으면 로드, 없으면 생성."""
    loop = asyncio.get_event_loop()

    # 1. 샘플 맵 로드 시도
    if spec.original_file_name:
        sample_maps_dir = Path(settings.BASE_GAME_PATH) / "samplemaps"
        sample_path = sample_maps_dir / spec.original_file_name
        if sample_path.exists():
            try:
                with open(sample_path, encoding="utf-8") as f:
                    map_data = json.load(f)
                    tile_data = map_data.get("data", [])
                    if tile_data:
                        logger.info("샘플 맵 타일 로드 성공: %s", spec.original_file_name)
                        # 샘플 맵의 연결 정보 추출 (flags 기준)
                        conn_info = extract_connection_info(spec, tile_data, tilesets=tilesets)
                        return spec.map_id, tile_data, conn_info
            except Exception as e:
                logger.error("샘플 맵 로드 중 에러 (%s): %s", spec.original_file_name, e)
        else:
            logger.warning("샘플 맵 파일 없음: %s", sample_path)

    # 2. 샘플이 없거나 로드 실패 시 기존 AI 생성 로직 실행
    data = await loop.run_in_executor(None, generate_map, spec, seed)
    conn_info = extract_connection_info(spec, data, tilesets=tilesets)
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

    # 타일셋 정보 로드 (스폰 포인트 계산용)
    tilesets = load_base_tilesets()

    # 맵별 병렬 처리
    tasks = [_load_or_generate_map(spec, seed=spec.map_id, tilesets=tilesets) for spec in map_specs]
    results: list[Any] = await asyncio.gather(*tasks, return_exceptions=True)

    map_tiles: dict[int, list[int]] = {}
    connection_info: dict[int, MapConnectionInfo] = {}
    updated_map_specs: list[MapSpec] = []

    for spec, result in zip(map_specs, results):
        if isinstance(result, Exception):
            logger.error("tile_generator: 맵 '%s' 준비 실패: %s", spec.name, result)
            map_tiles[spec.map_id] = [0] * (spec.width * spec.height * 6)
            connection_info[spec.map_id] = MapConnectionInfo(
                map_id=spec.map_id, exit_tiles=[], entry_tiles=[]
            )
            updated_map_specs.append(spec)
        else:
            map_id, data, conn = result
            map_tiles[map_id] = data
            connection_info[map_id] = conn
            # connection_info에서 계산된 실제 spawn_point를 spec에 반영
            # (map_designer는 중앙 좌표로 초기화하므로, 최대 연결 구역 기준으로 교정)
            if conn.entry_tiles:
                actual_spawn = (conn.entry_tiles[0]["x"], conn.entry_tiles[0]["y"])
                if actual_spawn != spec.spawn_point:
                    logger.info(
                        "tile_generator: Map '%s' spawn_point 교정 (%d,%d) → (%d,%d)",
                        spec.name,
                        spec.spawn_point[0],
                        spec.spawn_point[1],
                        actual_spawn[0],
                        actual_spawn[1],
                    )
                    spec = spec.model_copy(update={"spawn_point": actual_spawn})
            updated_map_specs.append(spec)

    logger.info("tile_generator 완료: %d개 맵 데이터 준비", len(map_tiles))
    map_specs = updated_map_specs

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
        "map_specs": map_specs,  # spawn_point 교정된 버전 전파
        "completed_phases": completed,
    }
