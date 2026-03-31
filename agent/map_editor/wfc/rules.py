"""WFC 카테고리 정의 및 인접 규칙.

MZ_SampleMap 42개 맵 실측 분석 기반.
카테고리는 정확한 tile_id가 아닌 지형 의미 단위로 정의한다.
"""

# ── 카테고리 → tilesetId별 대표 tile_id ────────────────────────────────────
# 실제 배치 시 이 값으로 데이터를 채운다.
# key: 카테고리명, value: {tilesetId: tile_id}
CATEGORY_TILES: dict[str, dict[int, int]] = {
    # 야외(tilesetId=2) 지형 — Steam 원본 txt 기준 tile_id
    "grass": {1: 2816, 2: 2816, 5: 2816},  # Meadow (slot 0)
    "water": {2: 2048, 4: 2096},  # Outside: Water A; Dungeon: water A
    "water_anim": {2: 2624, 3: 2048},  # Outside: Water E(Port) slot 12; Inside: water
    "sand": {2: 3584},  # Sand (slot 16) — 이전엔 2864(Dirt on Meadow)
    "dirt": {2: 3200},  # Dirt (slot 8)  — 이전엔 2912(Road Meadow)
    "snow": {2: 3968},  # Snow (slot 24) — 이전엔 2960(Cobblestones A)
    "cliff": {2: 4304},  # Ledge (slot 31)— 이전엔 3200(Dirt)
    "path": {2: 2912, 3: 2960},  # Road Meadow (slot 2) — 이전엔 3584(Sand)
    "stone_floor": {2: 3728, 3: 2864},  # Cobblestones B (slot 19) — 이전엔 3968(Snow)
    "roof": {2: 4352},
    # 실내(tilesetId=3) 지형
    "wood_floor": {3: 1536, 6: 1536},
    "tile_floor": {3: 1544},
    "carpet": {3: 1552},
    "indoor_stone": {3: 1560},
    "wall_indoor": {3: 5888},
    # 던전(tilesetId=4) 지형
    "dungeon_floor": {4: 5888},
    "dungeon_floor2": {4: 5936},
    "dungeon_wall": {4: 3104},  # layer1 (벽)
    "lava": {4: 2240},  # Dungeon_A1 slot 4 (Steam 원본 확인)
    "poison": {4: 2144},  # Dungeon_A1 slot 2 (Swamp Grass)
    "dungeon_stone": {4: 1568},
    # SF(tilesetId=5/6)
    "metal_floor": {5: 1536, 6: 1536},
    "concrete": {5: 1544},
}

# ── 인접 허용 규칙 (양방향 — A→B면 B→A도 허용) ─────────────────────────────
# MZ_SampleMap 분석: 실측 인접 빈도 ≥ 10 케이스만 포함
ADJACENCY: dict[str, frozenset[str]] = {
    "grass": frozenset(
        {
            "grass",
            "water",
            "water_anim",
            "sand",
            "dirt",
            "snow",
            "cliff",
            "stone_floor",
            "path",
            "roof",
        }
    ),
    "water": frozenset({"water", "grass", "water_anim", "sand"}),
    "water_anim": frozenset({"water_anim", "water", "grass", "path", "stone_floor"}),
    "sand": frozenset({"sand", "grass", "dirt", "water", "water_anim"}),
    "dirt": frozenset({"dirt", "grass", "sand", "path"}),
    "snow": frozenset({"snow", "grass", "cliff"}),
    "cliff": frozenset(
        {"cliff", "grass", "stone_floor", "dungeon_wall", "dungeon_floor", "dungeon_floor2"}
    ),
    "path": frozenset(
        {"path", "grass", "stone_floor", "roof", "dirt", "water_anim", "dungeon_floor"}
    ),
    "stone_floor": frozenset(
        {"stone_floor", "grass", "path", "cliff", "roof", "wall_indoor", "wood_floor"}
    ),
    "roof": frozenset({"roof", "grass", "path", "stone_floor"}),
    # 실내
    "wood_floor": frozenset(
        {"wood_floor", "tile_floor", "carpet", "indoor_stone", "wall_indoor", "stone_floor"}
    ),
    "tile_floor": frozenset({"tile_floor", "wood_floor", "carpet", "wall_indoor"}),
    "carpet": frozenset({"carpet", "wood_floor", "tile_floor", "wall_indoor"}),
    "indoor_stone": frozenset({"indoor_stone", "wood_floor", "wall_indoor"}),
    "wall_indoor": frozenset(
        {"wall_indoor", "wood_floor", "tile_floor", "carpet", "indoor_stone", "stone_floor"}
    ),
    # 던전
    "dungeon_floor": frozenset(
        {
            "dungeon_floor",
            "dungeon_floor2",
            "dungeon_stone",
            "dungeon_wall",
            "cliff",
            "lava",
            "path",
        }
    ),
    "dungeon_floor2": frozenset({"dungeon_floor2", "dungeon_floor", "dungeon_wall", "cliff"}),
    "dungeon_wall": frozenset(
        {"dungeon_wall", "dungeon_floor", "dungeon_floor2", "cliff", "dungeon_stone"}
    ),
    "lava": frozenset({"lava", "dungeon_floor", "path", "poison"}),
    "poison": frozenset({"poison", "dungeon_floor", "lava"}),
    "dungeon_stone": frozenset({"dungeon_stone", "dungeon_floor", "dungeon_wall"}),
    # SF
    "metal_floor": frozenset({"metal_floor", "concrete", "wall_indoor"}),
    "concrete": frozenset({"concrete", "metal_floor", "wall_indoor"}),
}

# ── 테마 → 기본 카테고리 (레이어 0 배경) ──────────────────────────────────────
THEME_BASE_CATEGORY: dict[str, str] = {
    "field": "grass",
    "town": "grass",
    "desert": "sand",
    "snow": "snow",
    "indoor": "wood_floor",
    "dungeon": "dungeon_floor",
    "sf": "metal_floor",
}

# ── 카테고리 → 권장 tilesetId ────────────────────────────────────────────────
CATEGORY_DEFAULT_TILESET: dict[str, int] = {
    "grass": 2,
    "water": 2,
    "water_anim": 2,
    "sand": 2,
    "dirt": 2,
    "snow": 2,
    "cliff": 2,
    "path": 2,
    "stone_floor": 2,
    "roof": 2,
    "wood_floor": 3,
    "tile_floor": 3,
    "carpet": 3,
    "indoor_stone": 3,
    "wall_indoor": 3,
    "dungeon_floor": 4,
    "dungeon_floor2": 4,
    "dungeon_wall": 4,
    "lava": 4,
    "poison": 4,
    "dungeon_stone": 4,
    "metal_floor": 5,
    "concrete": 5,
}


def get_tile_id(category: str, tileset_id: int) -> int:
    """카테고리와 tilesetId로 대표 tile_id를 반환한다.

    해당 tilesetId에 매핑이 없으면 가장 가까운 tilesetId 매핑을 사용.
    매핑 자체가 없으면 0 반환.
    """
    mapping = CATEGORY_TILES.get(category, {})
    if not mapping:
        return 0
    if tileset_id in mapping:
        return mapping[tileset_id]
    # fallback: 아무 값이나 반환
    return next(iter(mapping.values()))


def can_be_adjacent(cat_a: str, cat_b: str) -> bool:
    """두 카테고리가 인접할 수 있는지 확인한다."""
    neighbors_a = ADJACENCY.get(cat_a, frozenset())
    return cat_b in neighbors_a


def compatible_categories(cat: str) -> frozenset[str]:
    """주어진 카테고리와 인접 가능한 카테고리 집합을 반환한다."""
    return ADJACENCY.get(cat, frozenset())
