"""타일 data 배열 수정 연산.

RPG Maker MZ 타일 인덱스 공식:
    index = layer * (width * height) + y * width + x

레이어 0~5 (총 6개), 각 레이어는 width*height 개의 타일 ID를 가진다.
"""

from typing import Any

# ── 타일 ID 상수 (RPG Maker MZ 기본 타일셋 기준) ─────────────────────────────
TILE_A2_GRASS: int = 2432  # 풀밭 (A2 - 외부 바닥)
TILE_A2_DIRT: int = 2576  # 흙 (A2 - 외부 바닥)
TILE_A3_FLOOR: int = 2816  # 건물 바닥 (A3 - 실내)
TILE_A4_WALL: int = 3200  # 벽 (A4)
TILE_A5_STONE: int = 3584  # 돌 바닥 (A5)
TILE_A5_WOOD: int = 3592  # 나무 바닥 (A5)

# ── 테마 → 기본 tile_id 매핑 ─────────────────────────────────────────────────
# tilesetId 2=외부, 3=내부, 4=던전
THEME_TILE: dict[str, int] = {
    "field": TILE_A2_GRASS,  # 2432 풀밭
    "town": TILE_A3_FLOOR,  # 2816 건물 바닥
    "dungeon": TILE_A5_STONE,  # 3584 돌 바닥
    "indoor": TILE_A5_WOOD,  # 3592 나무 바닥
    "desert": TILE_A2_DIRT,  # 2576 흙
}

# 테마 → 권장 tilesetId
THEME_TILESET: dict[str, int] = {
    "field": 2,
    "town": 2,
    "dungeon": 4,
    "indoor": 3,
    "desert": 2,
}

_MAX_LAYER = 5


def _tile_index(width: int, height: int, x: int, y: int, layer: int) -> int:
    return layer * (width * height) + y * width + x


def _validate(map_data: dict[str, Any], x: int, y: int, layer: int) -> None:
    w, h = map_data["width"], map_data["height"]
    if not (0 <= x < w):
        raise ValueError(f"x={x}가 맵 너비({w}) 범위를 벗어났습니다.")
    if not (0 <= y < h):
        raise ValueError(f"y={y}가 맵 높이({h}) 범위를 벗어났습니다.")
    if not (0 <= layer <= _MAX_LAYER):
        raise ValueError(f"layer={layer}는 0~{_MAX_LAYER} 범위여야 합니다.")


def update_tile(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """단일 타일을 수정한다.

    params: x (int), y (int), layer (int 0~5), tile_id (int)
    """
    x, y, layer, tile_id = params["x"], params["y"], params["layer"], params["tile_id"]
    _validate(map_data, x, y, layer)

    idx = _tile_index(map_data["width"], map_data["height"], x, y, layer)
    map_data["data"][idx] = tile_id
    return map_data


def update_tile_region(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """직사각형 영역을 단일 tile_id로 채운다.

    params: x1, y1, x2, y2 (포함), layer (int 0~5), tile_id (int)
    """
    x1, y1, x2, y2 = params["x1"], params["y1"], params["x2"], params["y2"]
    layer, tile_id = params["layer"], params["tile_id"]

    lx, rx = min(x1, x2), max(x1, x2)
    ty, by = min(y1, y2), max(y1, y2)

    _validate(map_data, lx, ty, layer)
    _validate(map_data, rx, by, layer)

    w, h = map_data["width"], map_data["height"]
    for y in range(ty, by + 1):
        for x in range(lx, rx + 1):
            idx = _tile_index(w, h, x, y, layer)
            map_data["data"][idx] = tile_id

    return map_data


def fill_map_layer(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """맵의 레이어 전체를 테마 타일로 채운다.

    params:
        layer (int 0~5): 채울 레이어 (기본: 0)
        theme (str): "field" | "town" | "dungeon" | "indoor" | "desert"
        tile_id (int, 선택): 직접 지정 시 theme 무시
    """
    layer = params.get("layer", 0)
    if not (0 <= layer <= _MAX_LAYER):
        raise ValueError(f"layer={layer}는 0~{_MAX_LAYER} 범위여야 합니다.")

    tile_id = params.get("tile_id")
    if tile_id is None:
        theme = params.get("theme", "field")
        tile_id = THEME_TILE.get(theme, TILE_A2_GRASS)

    w, h = map_data["width"], map_data["height"]
    start = layer * w * h
    end = start + w * h
    for i in range(start, end):
        map_data["data"][i] = tile_id

    return map_data
