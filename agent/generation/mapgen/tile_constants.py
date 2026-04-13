"""타일 ID 상수 및 공통 유틸리티.

canonical: docs/The_world/map_generation.md §타일셋 ID 매핑
"""

# ── 마을 타일셋 (tileset_id=1, Exterior) ─────────────────────────────────────

TOWN_TILES: dict[str, int] = {
    "grass": 2816,  # 잔디 (이동 가능)
    "dirt_path": 2624,  # 흙길 (이동 가능)
    "stone_path": 2576,  # 돌길 (이동 가능)
    "water": 4352,  # 물 (이동 불가)
    "tree": 3584,  # 나무 (이동 불가)
    "fence": 3456,  # 울타리 (이동 불가)
    "building_tl": 2050,  # 건물 타일 2×2 블록
    "building_tr": 2051,
    "building_bl": 2082,
    "building_br": 2083,
    "door": 2114,  # 문 (이동 가능)
    "well": 2370,  # 우물 (이동 불가, 장식)
    "border_wall": 2624,  # 외곽 벽
}

# 마을에서 이동 불가 타일 IDs
TOWN_IMPASSABLE: set[int] = {
    TOWN_TILES["tree"],
    TOWN_TILES["fence"],
    TOWN_TILES["water"],
    TOWN_TILES["well"],
    TOWN_TILES["building_tl"],
    TOWN_TILES["building_tr"],
    TOWN_TILES["building_bl"],
    TOWN_TILES["building_br"],
}

# ── 던전 타일셋 (tileset_id=2, Dungeon) ──────────────────────────────────────

DUNGEON_TILES: dict[str, int] = {
    "floor": 2816,  # 바닥 (이동 가능)
    "wall": 2624,  # 벽 (이동 불가)
    "wall_top": 2576,  # 벽 상단 장식
    "door": 2818,  # 문
    "stairs_up": 2884,  # 위층 계단 (입구)
    "stairs_down": 2885,  # 아래층 계단 (출구)
    "chest_tile": 2882,  # 상자 위치 표시
    "darkness": 0,  # 아무것도 없음
    "lava": 4416,  # 용암 (이동 불가, 장식)
}

# 던전에서 이동 불가 타일 IDs (레이어0 기준)
DUNGEON_IMPASSABLE: set[int] = {
    DUNGEON_TILES["wall"],
    DUNGEON_TILES["wall_top"],
    DUNGEON_TILES["lava"],
    DUNGEON_TILES["darkness"],
}

# ── 6레이어 공통 유틸리티 ─────────────────────────────────────────────────────


def make_empty_data(width: int, height: int) -> list[int]:
    """width × height × 6 크기의 타일 데이터 배열 초기화."""
    return [0] * (width * height * 6)


def set_tile(
    data: list[int], x: int, y: int, width: int, height: int, layer: int, tile_id: int
) -> None:
    """지정 좌표·레이어에 타일 ID 설정."""
    if 0 <= x < width and 0 <= y < height and 0 <= layer < 6:
        idx = (layer * width * height) + (y * width) + x
        data[idx] = tile_id


def get_tile(data: list[int], x: int, y: int, width: int, height: int, layer: int) -> int:
    """지정 좌표·레이어의 타일 ID 반환."""
    if 0 <= x < width and 0 <= y < height and 0 <= layer < 6:
        idx = (layer * width * height) + (y * width) + x
        return data[idx]
    return 0


def set_passability(
    data: list[int],
    width: int,
    height: int,
    impassable_tiles: set[int],
    layer_check: int = 1,
) -> None:
    """레이어1(건물/나무) 기준으로 통행 불가(레이어5) 설정.

    레이어5 값: 0=통행 가능, 1=통행 불가
    """
    for y in range(height):
        for x in range(width):
            tile_l0 = get_tile(data, x, y, width, height, 0)
            tile_l1 = get_tile(data, x, y, width, height, layer_check)
            if tile_l0 in impassable_tiles or tile_l1 in impassable_tiles:
                set_tile(data, x, y, width, height, 5, 1)
