"""타일 data 배열 수정 연산.

RPG Maker MZ 타일 인덱스 공식:
    index = layer * (width * height) + y * width + x

레이어 0~5 (총 6개), 각 레이어는 width*height 개의 타일 ID를 가진다.

## 타일 ID 체계
- 0        : 빈 타일
- 1~47     : 리전 ID (Region)
- 48~255   : 그림자/오버레이
- 256~1535 : B-타일 (오브젝트 시트)
- 1536~2047: C-타일 (실내 바닥 등)
- 2048~2815: A1/A2 오토타일 (물, 풀밭 등)
- 2816~4095: A3/A4/A5 오토타일 (건물, 절벽, 지면 등)
- 4096+    : 애니메이션 오토타일 (물결, 용암 등)
"""

from typing import Any

# ── 단일 타일 ID 상수 (자주 쓰이는 기준값) ──────────────────────────────────
# tilesetId 1 (세계) 기준
TILE_WORLD_FLOOR: int = 2816  # 세계맵 기본 바닥
TILE_WORLD_GRASS: int = 2432  # 세계맵 풀밭

# tilesetId 2 (외부/Outside) 기준 — MZ_SampleMap 분석값
TILE_OUTSIDE_FLOOR: int = 2816  # 야외 기본 바닥 (풀밭)
TILE_OUTSIDE_PATH: int = 3584  # 돌길/흙길 (sample top1)
TILE_OUTSIDE_CLIFF: int = 3200  # 절벽/외벽
TILE_OUTSIDE_WATER: int = 2624  # 수면

# tilesetId 3 (내부/Inside) 기준 — MZ_SampleMap 분석값
TILE_INSIDE_FLOOR: int = 1536  # 실내 기본 바닥 (sample/game 압도적 1위)

# tilesetId 4 (던전/Dungeon) 기준 — MZ_SampleMap 분석값
TILE_DUNGEON_FLOOR: int = 5888  # 던전 바닥 (sample 압도적 1위)
TILE_DUNGEON_FLOOR2: int = 5936  # 던전 바닥 변형
TILE_DUNGEON_WALL: int = 3104  # 던전 벽/기둥 (layer1 압도적 1위)

# ── tilesetId별 레이어0 기본 타일 ────────────────────────────────────────────
# 각 항목: {"floor": int, ...} — MZ_SampleMap + game_001 실측값 기반
BASE_TILE: dict[int, dict[str, int]] = {
    1: {  # 세계 (World)
        "floor": TILE_WORLD_FLOOR,
    },
    2: {  # 외부 (Outside) — 야외, 마을, 숲
        "floor": TILE_OUTSIDE_FLOOR,
        "path": TILE_OUTSIDE_PATH,
        "cliff": TILE_OUTSIDE_CLIFF,
        "water": TILE_OUTSIDE_WATER,
    },
    3: {  # 내부 (Inside) — 가옥, 상점, 여관
        "floor": TILE_INSIDE_FLOOR,
    },
    4: {  # 던전 (Dungeon) — 동굴, 탑
        "floor": TILE_DUNGEON_FLOOR,
        "floor2": TILE_DUNGEON_FLOOR2,
        "wall": TILE_DUNGEON_WALL,
    },
    5: {  # SF 외부 (Outside 기반)
        "floor": TILE_OUTSIDE_FLOOR,
        "path": TILE_OUTSIDE_PATH,
    },
    6: {  # SF 내부 (Inside 기반)
        "floor": TILE_INSIDE_FLOOR,
    },
}

# ── 테마 → 기본 tile_id / tilesetId 매핑 ─────────────────────────────────────
# "초원맵 만들어줘" → theme="field" → tilesetId=2, layer0=2816
THEME_TILE: dict[str, int] = {
    "field": TILE_OUTSIDE_FLOOR,  # 2816  야외 기본 바닥
    "town": TILE_OUTSIDE_FLOOR,  # 2816  마을 (야외 타일셋)
    "indoor": TILE_INSIDE_FLOOR,  # 1536  실내 바닥
    "dungeon": TILE_DUNGEON_FLOOR,  # 5888  던전 바닥
    "desert": TILE_OUTSIDE_PATH,  # 3584  사막/흙길
}

THEME_TILESET: dict[str, int] = {
    "field": 2,
    "town": 2,
    "indoor": 3,
    "dungeon": 4,
    "desert": 2,
}


def get_base_tile(tileset_id: int, surface: str = "floor") -> int:
    """tilesetId와 surface 이름으로 기본 tile_id를 반환한다.

    surface: "floor" | "path" | "cliff" | "water" | "wall" | "floor2"
    알 수 없는 조합은 해당 tileset의 "floor"를 반환.
    """
    ts = BASE_TILE.get(tileset_id, BASE_TILE[2])
    return ts.get(surface, ts["floor"])


# ── 타일 연산 ────────────────────────────────────────────────────────────────

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
    """맵의 레이어 전체를 지정 타일로 채운다.

    params:
        layer (int 0~5): 채울 레이어 (기본: 0)
        theme (str): "field" | "town" | "indoor" | "dungeon" | "desert"
        tile_id (int, 선택): 직접 지정 시 theme 무시
        tileset_id (int, 선택): theme 없이 tilesetId 기반 기본 타일 사용 시
        surface (str, 선택): "floor" | "path" | "cliff" | "wall" 등 (tileset_id와 함께 사용)
    """
    layer = params.get("layer", 0)
    if not (0 <= layer <= _MAX_LAYER):
        raise ValueError(f"layer={layer}는 0~{_MAX_LAYER} 범위여야 합니다.")

    tile_id = params.get("tile_id")
    if tile_id is None:
        theme = params.get("theme")
        if theme:
            tile_id = THEME_TILE.get(theme, TILE_OUTSIDE_FLOOR)
        else:
            tileset_id = params.get("tileset_id", 2)
            surface = params.get("surface", "floor")
            tile_id = get_base_tile(tileset_id, surface)

    w, h = map_data["width"], map_data["height"]
    start = layer * w * h
    end = start + w * h
    for i in range(start, end):
        map_data["data"][i] = tile_id

    return map_data
