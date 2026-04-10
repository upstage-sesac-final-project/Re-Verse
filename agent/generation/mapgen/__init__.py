"""mapgen — 맵 타일 생성 진입점.

generate_map(spec) 호출 시 map_type에 맞는 생성기로 위임.
"""

import logging

from agent.generation.mapgen.dungeon_generator import generate_dungeon
from agent.generation.mapgen.tile_checker import find_nearest_safe_coord, is_walkable
from agent.generation.mapgen.town_generator import generate_town
from agent.generation.models import MapConnectionInfo, MapSpec

# 보스/필드는 던전/마을 생성기 재사용 (Phase 3 단순화)
_GENERATOR = {
    "town": generate_town,
    "dungeon": generate_dungeon,
    "boss": generate_dungeon,
    "field": generate_town,
}

# 맵 크기 고정 (LLM 출력 덮어쓰기)
MAP_SIZE_BY_TYPE: dict[str, tuple[int, int, int]] = {
    # (width, height, tileset_id)
    "town": (30, 30, 1),
    "dungeon": (40, 30, 2),
    "boss": (20, 20, 2),
    "field": (40, 30, 1),
}


def generate_map(spec: MapSpec, seed: int = 0) -> list[int]:
    """map_type에 따라 적절한 생성기 호출. 반환: flat 1D 타일 배열."""
    gen = _GENERATOR.get(spec.map_type, generate_dungeon)
    return gen(spec, seed=seed)


logger = logging.getLogger(__name__)


def calculate_spawn_point(
    spec: MapSpec,
    data: list[int],
    tilesets: list | None = None,
) -> tuple[int, int]:
    """walkable 타일 탐색. tilesets가 주어지면 flags를, 아니면 레이어5를 기준."""
    w, h = spec.width, spec.height
    sx, sy = spec.spawn_point

    # 시작점이 이미 walkable이면 즉시 반환
    if is_walkable(data, sx, sy, w, h, spec.tileset_id, tilesets):
        logger.info("Map '%s': 기존 시작 좌표 (%d, %d)를 사용합니다.", spec.name, sx, sy)
        return sx, sy

    # 보정 시작 로그
    logger.info(
        "Map '%s': 초기 시작 좌표 (%d, %d) 통행 불가 -> 안전한 좌표 탐색 시작", spec.name, sx, sy
    )

    # 안전한 좌표 탐색 (BFS)
    nx, ny = find_nearest_safe_coord(data, sx, sy, w, h, spec.tileset_id, tilesets)

    if (nx, ny) != (sx, sy):
        logger.info(
            "Map '%s': 안전한 시작 좌표 발견 (%d, %d). 좌표를 수정했습니다.",
            spec.name,
            nx,
            ny,
        )
        return nx, ny

    logger.warning("Map '%s': 안전한 좌표를 찾지 못했습니다. 초기값 유지.", spec.name)
    return sx, sy


def get_exit_coords(direction: str, width: int, height: int) -> tuple[int, int]:
    """방향 → 맵 테두리 출구 좌표."""
    mid_x = width // 2
    mid_y = height // 2
    return {
        "north": (mid_x, 1),
        "south": (mid_x, height - 2),
        "east": (width - 2, mid_y),
        "west": (1, mid_y),
    }.get(direction, (mid_x, height - 2))


def extract_connection_info(
    spec: MapSpec, data: list[int], tilesets: list | None = None
) -> MapConnectionInfo:
    """타일 생성 후 맵 연결 좌표 추출."""
    exit_tiles = []
    for exit_spec in spec.exits:
        ex, ey = get_exit_coords(exit_spec.direction, spec.width, spec.height)
        exit_tiles.append(
            {
                "direction": exit_spec.direction,
                "to_map_id": exit_spec.to_map_id,
                "x": ex,
                "y": ey,
            }
        )

    # 타일셋 정보와 함께 스폰 포인트 계산
    spawn = calculate_spawn_point(spec, data, tilesets=tilesets)
    entry_tiles = [{"from_spawn": True, "x": spawn[0], "y": spawn[1]}]

    return MapConnectionInfo(
        map_id=spec.map_id,
        exit_tiles=exit_tiles,
        entry_tiles=entry_tiles,
    )
