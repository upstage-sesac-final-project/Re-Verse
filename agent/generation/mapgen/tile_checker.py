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
FLAG_STAR = 0x10  # 플레이어 위로 표시 (천장/숲 상단 등)
FLAG_LADDER = 0x20  # 사다리
FLAG_BUSH = 0x40  # 숲/풀숲 (캐릭터 하단 반투명)
FLAG_COUNTER = 0x80  # 카운터 (상점 테이블 등)
FLAG_DAMAGE = 0x100  # 데미지 바닥 (독늪, 용암 등)


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
    if region_id == 1:  # Region 1은 명시적 통행 불가로 약속
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
            # MZ 표준: 상위 레이어(3)부터 하위 레이어(0)로 내려가며 확인
            for layer in [3, 2, 1, 0]:
                tile_id = get_tile(data, x, y, width, height, layer)
                if tile_id == 0:  # 투명 타일은 무시하고 아래 레이어 확인
                    continue

                if tile_id < len(flags):
                    f = flags[tile_id]

                    # 0x10 (FLAG_STAR)가 켜져 있으면 '천장'이므로
                    # 통행 판정(막힘)에 영향을 주지 않고 아래 레이어를 확인합니다.
                    if f & FLAG_STAR:
                        continue

                    # 레이어 0 또는 1에 타일이 있다면 바닥이 있는 것으로 간주 (A 레이어)
                    if layer <= 1:
                        found_base = True

                    # 데미지 타일 확인 (0x100)
                    if avoid_damage and (f & FLAG_DAMAGE):
                        logger.info("is_walkable: (x:%d, y:%d) 데미지 타일 감지 (0x%X)", x, y, f)
                        return False

                    # 통행 가능성 판정 (하위 4비트)
                    # 0x01~0x08 중 하나라도 켜져 있으면 해당 방향으로 못 감.
                    # 시작 좌표로는 4방향 모두 열려있는(0x00) 타일이 가장 안전함.
                    if (f & 0x0F) > 0:
                        # logger.debug("is_walkable: (x:%d, y:%d) 막힌 타일 감지 (Layer %d, Flag 0x%X)", x, y, layer, f)
                        return False

                    # 여기까지 왔다면 이 타일이 최종 통행 결정 타일 (통과 가능)
                    return True

            # 모든 레이어를 돌았는데 유효한 바닥이 없거나(전부 0),
            # Star 타일만 있는 경우(바닥 없는 지붕 등)는 통행 불가
            if not found_base:
                return False
    else:
        # tilesets가 None이거나 인덱스가 유효하지 않은 경우 (로그 출력)
        if not tilesets:
            logger.warning(
                "is_walkable(x=%d, y=%d): tilesets 데이터가 None입니다! (폴백 로직 수행)", x, y
            )
        else:
            logger.warning(
                "is_walkable(x=%d, y=%d): tileset_id(%d)가 범위를 벗어났습니다 (len=%d).",
                x,
                y,
                tileset_id,
                len(tilesets),
            )

    # 3. 폴백 (알고리즘 생성 맵용)
    val_l5 = get_tile(data, x, y, width, height, 5)
    return val_l5 == 0

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


def filter_non_corridor_coords(
    coords: list[tuple[int, int]],
    data: list[int],
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None = None,
) -> list[tuple[int, int]]:
    """좌표 목록에서 좁은 통로(corridor) 타일을 제거하여 반환합니다.

    좁은 통로 판별 기준:
    - 4방향 보행 가능한 이웃 타일이 정확히 2개이고
    - 그 2개가 서로 인접하지 않은 경우 (예: 북+남, 동+서, 북+동 등 직접 연결 불가)

    이러한 타일에 이벤트를 배치하면 플레이어의 이동 경로가 차단될 수 있습니다.

    비-통로 좌표가 전체의 20% 미만이면 원본 목록을 반환합니다 (던전 등 통로가 많은 맵 고려).
    """
    coords_set = set(coords)

    def walkable_neighbors(x: int, y: int) -> list[tuple[int, int]]:
        return [
            (x + dx, y + dy)
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if (x + dx, y + dy) in coords_set
            or (
                0 <= x + dx < width
                and 0 <= y + dy < height
                and is_walkable(data, x + dx, y + dy, width, height, tileset_id, tilesets)
            )
        ]

    non_corridor = []
    for x, y in coords:
        nbrs = walkable_neighbors(x, y)
        if len(nbrs) == 2:
            (x1, y1), (x2, y2) = nbrs
            # 두 이웃 사이의 거리가 1이면 서로 인접(코너) → 통로 아님
            # 거리가 2 이상이면 반대편 또는 대각방향 → 좁은 통로
            if abs(x1 - x2) + abs(y1 - y2) > 1:
                continue  # 통로 타일 → 제외
        non_corridor.append((x, y))

    # 비-통로 좌표가 너무 적으면 필터링 효과가 없음 → 원본 복사본 반환
    if len(non_corridor) < max(len(coords) // 5, 5):
        return list(coords)

    return non_corridor


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


def are_exits_reachable(
    data: list[int],
    spawn_x: int,
    spawn_y: int,
    width: int,
    height: int,
    tileset_id: int,
    tilesets: list | None,
    exit_coords: set[tuple[int, int]],
    event_positions: set[tuple[int, int]],
) -> bool:
    """이벤트 배치 후에도 스폰 → 모든 출구 타일이 도달 가능한지 BFS로 검증합니다.

    event_positions에 있는 타일은 이벤트가 점유해 통행 불가로 간주합니다.
    출구 타일이 없으면 항상 True를 반환합니다.
    """
    if not exit_coords:
        return True

    # 스폰 자체가 막혀 있으면 체크 불가 → True(낙관적)
    if (spawn_x, spawn_y) in event_positions:
        return True

    visited: set[tuple[int, int]] = {(spawn_x, spawn_y)}
    queue: deque[tuple[int, int]] = deque([(spawn_x, spawn_y)])

    while queue:
        x, y = queue.popleft()
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            nb = (nx, ny)
            if nb in visited or nb in event_positions:
                continue
            if 0 <= nx < width and 0 <= ny < height:
                if is_walkable(data, nx, ny, width, height, tileset_id, tilesets):
                    visited.add(nb)
                    queue.append(nb)

    return all(ec in visited for ec in exit_coords)
