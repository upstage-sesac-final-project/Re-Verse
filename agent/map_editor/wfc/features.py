"""Feature Registry — kind → 생성 알고리즘 + 맵 합성 로직.

Feature spec 형식 (LLM이 출력):
    {
        "background": "grass",      # 기본 배경 카테고리
        "features": [
            {
                "kind": "river",    # 알고리즘 종류
                "tile": "water",    # 배치할 카테고리
                "from_edge": "top",
                "to_edge": "bottom",
                "from_ratio": 0.25,
                "to_ratio": 0.6,
                "width": 3
            },
            {
                "kind": "road",
                "tile": "path",
                "from_edge": "top",
                "to_edge": "bottom",
                "from_ratio": 0.65,
                "to_ratio": 0.65,
                "width": 2
            },
            {
                "kind": "biome",
                "tile": "sand",
                "coverage": 0.2
            }
        ]
    }

kind 목록:
    river  — 구불구불한 강 (Random Walk)
    road   — 완만한 곡선 길 (Random Walk, 낮은 roughness)
    biome  — 지형 패치 분포 (Voronoi)
    fill   — 직사각형 채우기 (실내 방/구역, x1/y1/x2/y2 필수)
"""

from __future__ import annotations

import random
from typing import Any

from agent.map_editor.wfc.autotile import apply_autotile_shapes
from agent.map_editor.wfc.generators import biome as biome_gen
from agent.map_editor.wfc.generators import river as river_gen
from agent.map_editor.wfc.generators import road as road_gen
from agent.map_editor.wfc.rules import THEME_BASE_CATEGORY, get_tile_id

# ── kind → generator 함수 매핑 ────────────────────────────────────────────────
# 각 generator: generate(width, height, params, rng) → set[tuple[int,int]]
_REGISTRY: dict[str, Any] = {
    "river": river_gen.generate,
    "stream": river_gen.generate,  # stream = river alias
    "lake": biome_gen.generate,  # lake ≈ biome patch (water)
    "road": road_gen.generate,
    "path": road_gen.generate,  # path = road alias
    "biome": biome_gen.generate,
    "terrain": biome_gen.generate,
    "patch": biome_gen.generate,
}

# fill은 별도 처리 (생성기 함수 없음)


def _apply_fill(
    width: int,
    height: int,
    params: dict,
) -> set[tuple[int, int]]:
    """직사각형 채우기 (실내 방, 고정 구역)."""
    x1 = max(0, int(params.get("x1", 0)))
    y1 = max(0, int(params.get("y1", 0)))
    x2 = min(width - 1, int(params.get("x2", width - 1)))
    y2 = min(height - 1, int(params.get("y2", height - 1)))
    return {(x, y) for y in range(y1, y2 + 1) for x in range(x1, x2 + 1)}


def apply_features(
    map_data: dict[str, Any],
    feature_spec: dict[str, Any],
    rng_seed: int | None = None,
) -> dict[str, Any]:
    """feature spec으로 map_data layer 0을 채운다.

    Args:
        map_data:     RPG Maker MZ 맵 dict (width/height/data/tilesetId)
        feature_spec: {"background": str, "features": list[dict]}
        rng_seed:     재현 가능한 결과를 원할 때 시드 지정

    Returns:
        수정된 map_data
    """
    width: int = map_data["width"]
    height: int = map_data["height"]
    tileset_id: int = map_data.get("tilesetId", 2)
    rng = random.Random(rng_seed)

    # ── 배경 채우기 ────────────────────────────────────────────────────────────
    raw_bg = feature_spec.get("background", "grass")
    # theme 이름이 들어온 경우 카테고리로 변환
    background = THEME_BASE_CATEGORY.get(raw_bg, raw_bg)
    bg_tile = get_tile_id(background, tileset_id)

    if bg_tile > 0:
        base_size = width * height
        for i in range(base_size):
            map_data["data"][i] = bg_tile

    # ── feature 순서대로 합성 (나중 feature가 위에 그려짐) ───────────────────
    features: list[dict] = feature_spec.get("features", [])

    for feat in features:
        kind = feat.get("kind", "").lower()
        raw_tile = feat.get("tile", background)
        tile_cat = THEME_BASE_CATEGORY.get(raw_tile, raw_tile)
        tile_id = get_tile_id(tile_cat, tileset_id)

        if tile_id <= 0:
            continue  # 해당 tilesetId에 없는 카테고리 → 건너뜀

        # 셀 집합 계산
        if kind in ("fill", "rect", "rectangle"):
            cells = _apply_fill(width, height, feat)
        else:
            generator = _REGISTRY.get(kind)
            if generator is None:
                # 알 수 없는 kind → biome으로 fallback
                generator = biome_gen.generate
            cells = generator(width, height, feat, rng)

        # layer 0에 기록
        for x, y in cells:
            if 0 <= x < width and 0 <= y < height:
                map_data["data"][y * width + x] = tile_id

    # ── 오토타일 shape 보정 (A1/A2 경계 자연스럽게) ───────────────────────────
    layer0 = map_data["data"][: width * height]
    corrected = apply_autotile_shapes(layer0, width, height)
    map_data["data"][: width * height] = corrected

    return map_data
