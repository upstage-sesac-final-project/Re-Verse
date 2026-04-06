"""mapgen — 맵 타일 생성 진입점.

generate_map(spec) 호출 시 map_type에 맞는 생성기로 위임.
"""

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


def calculate_spawn_point(
    spec: MapSpec,
    data: list[int],
) -> tuple[int, int]:
    """MapSpec.spawn_point가 walkable인지 확인. 아니면 BFS로 가장 가까운 walkable 탐색."""
    w, h = spec.width, spec.height
    sx, sy = spec.spawn_point

    def is_walkable(x: int, y: int) -> bool:
        return get_tile(data, x, y, w, h, 5) == 0

    if is_walkable(sx, sy):
        return sx, sy

    visited = {(sx, sy)}
    q: deque[tuple[int, int]] = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) not in visited and 0 <= nx < w and 0 <= ny < h:
                visited.add((nx, ny))
                if is_walkable(nx, ny):
                    return nx, ny
                q.append((nx, ny))

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


def extract_connection_info(spec: MapSpec, data: list[int]) -> MapConnectionInfo:
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

    spawn = calculate_spawn_point(spec, data)
    entry_tiles = [{"from_spawn": True, "x": spawn[0], "y": spawn[1]}]

    return MapConnectionInfo(
        map_id=spec.map_id,
        exit_tiles=exit_tiles,
        entry_tiles=entry_tiles,
    )
