"""타일 data 배열 수정 연산.

RPG Maker MZ 타일 인덱스 공식:
    index = layer * (width * height) + y * width + x

레이어 0~3 (총 4개), 각 레이어는 width*height 개의 타일 ID를 가진다.
"""

from typing import Any


def _tile_index(width: int, height: int, x: int, y: int, layer: int) -> int:
    return layer * (width * height) + y * width + x


def _validate(map_data: dict[str, Any], x: int, y: int, layer: int) -> None:
    w, h = map_data["width"], map_data["height"]
    if not (0 <= x < w):
        raise ValueError(f"x={x}가 맵 너비({w}) 범위를 벗어났습니다.")
    if not (0 <= y < h):
        raise ValueError(f"y={y}가 맵 높이({h}) 범위를 벗어났습니다.")
    if not (0 <= layer <= 3):
        raise ValueError(f"layer={layer}는 0~3 범위여야 합니다.")


def update_tile(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """단일 타일을 수정한다.

    params: x (int), y (int), layer (int, 0~3), tile_id (int)
    """
    x, y, layer, tile_id = params["x"], params["y"], params["layer"], params["tile_id"]
    _validate(map_data, x, y, layer)

    idx = _tile_index(map_data["width"], map_data["height"], x, y, layer)
    map_data["data"][idx] = tile_id
    return map_data


def update_tile_region(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """직사각형 영역을 단일 타일 ID로 채운다.

    params: x1, y1, x2, y2 (포함), layer (int, 0~3), tile_id (int)
    """
    x1, y1, x2, y2 = params["x1"], params["y1"], params["x2"], params["y2"]
    layer, tile_id = params["layer"], params["tile_id"]

    # 범위 정규화 (역순 입력 허용)
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
