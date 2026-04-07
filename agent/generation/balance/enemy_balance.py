"""적 티어별 스탯 범위 및 난이도 보정."""

import random

ENEMY_STAT_GUIDE: dict[str, dict] = {
    "weak": {
        "hp": (60, 100),
        "mp": (10, 30),
        "atk": (8, 13),
        "def": (2, 5),
        "mat": (5, 10),
        "mdf": (2, 5),
        "agi": (5, 10),
        "luk": (3, 8),
        "exp": (25, 55),
        "gold": (10, 30),
    },
    "normal": {
        "hp": (120, 200),
        "mp": (20, 60),
        "atk": (13, 20),
        "def": (4, 9),
        "mat": (10, 18),
        "mdf": (4, 9),
        "agi": (8, 14),
        "luk": (5, 12),
        "exp": (55, 100),
        "gold": (25, 60),
    },
    "elite": {
        "hp": (300, 500),
        "mp": (50, 120),
        "atk": (20, 30),
        "def": (10, 15),
        "mat": (18, 28),
        "mdf": (10, 15),
        "agi": (12, 20),
        "luk": (8, 15),
        "exp": (200, 400),
        "gold": (80, 200),
    },
    "boss": {
        "hp": (1800, 4000),
        "mp": (200, 500),
        "atk": (30, 45),
        "def": (15, 25),
        "mat": (25, 40),
        "mdf": (15, 25),
        "agi": (15, 25),
        "luk": (10, 20),
        "exp": (1000, 3000),
        "gold": (500, 1500),
    },
}

DIFFICULTY_MULTIPLIER: dict[str, dict[str, float]] = {
    "easy": {"enemy_hp": 0.7, "enemy_atk": 0.7, "exp": 1.5, "gold": 1.5},
    "normal": {"enemy_hp": 1.0, "enemy_atk": 1.0, "exp": 1.0, "gold": 1.0},
    "hard": {"enemy_hp": 1.5, "enemy_atk": 1.3, "exp": 0.7, "gold": 0.7},
}


def generate_enemy_params(tier: str, difficulty: str = "normal") -> list[int]:
    """티어 + 난이도 기반 적 스탯 [HP, MP, ATK, DEF, MAT, MDF, AGI, LUK] 생성."""
    guide = ENEMY_STAT_GUIDE.get(tier, ENEMY_STAT_GUIDE["normal"])
    mult = DIFFICULTY_MULTIPLIER.get(difficulty, DIFFICULTY_MULTIPLIER["normal"])

    def rnd(key: str, hp_mult: bool = False) -> int:
        lo, hi = guide[key]
        val = random.randint(lo, hi)
        if hp_mult:
            val = int(val * mult.get("enemy_hp", 1.0))
        elif key == "atk":
            val = int(val * mult.get("enemy_atk", 1.0))
        return val

    return [
        rnd("hp", hp_mult=True),
        rnd("mp"),
        rnd("atk"),
        rnd("def"),
        rnd("mat"),
        rnd("mdf"),
        rnd("agi"),
        rnd("luk"),
    ]
