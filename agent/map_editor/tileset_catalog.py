"""RPG Maker MZ 표준 타일셋 이미지별 tile_id 카탈로그.

데이터 출처:
- MZ_SampleMap 42개 맵 실측 분석 (layer별 상위 tile_id)
- RPG Maker MZ 타일 ID 레이아웃 규칙
  · A5: 1536+ (8열 그리드, 열당 8 ID 간격)
  · A1: 2048+ (애니메이션 오토타일, 48 ID 간격)
  · A2: 2816+ (지면 오토타일, 48 ID 간격)
  · A3: 4352+ (건물 지붕, 48 ID 간격)
  · A4: 5888+ (건물 벽/던전 바닥, 48 ID 간격)
  · B~E: 0~1535 (오브젝트 시트, 열당 1 ID)

각 항목: { "시각적 설명": (tile_id, layer) }
  layer=0: 바닥(레이어 0)에 배치
  layer=1: 오브젝트(레이어 1)에 배치
"""

from typing import NamedTuple


class TileEntry(NamedTuple):
    tile_id: int
    layer: int  # 권장 배치 레이어 (0=바닥, 1=오브젝트)
    desc_en: str  # 영문 설명 (참고용)


# ── 타일셋 이미지별 카탈로그 ────────────────────────────────────────────────
# key: tilesetNames 배열에 들어오는 파일명 (확장자 없음)

_RAW: dict[str, dict[str, TileEntry]] = {
    # ── World (세계) ────────────────────────────────────────────────────────
    "World_A1": {
        "바다": TileEntry(2048, 0, "sea"),
        "강": TileEntry(2096, 0, "river"),
        "얕은물": TileEntry(2144, 0, "shallow water"),
    },
    "World_A2": {
        "풀밭": TileEntry(2816, 0, "grass"),
        "모래": TileEntry(2864, 0, "sand/desert"),
        "흙": TileEntry(2912, 0, "dirt"),
        "눈": TileEntry(2960, 0, "snow"),
        "절벽": TileEntry(3200, 0, "cliff"),
        "돌길": TileEntry(3584, 0, "stone path"),
    },
    "World_B": {
        "산": TileEntry(32, 1, "mountain"),
        "나무": TileEntry(3, 1, "tree"),
    },
    "World_C": {
        "마을": TileEntry(256, 1, "town marker"),
        "성": TileEntry(264, 1, "castle"),
    },
    # ── Outside (외부) ──────────────────────────────────────────────────────
    # Steam 원본 txt 기준 slot 번호 (각 48 ID 간격, base=2048)
    "Outside_A1": {
        "깊은물": TileEntry(2048, 0, "water A meadow"),  # slot 0
        "연못": TileEntry(2096, 0, "pond"),  # slot 1
        "수초A": TileEntry(2144, 0, "swamp grass A"),  # slot 2
        "물_항구": TileEntry(2624, 0, "water E port"),  # slot 12 (실측 top)
        "폭포A": TileEntry(2288, 0, "waterfall A"),  # slot 5
        "독늪": TileEntry(2720, 0, "poison swamp"),  # slot 14
    },
    # Steam 원본 txt 기준 slot 번호 (각 48 ID 간격, base=2816)
    "Outside_A2": {
        "풀밭": TileEntry(2816, 0, "meadow"),  # slot 0 ✓
        "흙_풀밭": TileEntry(2864, 0, "dirt on meadow"),  # slot 1
        "길_풀밭": TileEntry(2912, 0, "road meadow"),  # slot 2
        "돌바닥A": TileEntry(2960, 0, "cobblestones A"),  # slot 3
        "흙": TileEntry(3200, 0, "dirt"),  # slot 8
        "모래": TileEntry(3584, 0, "sand"),  # slot 16
        "길_모래": TileEntry(3680, 0, "road sand"),  # slot 18
        "돌바닥B": TileEntry(3728, 0, "cobblestones B"),  # slot 19 (실측 top)
        "눈": TileEntry(3968, 0, "snow"),  # slot 24
        "흙_눈": TileEntry(4016, 0, "dirt snow"),  # slot 25
        "단차": TileEntry(4304, 0, "ledge/cliff"),  # slot 31
    },
    "Outside_A3": {
        "지붕_갈색": TileEntry(4352, 0, "brown roof"),
        "지붕_적색": TileEntry(4400, 0, "red roof"),
        "지붕_파란색": TileEntry(4448, 0, "blue roof"),
    },
    "Outside_A4": {
        "건물벽": TileEntry(5888, 0, "building wall"),
        "건물벽2": TileEntry(5936, 0, "building wall 2"),
    },
    "Outside_A5": {
        "돌벽": TileEntry(1536, 0, "stone wall"),
        "나무벽": TileEntry(1544, 0, "wood wall"),
        "벽돌": TileEntry(1552, 0, "brick"),
    },
    "Outside_B": {
        "나무": TileEntry(3521, 1, "tree"),  # 실측 top1 (outdoor layer1)
        "바위": TileEntry(3008, 1, "rock"),  # 실측 top2
        "수풀": TileEntry(3032, 1, "bush"),  # 실측 top3
        "울타리": TileEntry(3520, 1, "fence"),  # 실측 top4
        "건물벽": TileEntry(3137, 1, "building wall"),  # 실측 top4
        "문": TileEntry(3024, 1, "door"),
        "계단": TileEntry(3036, 1, "stairs"),
        "가로등": TileEntry(3905, 1, "lamp post"),  # 실측 top7
    },
    "Outside_C": {
        "꽃": TileEntry(256, 1, "flower"),
        "풀": TileEntry(260, 1, "grass decoration"),
        "버섯": TileEntry(264, 1, "mushroom"),
    },
    # ── Inside (내부) ───────────────────────────────────────────────────────
    "Inside_A1": {
        "물": TileEntry(2048, 0, "water"),
    },
    "Inside_A2": {
        "나무바닥": TileEntry(2816, 0, "wood floor"),
        "돌바닥": TileEntry(2864, 0, "stone floor"),
    },
    "Inside_A4": {
        "벽": TileEntry(5888, 0, "wall"),
        "벽2": TileEntry(5936, 0, "wall 2"),
        "천장": TileEntry(6880, 0, "ceiling"),  # 실측 top2 (indoor)
        "기둥": TileEntry(6784, 0, "pillar"),  # 실측 top3
    },
    "Inside_A5": {
        "나무바닥": TileEntry(1536, 0, "wood floor"),  # 실측 압도적 top1 (indoor)
        "타일바닥": TileEntry(1544, 0, "tile floor"),
        "카펫": TileEntry(1552, 0, "carpet"),
        "돌바닥": TileEntry(1560, 0, "stone floor"),
    },
    "Inside_B": {
        "가구": TileEntry(3568, 1, "furniture"),  # 실측 top1 (indoor layer1)
        "선반": TileEntry(3578, 1, "shelf"),  # 실측 top2
        "상자": TileEntry(3569, 1, "chest"),
        "침대": TileEntry(3575, 1, "bed"),
        "탁자": TileEntry(3579, 1, "table"),
        "의자": TileEntry(3581, 1, "chair"),
    },
    "Inside_C": {
        "벽장식": TileEntry(3195, 1, "wall decoration"),  # 실측 top4
        "그림": TileEntry(3197, 1, "painting"),
        "촛대": TileEntry(256, 1, "candle"),
    },
    # ── Dungeon (던전) ──────────────────────────────────────────────────────
    "Dungeon_A1": {
        "물A": TileEntry(2048, 0, "water A"),
        "깊은물": TileEntry(2096, 0, "deep water"),
        "수초": TileEntry(2144, 0, "swamp grass"),
        "수련": TileEntry(2192, 0, "lotus pads"),
        "용암": TileEntry(2240, 0, "lava"),  # Steam 원본: slot 4
        "폭포_용암": TileEntry(2288, 0, "waterfall lava cave"),
        "물D_암굴": TileEntry(2528, 0, "water D rock cave"),  # 실측 top (dungeon)
    },
    "Dungeon_A2": {
        "던전벽": TileEntry(3104, 1, "dungeon wall"),  # 실측 압도적 top1 (dungeon layer1)
        "벽상단": TileEntry(3120, 1, "wall top"),  # 실측 top2
        "벽하단": TileEntry(3132, 1, "wall bottom"),  # 실측 top5
        "벽좌측": TileEntry(3128, 1, "wall left"),  # 실측 top3
        "벽우측": TileEntry(3124, 1, "wall right"),  # 실측 top4
        "기둥": TileEntry(3144, 1, "pillar"),  # 실측 top6
        "모서리벽": TileEntry(3108, 1, "corner wall"),
    },
    "Dungeon_A4": {
        "던전바닥": TileEntry(5888, 0, "dungeon floor"),  # 실측 압도적 top1
        "던전바닥2": TileEntry(5936, 0, "dungeon floor 2"),  # 실측 top2
        "특수바닥": TileEntry(7760, 0, "special floor"),  # 실측 top4 (dungeon)
        "어두운바닥": TileEntry(5984, 0, "dark floor"),  # 실측 top8
    },
    "Dungeon_A5": {
        "돌": TileEntry(1568, 0, "stone"),  # 실측 top5 (dungeon)
        "돌2": TileEntry(1572, 0, "stone 2"),  # 실측 top7
    },
    "Dungeon_B": {
        "횃불": TileEntry(3, 1, "torch"),
        "보물상자": TileEntry(11, 1, "treasure chest"),
        "해골": TileEntry(19, 1, "skull"),
        "제단": TileEntry(27, 1, "altar"),
        "계단_위": TileEntry(35, 1, "stairs up"),
        "계단_아래": TileEntry(43, 1, "stairs down"),
    },
    "Dungeon_C": {
        # Steam 원본: Decorative Pillar A~H (slot 0~7), 각 tile_id=256+slot*4
        "기둥_돌A": TileEntry(256, 1, "decorative pillar stone A"),
        "기둥_돌B": TileEntry(257, 1, "decorative pillar stone B"),
        "기둥_유적": TileEntry(258, 1, "decorative pillar temple"),
        "기둥_암굴": TileEntry(259, 1, "decorative pillar rock cave"),
        "기둥_마왕성": TileEntry(260, 1, "decorative pillar demon castle"),
    },
    # ── SF Outside (SF 외부) ────────────────────────────────────────────────
    "SF_Outside_A3": {
        "금속지붕": TileEntry(4352, 0, "metal roof"),
        "유리지붕": TileEntry(4400, 0, "glass roof"),
    },
    "SF_Outside_A4": {
        "콘크리트벽": TileEntry(5888, 0, "concrete wall"),
        "금속벽": TileEntry(5936, 0, "metal wall"),
    },
    "SF_Outside_A5": {
        "콘크리트": TileEntry(1536, 0, "concrete"),
        "금속판": TileEntry(1544, 0, "metal plate"),
    },
    "SF_Outside_B": {
        "기계": TileEntry(3, 1, "machine"),
        "파이프": TileEntry(11, 1, "pipe"),
        "안테나": TileEntry(19, 1, "antenna"),
    },
    "SF_Outside_C": {
        "전선": TileEntry(256, 1, "wire"),
        "표지판": TileEntry(260, 1, "sign"),
    },
    # ── SF Inside (SF 내부) ─────────────────────────────────────────────────
    "SF_Inside_A4": {
        "금속벽": TileEntry(5888, 0, "metal wall"),
        "패널벽": TileEntry(5936, 0, "panel wall"),
    },
    "SF_Inside_A5": {
        "금속바닥": TileEntry(1536, 0, "metal floor"),
        "격자바닥": TileEntry(1544, 0, "grid floor"),
    },
    "SF_Inside_B": {
        "컴퓨터": TileEntry(3, 1, "computer"),
        "서버": TileEntry(11, 1, "server rack"),
        "캡슐": TileEntry(19, 1, "capsule"),
    },
    "SF_Inside_C": {
        "홀로그램": TileEntry(256, 1, "hologram"),
        "패널": TileEntry(260, 1, "panel"),
    },
}


def get_tiles_for_images(image_names: list[str]) -> dict[str, list[dict]]:
    """tilesetNames 이미지 목록으로 사용 가능한 타일 카탈로그를 반환한다.

    반환 형식:
        {
            "layer0": [{"name": "풀밭", "tile_id": 2816}, ...],
            "layer1": [{"name": "나무", "tile_id": 3521}, ...],
        }
    """
    layer0: list[dict] = []
    layer1: list[dict] = []

    for img in image_names:
        if not img:
            continue
        entries = _RAW.get(img, {})
        for name, entry in entries.items():
            item = {"name": name, "tile_id": entry.tile_id, "image": img}
            if entry.layer == 0:
                layer0.append(item)
            else:
                layer1.append(item)

    return {"layer0": layer0, "layer1": layer1}


def format_catalog_for_prompt(image_names: list[str]) -> str:
    """LLM 프롬프트에 삽입할 타일 카탈로그 텍스트를 생성한다."""
    catalog = get_tiles_for_images(image_names)

    lines: list[str] = []

    if catalog["layer0"]:
        lines.append("Layer 0 (바닥):")
        for t in catalog["layer0"]:
            lines.append(f"  {t['name']}: tile_id={t['tile_id']}")

    if catalog["layer1"]:
        lines.append("Layer 1 (오브젝트):")
        for t in catalog["layer1"]:
            lines.append(f"  {t['name']}: tile_id={t['tile_id']}")

    return "\n".join(lines) if lines else "카탈로그 없음"
