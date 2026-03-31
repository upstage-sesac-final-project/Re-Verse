"""Zone-based 맵 페인터.

LLM이 출력한 zone spec을 받아 layer 0을 자연스럽게 채운다.

Zone spec 형식:
    [
        {"type": "grass", "x1": 0, "y1": 0, "x2": 16, "y2": 12},
        {"type": "water", "x1": 0, "y1": 0, "x2": 3, "y2": 12},
        {"type": "path",  "x1": 7, "y1": 0, "x2": 9, "y2": 12},
    ]

처리 순서:
  1. 각 셀에 zone 카테고리 배정 (나중에 선언된 zone이 우선)
  2. 카테고리 → tile_id 변환 (tilesetId 기반)
  3. 경계 셀: 이웃 카테고리와 인접 불가이면 transition 카테고리로 교체
  4. layer 0 data 배열에 쓰기
"""

from typing import Any

from agent.map_editor.wfc.autotile import apply_autotile_shapes
from agent.map_editor.wfc.rules import (
    THEME_BASE_CATEGORY,
    can_be_adjacent,
    get_tile_id,
)

# ── transition 규칙: (from_cat, to_cat) → 경계에서 쓸 카테고리 ───────────────
# 인접 불가 조합 사이에 삽입할 전이 카테고리.
# 없으면 from_cat 유지.
_TRANSITION: dict[frozenset, str] = {
    frozenset({"grass", "water"}): "grass",  # 물-풀 직접 접촉: 풀 우선
    frozenset({"grass", "cliff"}): "grass",
    frozenset({"dungeon_floor", "cliff"}): "dungeon_floor",
    frozenset({"dungeon_floor2", "cliff"}): "dungeon_floor2",
    frozenset({"sand", "cliff"}): "sand",
    frozenset({"snow", "dirt"}): "snow",
    frozenset({"wood_floor", "dungeon_floor"}): "wood_floor",
}

_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 4방향


def _resolve_transition(cell_cat: str, neighbor_cat: str) -> str:
    """인접 불가 조합의 transition 카테고리를 반환한다."""
    key = frozenset({cell_cat, neighbor_cat})
    if key in _TRANSITION:
        return _TRANSITION[key]
    # 기본: cell_cat 유지 (경계면 그냥 덮어씀)
    return cell_cat


def _build_category_grid(
    width: int,
    height: int,
    zones: list[dict[str, Any]],
    base_category: str,
) -> list[list[str]]:
    """zone spec으로 카테고리 그리드(2D)를 만든다.

    나중에 선언된 zone이 앞선 zone을 덮어쓴다.
    """
    grid: list[list[str]] = [[base_category] * width for _ in range(height)]

    for zone in zones:
        cat = zone.get("type", base_category)
        x1 = max(0, int(zone.get("x1", 0)))
        y1 = max(0, int(zone.get("y1", 0)))
        x2 = min(width - 1, int(zone.get("x2", width - 1)))
        y2 = min(height - 1, int(zone.get("y2", height - 1)))

        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                grid[y][x] = cat

    return grid


def _smooth_boundaries(grid: list[list[str]], width: int, height: int) -> list[list[str]]:
    """인접 불가 경계를 transition 카테고리로 교체한다.

    반복 횟수: 1회 (단순 경계 처리만 필요).
    """
    result = [row[:] for row in grid]  # 복사

    for y in range(height):
        for x in range(width):
            cat = grid[y][x]
            for dy, dx in _DIRS:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    neighbor = grid[ny][nx]
                    if not can_be_adjacent(cat, neighbor):
                        result[y][x] = _resolve_transition(cat, neighbor)
                        break  # 한 방향만 체크하면 충분

    return result


def generate_map_from_zones(
    map_data: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    """zone spec으로 map_data의 layer 0을 채운다.

    params:
        zones (list[dict]): zone spec 목록
        theme (str, 선택): 기본 배경 테마 ("field"|"dungeon"|"indoor"|...)
        base_category (str, 선택): theme 없을 때 기본 카테고리 직접 지정
        smooth (bool, 선택): 경계 smoothing 여부 (기본 True)

    Returns:
        수정된 map_data
    """
    width: int = map_data["width"]
    height: int = map_data["height"]
    tileset_id: int = map_data.get("tilesetId", 2)

    zones: list[dict[str, Any]] = params.get("zones", [])
    theme: str | None = params.get("theme")
    smooth: bool = params.get("smooth", True)

    # 기본 배경 카테고리 결정
    base_category = params.get("base_category") or THEME_BASE_CATEGORY.get(theme or "", "grass")

    # zone spec의 theme→category 정규화
    normalized_zones = []
    for z in zones:
        ztype = z.get("type", "")
        # "field"/"town" 같은 theme 이름을 카테고리로 변환
        if ztype in THEME_BASE_CATEGORY:
            ztype = THEME_BASE_CATEGORY[ztype]
        normalized_zones.append({**z, "type": ztype})

    # 카테고리 그리드 생성
    grid = _build_category_grid(width, height, normalized_zones, base_category)

    # 경계 smoothing
    if smooth:
        grid = _smooth_boundaries(grid, width, height)

    # tile_id 변환 → layer 0 data 배열 업데이트
    for y in range(height):
        for x in range(width):
            cat = grid[y][x]
            tile_id = get_tile_id(cat, tileset_id)
            if tile_id > 0:
                map_data["data"][y * width + x] = tile_id

    # 오토타일 shape 보정 (A1/A2 경계 자연스럽게)
    layer0 = map_data["data"][: width * height]
    corrected = apply_autotile_shapes(layer0, width, height)
    map_data["data"][: width * height] = corrected

    return map_data


def describe_zones(zones: list[dict[str, Any]], width: int, height: int) -> str:
    """zone spec을 사람이 읽기 쉬운 텍스트로 요약한다."""
    if not zones:
        return "zone 없음 (기본 배경만 사용)"
    lines = []
    for z in zones:
        x1, y1 = z.get("x1", 0), z.get("y1", 0)
        x2, y2 = z.get("x2", width - 1), z.get("y2", height - 1)
        lines.append(f"  {z.get('type', '?'):15s} ({x1},{y1})→({x2},{y2})")
    return "\n".join(lines)
