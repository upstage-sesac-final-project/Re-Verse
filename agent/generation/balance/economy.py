"""아이템 가격, 골드 경제 가이드라인."""

ITEM_PRICE_GUIDE: dict[str, dict] = {
    "HP포션(소)": {"price": 80, "hp_rate": 30, "hp_flat": 20},
    "HP포션": {"price": 150, "hp_rate": 50, "hp_flat": 30},
    "HP포션(대)": {"price": 300, "hp_rate": 80, "hp_flat": 0},
    "MP포션(소)": {"price": 60, "mp_rate": 30, "mp_flat": 0},
    "MP포션": {"price": 120, "mp_rate": 50, "mp_flat": 0},
}

DAMAGE_FORMULA_GUIDE: dict[str, str] = {
    "single_atk": "a.atk * 2 - b.def",
    "aoe_atk": "a.atk * 0.8 - b.def",
    "strong_single": "a.atk * 3 - b.def * 0.5",
    "magic_single": "a.mat * 2.5 - b.mdf",
    "magic_aoe": "a.mat * 1.2 - b.mdf",
    "heal_single": "a.mat * 1.5 + 50",
    "heal_aoe": "a.mat * 0.8 + 30",
}

MP_COST_GUIDE: dict[str, int] = {
    "single_atk": 8,
    "aoe_atk": 15,
    "strong_single": 20,
    "heal_single": 10,
    "heal_aoe": 20,
    "buff": 5,
}
