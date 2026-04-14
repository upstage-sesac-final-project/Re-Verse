"""mapgen — 맵 타일 생성 진입점.

generate_map(spec) 호출 시 map_type에 맞는 생성기로 위임.
"""

import logging
from collections import deque

from agent.generation.mapgen.dungeon_generator import generate_dungeon
from agent.generation.mapgen.tile_checker import is_walkable
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


def _find_largest_component(
    data: list[int],
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None = None,
) -> list[tuple[int, int]]:
    """맵 내 walkable 타일을 flood-fill로 연결 구역으로 분리하고 가장 큰 구역을 반환.

    샘플 맵은 물/벽으로 분리된 복수의 독립 구역을 가질 수 있다.
    가장 큰 연결 구역 = 플레이어가 실제로 이동하는 주요 구역.
    """
    all_walkable: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            if is_walkable(data, x, y, width, height, tileset_id, tilesets):
                all_walkable.add((x, y))

    if not all_walkable:
        return []

    visited: set[tuple[int, int]] = set()
    largest: list[tuple[int, int]] = []

    for start in all_walkable:
        if start in visited:
            continue
        component: list[tuple[int, int]] = []
        queue: deque[tuple[int, int]] = deque([start])
        visited.add(start)
        while queue:
            cx, cy = queue.popleft()
            component.append((cx, cy))
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nb = (cx + dx, cy + dy)
                if nb not in visited and nb in all_walkable:
                    visited.add(nb)
                    queue.append(nb)
        if len(component) > len(largest):
            largest = component

    return largest


def calculate_spawn_point(
    spec: MapSpec,
    data: list[int],
    tilesets: list | None = None,
) -> tuple[int, int]:
    """맵에서 가장 큰 연결 통행 구역의 중심에 가장 가까운 타일을 스폰 포인트로 반환.

    기존 방식(맵 중앙 고정)은 물/벽으로 분리된 샘플 맵에서 고립 구역을
    스폰 포인트로 잘못 선택하는 문제가 있었다.
    가장 큰 연결 구역을 선택함으로써 실제 플레이 가능 영역에 이벤트가 배치된다.
    """
    w, h = spec.width, spec.height
    center_x, center_y = w // 2, h // 2

    largest = _find_largest_component(data, w, h, spec.tileset_id, tilesets)

    if not largest:
        logger.warning(
            "Map '%s': walkable 타일 없음 → 맵 중앙 폴백 (%d, %d)", spec.name, center_x, center_y
        )
        return center_x, center_y

    # 가장 큰 구역에서 맵 중심에 가장 가까운 타일 선택
    best = min(largest, key=lambda p: abs(p[0] - center_x) + abs(p[1] - center_y))

    logger.info(
        "Map '%s': 최대 연결 구역(%d타일) 스폰 포인트 → (%d, %d)",
        spec.name,
        len(largest),
        best[0],
        best[1],
    )
    return best


def get_exit_coords(direction: str, width: int, height: int) -> tuple[int, int]:
    """방향 → 맵 테두리 출구 좌표 (walkable 검증 없는 기본값, 하위 호환용)."""
    mid_x = width // 2
    mid_y = height // 2
    return {
        "north": (mid_x, 1),
        "south": (mid_x, height - 2),
        "east": (width - 2, mid_y),
        "west": (1, mid_y),
    }.get(direction, (mid_x, height - 2))


def _get_exit_coords_in_component(
    direction: str,
    width: int,
    height: int,
    component: set[tuple[int, int]],
) -> tuple[int, int]:
    """방향별 경계에서 main_component 안의 타일 중 경계에 가장 가까운 좌표 반환.

    출구는 플레이어가 실제로 이동하는 주요 구역(component) 안에 있어야 한다.
    component에 해당 경계 근처 타일이 없으면 기본 중앙 좌표로 폴백.
    """
    mid_x = width // 2
    mid_y = height // 2

    if direction == "south":
        # y가 클수록 남쪽 경계에 가까움, x는 mid_x에 가까울수록 우선
        candidates = sorted(component, key=lambda p: (-(p[1]), abs(p[0] - mid_x)))
    elif direction == "north":
        candidates = sorted(component, key=lambda p: (p[1], abs(p[0] - mid_x)))
    elif direction == "east":
        candidates = sorted(component, key=lambda p: (-(p[0]), abs(p[1] - mid_y)))
    elif direction == "west":
        candidates = sorted(component, key=lambda p: (p[0], abs(p[1] - mid_y)))
    else:
        candidates = sorted(component, key=lambda p: (-(p[1]), abs(p[0] - mid_x)))

    if candidates:
        return candidates[0]

    # 폴백: 기본 중앙 좌표
    return get_exit_coords(direction, width, height)


def extract_connection_info(
    spec: MapSpec, data: list[int], tilesets: list | None = None
) -> MapConnectionInfo:
    """타일 생성 후 맵 연결 좌표 추출.

    스폰 포인트와 출구 좌표 모두 가장 큰 연결 통행 구역 안에서 선택한다.
    이를 통해 이벤트가 플레이어가 실제로 이동 가능한 영역에 배치된다.
    """
    w, h = spec.width, spec.height

    # 가장 큰 연결 구역 한 번만 계산 (spawn + exit 모두 재사용)
    largest = _find_largest_component(data, w, h, spec.tileset_id, tilesets)
    component_set: set[tuple[int, int]] = set(largest)

    # 스폰 포인트: 최대 연결 구역 중심 근접 타일
    if largest:
        center_x, center_y = w // 2, h // 2
        spawn = min(largest, key=lambda p: abs(p[0] - center_x) + abs(p[1] - center_y))
        logger.info(
            "Map '%s': 최대 연결 구역(%d타일) 스폰 포인트 → (%d, %d)",
            spec.name,
            len(largest),
            spawn[0],
            spawn[1],
        )
    else:
        spawn = (w // 2, h // 2)
        logger.warning("Map '%s': walkable 타일 없음 → 맵 중앙 스폰 폴백", spec.name)

    # 출구 좌표: 최대 연결 구역 안에서 방향별 경계에 가장 가까운 타일
    exit_tiles = []
    for exit_spec in spec.exits:
        if component_set:
            ex, ey = _get_exit_coords_in_component(exit_spec.direction, w, h, component_set)
        else:
            ex, ey = get_exit_coords(exit_spec.direction, w, h)

        logger.info(
            "Map '%s': exit %s → (%d, %d)",
            spec.name,
            exit_spec.direction,
            ex,
            ey,
        )
        exit_tiles.append(
            {
                "direction": exit_spec.direction,
                "to_map_id": exit_spec.to_map_id,
                "x": ex,
                "y": ey,
            }
        )

    entry_tiles = [{"from_spawn": True, "x": spawn[0], "y": spawn[1]}]

    return MapConnectionInfo(
        map_id=spec.map_id,
        exit_tiles=exit_tiles,
        entry_tiles=entry_tiles,
    )
