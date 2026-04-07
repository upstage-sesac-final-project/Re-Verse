"""마을 타일 생성기 — 격자형 건물 배치 알고리즘.

canonical: docs/The_world/map_generation.md §E-1
"""

import random

from agent.generation.mapgen.tile_constants import (
    TOWN_IMPASSABLE,
    TOWN_TILES,
    get_tile,
    make_empty_data,
    set_passability,
    set_tile,
)
from agent.generation.models import MapSpec

# ── position_hint → 좌표 비율 매핑 ──────────────────────────────────────────

_HINT_RATIOS: dict[str, tuple[float, float]] = {
    "north": (0.5, 0.10),
    "south": (0.5, 0.90),
    "east": (0.90, 0.5),
    "west": (0.10, 0.5),
    "north-center": (0.5, 0.15),
    "south-center": (0.5, 0.85),
    "east-center": (0.85, 0.5),
    "west-center": (0.15, 0.5),
    "center": (0.5, 0.5),
}


def hint_to_coords(hint: str, width: int, height: int) -> tuple[int, int]:
    """position_hint → 실제 타일 좌표. 약간의 랜덤 오프셋 추가."""
    rx, ry = _HINT_RATIOS.get(hint, (0.5, 0.5))
    base_x = int(width * rx)
    base_y = int(height * ry)
    ox = random.randint(-2, 2)
    oy = random.randint(-2, 2)
    x = max(2, min(width - 4, base_x + ox))
    y = max(2, min(height - 4, base_y + oy))
    return x, y


def get_exit_position(direction: str, width: int, height: int) -> tuple[int, int]:
    """출구 방향 → 테두리 좌표."""
    mid_x = width // 2
    mid_y = height // 2
    return {
        "north": (mid_x, 1),
        "south": (mid_x, height - 2),
        "east": (width - 2, mid_y),
        "west": (1, mid_y),
    }.get(direction, (mid_x, height - 2))


def _place_building(data: list[int], x: int, y: int, width: int, height: int) -> None:
    """2×2 건물 블록 + 문 배치."""
    # 경계 체크
    if x + 1 >= width - 1 or y + 2 >= height - 1:
        return
    set_tile(data, x, y, width, height, 1, TOWN_TILES["building_tl"])
    set_tile(data, x + 1, y, width, height, 1, TOWN_TILES["building_tr"])
    set_tile(data, x, y + 1, width, height, 1, TOWN_TILES["building_bl"])
    set_tile(data, x + 1, y + 1, width, height, 1, TOWN_TILES["building_br"])
    # 문: 건물 아래 왼쪽
    set_tile(data, x, y + 2, width, height, 0, TOWN_TILES["door"])


def _connect_to_road(data: list[int], bx: int, by: int, width: int, height: int) -> None:
    """건물 문(bx, by+2)에서 가장 가까운 돌길까지 흙길 연결."""
    door_x, door_y = bx, by + 2
    # 수직: 중앙 십자형 가로줄까지
    center_y = height // 2
    step = 1 if center_y > door_y else -1
    for y in range(door_y, center_y, step):
        if 0 < y < height - 1:
            cur = get_tile(data, door_x, y, width, height, 0)
            if cur not in {TOWN_TILES["stone_path"]}:
                set_tile(data, door_x, y, width, height, 0, TOWN_TILES["dirt_path"])
                # 레이어1 장애물 제거
                set_tile(data, door_x, y, width, height, 1, 0)


def generate_town(spec: MapSpec, seed: int = 0) -> list[int]:
    """마을 타일 데이터 생성. 반환: flat 1D list[int] (width×height×6)."""
    random.seed(seed if seed else spec.map_id)
    w, h = spec.width, spec.height
    data = make_empty_data(w, h)

    # 1단계: 전체 잔디
    for y in range(h):
        for x in range(w):
            set_tile(data, x, y, w, h, 0, TOWN_TILES["grass"])

    # 2단계: 외곽 나무 (1타일 테두리)
    for x in range(w):
        set_tile(data, x, 0, w, h, 1, TOWN_TILES["tree"])
        set_tile(data, x, h - 1, w, h, 1, TOWN_TILES["tree"])
    for y in range(h):
        set_tile(data, 0, y, w, h, 1, TOWN_TILES["tree"])
        set_tile(data, w - 1, y, w, h, 1, TOWN_TILES["tree"])

    # 3단계: 중앙 십자형 돌길
    for x in range(1, w - 1):
        set_tile(data, x, h // 2, w, h, 0, TOWN_TILES["stone_path"])
        set_tile(data, x, h // 2, w, h, 1, 0)  # 레이어1 클리어
    for y in range(1, h - 1):
        set_tile(data, w // 2, y, w, h, 0, TOWN_TILES["stone_path"])
        set_tile(data, w // 2, y, w, h, 1, 0)

    # 4~5단계: 랜드마크 배치
    building_positions: list[tuple[int, int]] = []
    for landmark in spec.landmarks:
        if landmark.landmark_type == "building":
            bx, by = hint_to_coords(landmark.position_hint, w, h)
            # 이미 배치된 건물과 너무 가깝지 않은지 확인
            too_close = any(abs(bx - ox) < 4 and abs(by - oy) < 4 for ox, oy in building_positions)
            if not too_close:
                _place_building(data, bx, by, w, h)
                building_positions.append((bx, by))

    # 6단계: 건물 → 길 연결
    for bx, by in building_positions:
        _connect_to_road(data, bx, by, w, h)

    # 7단계: 출구 타일 (나무 제거 + 흙길)
    for exit_spec in spec.exits:
        ex, ey = get_exit_position(exit_spec.direction, w, h)
        set_tile(data, ex, ey, w, h, 0, TOWN_TILES["dirt_path"])
        set_tile(data, ex, ey, w, h, 1, 0)  # 장애물 제거

    # 8단계: 통행 불가 레이어 설정
    set_passability(data, w, h, TOWN_IMPASSABLE, layer_check=1)

    return data
