"""타일 통행성 및 속성 체크 유틸리티.

RPG Maker MZ Tilesets.json의 flags 비트 연산을 기반으로 타일의 특성을 판별합니다.
"""

import logging
from collections import deque

from agent.generation.mapgen.tile_constants import get_tile

logger = logging.getLogger(__name__)

# RPG Maker MZ 타일 플래그 비트 상수
FLAG_IMP_DOWN = 0x01  # 아래쪽 통행 불가
FLAG_IMP_LEFT = 0x02  # 왼쪽 통행 불가
FLAG_IMP_RIGHT = 0x04  # 오른쪽 통행 불가
FLAG_IMP_UP = 0x08  # 위쪽 통행 불가
FLAG_IMP_ALL = 0x10  # 전방향 통행 불가 (벽/장애물)
FLAG_BUSH = 0x40  # 숲 (반투명 처리)
FLAG_COUNTER = 0x80  # 카운터 (상점 테이블 등)
FLAG_DAMAGE = 0x100  # 데미지 바닥 (독늪, 용암 등)
FLAG_LADDER = 0x20  # 사다리


def is_walkable(
    data: list[int],
    x: int,
    y: int,
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None = None,
    avoid_damage: bool = True,
    blocked_regions: set[int] | None = None,
) -> bool:
    """타일의 통행 가능 여부를 확인합니다 (RPG Maker MZ 표준 엔진 로직)."""
    if not (0 <= x < width and 0 <= y < height):
        return False

    # 1. Region ID (레이어 5) 체크
    region_id = get_tile(data, x, y, width, height, 5)
    if blocked_regions and region_id in blocked_regions:
        return False
    if region_id == 1:
        return False

    # 2. Tilesets.json의 flags 기반 판정
    if tilesets and 0 <= tileset_id < len(tilesets):
        ts = tilesets[tileset_id]
        if ts and "flags" in ts:
            flags = ts["flags"]

            # 폴백 데이터 감지 (flags가 모두 0이면 경고)
            if all(f == 0 for f in flags[:100]):
                logger.warning(
                    "is_walkable: Tileset %d의 flags가 모두 0입니다! (폴백 데이터 의심)", tileset_id
                )

            found_base = False
            for layer in [3, 2, 1, 0]:
                tile_id = get_tile(data, x, y, width, height, layer)
                if tile_id == 0:
                    continue

                if tile_id < len(flags):
                    f = flags[tile_id]

                    # 0x10 비트는 'Star' (Overhead) 타일을 의미함.
                    if f & 0x10:
                        # Star 타일 아래에 땅이 있는지 계속 확인
                        continue

                    # 레이어 0 또는 1에 타일이 있다면 바닥이 있는 것으로 간주
                    if layer <= 1:
                        found_base = True

                    # 데미지 타일 확인 (0x100)
                    if avoid_damage and (f & FLAG_DAMAGE):
                        return False

                    # 0x0F (전방향 차단) 확인
                    if (f & 0x0F) > 0:
                        return False

                    # 통과 가능한 타일을 찾았음
                    return True

            # 모든 레이어를 돌았는데 유효한 바닥이 없거나(전부 0),
            # Star 타일만 있는 경우(바닥 없는 지붕 등)는 통행 불가
            if not found_base:
                return False
    else:
        # tilesets가 None이거나 인덱스가 유효하지 않은 경우
        if not tilesets:
            logger.warning("is_walkable: tilesets 데이터가 None입니다! 정확한 판정이 불가능합니다.")
        else:
            logger.warning(
                "is_walkable: tileset_id(%d)가 범위를 벗어났습니다 (len=%d).",
                tileset_id,
                len(tilesets),
            )

    # 3. 폴백 (알고리즘 생성 맵용)
    val_l5 = get_tile(data, x, y, width, height, 5)
    return val_l5 == 0


def find_nearest_safe_coord(
    data: list[int],
    start_x: int,
    start_y: int,
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None = None,
    max_radius: int = 20,
    used_coords: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """주어진 좌표에서 가장 가까운 안전하고 비어있는 좌표를 찾습니다 (BFS)."""

    def is_safe(tx, ty):
        if not is_walkable(data, tx, ty, width, height, tileset_id, tilesets):
            return False
        if used_coords and (tx, ty) in used_coords:
            return False
        return True

    if is_safe(start_x, start_y):
        return start_x, start_y

    visited = {(start_x, start_y)}
    queue = deque([(start_x, start_y, 0)])

    while queue:
        x, y, dist = queue.popleft()
        if dist >= max_radius:
            continue

        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                visited.add((nx, ny))
                if is_safe(nx, ny):
                    return nx, ny
                queue.append((nx, ny, dist + 1))

    return start_x, start_y


def get_all_safe_coords(
    data: list[int],
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None = None,
    avoid_damage: bool = True,
    used_coords: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """맵 내의 모든 통행 가능하고 안전한 좌표 리스트를 반환합니다."""
    safe_coords = []
    for y in range(height):
        for x in range(width):
            if is_walkable(
                data, x, y, width, height, tileset_id, tilesets, avoid_damage=avoid_damage
            ):
                if used_coords and (x, y) in used_coords:
                    continue
                safe_coords.append((x, y))
    return safe_coords


def get_reachable_coords(
    data: list[int],
    start_x: int,
    start_y: int,
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None = None,
    avoid_damage: bool = True,
    used_coords: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """시작 지점에서 도달 가능한 모든 안전한 좌표 리스트를 반환합니다 (Flood Fill)."""
    # 시작 지점이 안전하지 않으면 근처 안전한 곳 찾기
    sx, sy = find_nearest_safe_coord(data, start_x, start_y, width, height, tileset_id, tilesets)

    reachable = []
    visited = {(sx, sy)}
    queue = deque([(sx, sy)])

    while queue:
        x, y = queue.popleft()
        reachable.append((x, y))

        # 4방향 탐색 (RPG Maker MZ는 기본적으로 4방향 통행)
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                if is_walkable(
                    data, nx, ny, width, height, tileset_id, tilesets, avoid_damage=avoid_damage
                ):
                    visited.add((nx, ny))
                    queue.append((nx, ny))

    # 이미 사용 중인 좌표 제외
    if used_coords:
        reachable = [c for c in reachable if c not in used_coords]

    return reachable
