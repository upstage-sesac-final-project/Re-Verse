"""mapgen — 맵 타일 생성 진입점.

generate_map(spec) 호출 시 map_type에 맞는 생성기로 위임.
"""

import logging
from collections import deque

from agent.generation.mapgen.dungeon_generator import generate_dungeon
from agent.generation.mapgen.tile_constants import get_tile
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

    def is_walkable(x: int, y: int) -> bool:
        # 1. Tilesets.json의 flags 기반 판정 (샘플 맵 등)
        if tilesets and spec.tileset_id < len(tilesets):
            ts = tilesets[spec.tileset_id]
            if ts and "flags" in ts:
                flags = ts["flags"]
                # 레이어 0~3까지 확인 (상층 타일이 통행을 막을 수 있음)
                for layer in range(4):
                    tile_id = get_tile(data, x, y, w, h, layer)
                    if tile_id < len(flags):
                        f = flags[tile_id]
                        # 0x10 (16): 통행 불가 비트.
                        # MZ 표준: 0이면 통과 가능, 16 이상이면 벽/장애물
                        if f & 0x10:
                            return False
                return True

        # 2. 레이어 5번 기반 판정 (자체 생성 맵 폴백)
        return get_tile(data, x, y, w, h, 5) == 0

    # 시작점이 이미 walkable이면 즉시 반환
    if is_walkable(sx, sy):
        logger.info("Map '%s': 기존 시작 좌표 (%d, %d)를 사용합니다.", spec.name, sx, sy)
        return sx, sy

    # 보정 시작 로그
    logger.info(
        "Map '%s': 초기 시작 좌표 (%d, %d) 통행 불가 -> 안전한 좌표 탐색 시작", spec.name, sx, sy
    )

    # BFS 탐색: 가장 가까운 walkable 타일 찾기
    visited = {(sx, sy)}
    q: deque[tuple[int, int]] = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        # 8방향 탐색 (상하좌우 + 대각선)하여 더 빨리 찾기
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited and 0 <= nx < w and 0 <= ny < h:
                visited.add((nx, ny))
                if is_walkable(nx, ny):
                    logger.info(
                        "Map '%s': 안전한 시작 좌표 발견 (%d, %d). 좌표를 수정했습니다.",
                        spec.name,
                        nx,
                        ny,
                    )
                    return nx, ny
                q.append((nx, ny))

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
