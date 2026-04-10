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
    """타일의 통행 가능 여부를 확인합니다 (RPG Maker MZ 표준 엔진 로직).

    판정 순서:
    1. Region ID (레이어 5)가 1이면 통행 불가.
    2. 레이어 3 -> 0 순으로 검사.
    3. 타일 ID가 0이 아닌 첫 번째 타일을 찾음.
    4. 만약 해당 타일의 플래그에 0x10(Star)이 켜져 있으면, 이 타일은 통과하고 다음 아래 레이어를 검사.
    5. Star가 없는 첫 번째 타일의 플래그(0x01~0x0F)가 0x0F(전방향 차단)이면 통행 불가.
    6. 모든 레이어가 0(빈 공간)이거나 Star 타일만 있다면 통행 불가.
    """
    if not (0 <= x < width and 0 <= y < height):
        return False

    # 1. Region ID (레이어 5) 체크
    region_id = get_tile(data, x, y, width, height, 5)
    if blocked_regions and region_id in blocked_regions:
        return False
    if region_id == 1:
        return False

    # 2. Tilesets.json의 flags 기반 판정
    if tilesets and tileset_id < len(tilesets):
        ts = tilesets[tileset_id]
        if ts and "flags" in ts:
            flags = ts["flags"]

            for layer in [3, 2, 1, 0]:
                tile_id = get_tile(data, x, y, width, height, layer)
                if tile_id == 0:
                    continue

                if tile_id < len(flags):
                    f = flags[tile_id]

                    # 0x10 비트는 'Star' (Overhead) 타일을 의미함.
                    # 이 타일은 캐릭터가 밑으로 지나갈 수 있으므로 판정을 무시하고 다음 레이어로 내려감.
                    if f & 0x10:
                        continue

                    # 데미지 타일 확인 (0x100)
                    if avoid_damage and (f & FLAG_DAMAGE):
                        return False

                    # 0x0F (0x01|0x02|0x04|0x08) 는 모든 방향 통행 불가 (벽, 깊은 물 등)
                    # MZ에서 일반적인 통행 불가 타일은 0x0F 또는 0x1F(Star가 아닌 벽) 값을 가짐.
                    if (f & 0x0F) == 0x0F:
                        return False

                    # 여기까지 왔다면 통과 가능한 타일을 찾은 것임
                    return True

            # 모든 레이어를 다 돌았는데 통과 가능한 타일을 못 찾았거나(전부 빈 공간),
            # 전부 Star 타일만 있는 경우엔 땅이 없는 것으로 간주.
            return False

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
    max_radius: int = 20,  # 반경 더 확대
    used_coords: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """주어진 좌표에서 가장 가까운 안전하고 비어있는 좌표를 찾습니다 (BFS)."""

    def is_safe(tx, ty):
        # 통행 가능 여부 확인
        if not is_walkable(data, tx, ty, width, height, tileset_id, tilesets):
            return False
        # 이미 이벤트가 배치된 좌표인지 확인
        if used_coords and (tx, ty) in used_coords:
            return False
        return True

    # 시작점이 이미 안전하면 즉시 반환
    if is_safe(start_x, start_y):
        return start_x, start_y

    visited = {(start_x, start_y)}
    queue = deque([(start_x, start_y, 0)])

    while queue:
        x, y, dist = queue.popleft()
        if dist >= max_radius:
            continue

        # 8방향 탐색
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                visited.add((nx, ny))
                if is_safe(nx, ny):
                    return nx, ny
                queue.append((nx, ny, dist + 1))

    return start_x, start_y
