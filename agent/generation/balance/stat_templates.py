"""직업별 스탯 곡선 템플릿 및 Classes.json params 생성 알고리즘."""

import math

CLASS_STAT_TEMPLATE: dict[str, dict[str, tuple[int, int]]] = {
    "warrior": {
        "mhp": (180, 2500),
        "mmp": (60, 800),
        "atk": (18, 280),
        "def": (10, 150),
        "mat": (8, 135),
        "mdf": (8, 110),
        "agi": (9, 110),
        "luk": (8, 80),
    },
    "mage": {
        "mhp": (130, 1600),
        "mmp": (100, 1400),
        "atk": (10, 140),
        "def": (6, 90),
        "mat": (18, 280),
        "mdf": (12, 160),
        "agi": (10, 120),
        "luk": (9, 90),
    },
    "healer": {
        "mhp": (150, 2000),
        "mmp": (90, 1200),
        "atk": (10, 150),
        "def": (8, 120),
        "mat": (14, 200),
        "mdf": (14, 200),
        "agi": (9, 110),
        "luk": (10, 100),
    },
    "thief": {
        "mhp": (140, 1800),
        "mmp": (50, 700),
        "atk": (15, 220),
        "def": (7, 110),
        "mat": (8, 100),
        "mdf": (8, 100),
        "agi": (18, 280),
        "luk": (15, 200),
    },
    "archer": {
        "mhp": (145, 1900),
        "mmp": (55, 750),
        "atk": (16, 240),
        "def": (7, 105),
        "mat": (9, 120),
        "mdf": (9, 115),
        "agi": (15, 230),
        "luk": (12, 160),
    },
    "default": {
        "mhp": (150, 2000),
        "mmp": (70, 1000),
        "atk": (14, 200),
        "def": (8, 120),
        "mat": (12, 160),
        "mdf": (8, 120),
        "agi": (10, 140),
        "luk": (9, 90),
    },
}

STAT_ORDER = ["mhp", "mmp", "atk", "def", "mat", "mdf", "agi", "luk"]


def generate_class_params(stat_lv1: int, stat_lv99: int, growth: str = "linear") -> list[int]:
    """레벨 0~99 스탯 배열 생성 (100개 정수). 인덱스 0은 레벨 1에 해당."""
    result = []
    for lv in range(100):
        t = lv / 99 if lv > 0 else 0
        if growth == "accelerate":
            t = t**2
        elif growth == "decelerate":
            t = math.sqrt(t)
        value = int(stat_lv1 + (stat_lv99 - stat_lv1) * t)
        result.append(value)
    return result


def build_params_2d(role: str) -> list[list[int]]:
    """8×100 params 2D 배열 생성."""
    template = CLASS_STAT_TEMPLATE.get(role, CLASS_STAT_TEMPLATE["default"])
    params_2d = []
    for stat in STAT_ORDER:
        lv1, lv99 = template[stat]
        growth = "accelerate" if stat in ("mhp", "mmp") else "linear"
        params_2d.append(generate_class_params(lv1, lv99, growth=growth))
    return params_2d  # [8][100]
