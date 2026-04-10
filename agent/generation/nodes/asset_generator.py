"""C 노드 — asset_generator: LLM 6회 병렬 → Actors~Enemies.json.

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.C
canonical: docs/The_world/asset_generation.md
canonical: docs/The_world/classes_params_generation.md
"""

import asyncio
import logging
from typing import Any, cast

from pydantic import BaseModel

from agent.core.llm_client import invoke_llm
from agent.generation.models import GameSpec
from agent.generation.progress import publish_progress
from agent.generation.prompts.asset_generator_prompt import (
    build_actors_prompt,
    build_armors_prompt,
    build_classes_prompt,
    build_enemies_prompt,
    build_items_prompt,
    build_skills_prompt,
    build_weapons_prompt,
)
from agent.generation.registry.id_table import IdTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.3  # 에셋 스탯/스킬 수치 — 구조화 출력 위주, 약간의 다양성

# ── 역할 정규화 ──────────────────────────────────────────────────────────────

_ROLE_KEYWORDS: dict[str, list[str]] = {
    "warrior": ["warrior", "전사", "근접", "검사", "기사", "파이터"],
    "mage": ["mage", "마법사", "마도사", "wizard", "소서러"],
    "healer": ["healer", "힐러", "성직자", "치유", "priest", "클레릭"],
    "thief": ["thief", "도적", "ninja", "닌자", "rogue", "어쌔신"],
}


def _normalize_role(raw: str) -> str:
    lower = raw.lower()
    for role, keywords in _ROLE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return role
    return "default"


# ── Classes.json 알고리즘 params ─────────────────────────────────────────────

# maxLevel=20 기준 (lv1, lv20) — 시뮬레이션 검증 완료
# docs/The_world/BALANCE_IMPROVEMENT_PLAN.md 참조
_CLASS_STAT_TEMPLATE: dict[str, dict[str, tuple[int, int]]] = {
    "warrior": {
        "mhp": (400, 3000),
        "mmp": (30, 300),
        "atk": (15, 60),
        "def": (12, 50),
        "mat": (5, 25),
        "mdf": (8, 35),
        "agi": (10, 35),
        "luk": (8, 25),
    },
    "mage": {
        "mhp": (250, 1800),
        "mmp": (80, 800),
        "atk": (5, 20),
        "def": (6, 25),
        "mat": (15, 65),
        "mdf": (12, 50),
        "agi": (10, 35),
        "luk": (8, 25),
    },
    "healer": {
        "mhp": (350, 2500),
        "mmp": (60, 600),
        "atk": (8, 30),
        "def": (10, 40),
        "mat": (12, 50),
        "mdf": (14, 55),
        "agi": (9, 30),
        "luk": (10, 30),
    },
    "thief": {
        "mhp": (300, 2200),
        "mmp": (40, 400),
        "atk": (12, 50),
        "def": (7, 30),
        "mat": (5, 20),
        "mdf": (7, 30),
        "agi": (18, 70),
        "luk": (15, 50),
    },
    "default": {
        "mhp": (350, 2500),
        "mmp": (50, 500),
        "atk": (12, 45),
        "def": (10, 40),
        "mat": (10, 40),
        "mdf": (10, 40),
        "agi": (12, 40),
        "luk": (10, 30),
    },
}

_STAT_ORDER = ["mhp", "mmp", "atk", "def", "mat", "mdf", "agi", "luk"]


_MAX_LEVEL = 20  # 생성 게임의 최대 레벨


def _generate_class_params(lv1: int, lv_max: int, growth: str = "linear") -> list[int]:
    """lv1~lv99 값의 99개 정수 배열 생성. lv_max는 _MAX_LEVEL 시점 목표값.

    lv1~lv_MAX_LEVEL 구간에서 lv1→lv_max로 성장하고,
    lv_MAX_LEVEL 이후는 lv_max 값을 유지한다.
    """
    result = []
    for lv in range(1, 100):
        if lv <= _MAX_LEVEL:
            t = (lv - 1) / max(1, _MAX_LEVEL - 1)
        else:
            t = 1.0
        if growth == "accelerate":
            t = t * t
        val = round(lv1 + (lv_max - lv1) * t)
        result.append(val)
    assert len(result) == 99, f"params row length error: {len(result)}"
    return result


def _build_params_2d(role: str) -> list[list[int]]:
    """8 × 99 params 2D 배열 생성."""
    template = _CLASS_STAT_TEMPLATE.get(role, _CLASS_STAT_TEMPLATE["default"])
    params_2d = []
    for stat in _STAT_ORDER:
        lv1, lv_max = template[stat]
        growth = "accelerate" if stat in ("mhp", "mmp") else "linear"
        params_2d.append(_generate_class_params(lv1, lv_max, growth=growth))
    return params_2d


def _validate_exp_params(ep: list[int]) -> list[int]:
    """expParams 강제 — maxLevel=20 게임용 빠른 레벨업 곡선.

    [5,5,2,30]: 총 ~16전으로 lv1→lv20 달성 (5~15분 플레이 기준).
    LLM 출력은 무시하고 고정값 사용.
    """
    return [5, 5, 2, 30]


# ── LLM 응답 스키마 ──────────────────────────────────────────────────────────


class LlmLearning(BaseModel):
    level: int
    skillId: int


class LlmClass(BaseModel):
    id: int
    name: str
    expParams: list[int]
    learnings: list[LlmLearning]
    note: str = ""


class LlmClassList(BaseModel):
    classes: list[LlmClass]


class RpgSkillDamage(BaseModel):
    type: int = 1
    elementId: int = 0
    formula: str = "a.atk * 2 - b.def"
    variance: int = 20
    critical: bool = False


class RpgSkill(BaseModel):
    id: int
    name: str
    description: str = ""
    iconTag: str = "physical_melee"
    power: int = 5  # 0~10. 시스템이 damage.formula/mpCost 계산
    stypeId: int = 1
    scope: int = 1
    occasion: int = 1
    tpCost: int = 0
    tpGain: int = 0
    speed: int = 0
    repeats: int = 1
    successRate: int = 100
    hitType: int = 1
    messageType: int = 1
    message1: str = ""
    message2: str = ""
    requiredWtypeId1: int = 0
    requiredWtypeId2: int = 0
    damage: RpgSkillDamage = RpgSkillDamage()
    effects: list[dict] = []
    note: str = ""


class SkillListOutput(BaseModel):
    items: list[RpgSkill]


class RpgItemDamage(BaseModel):
    type: int = 0
    elementId: int = -1
    formula: str = "0"
    variance: int = 0
    critical: bool = False


class RpgItem(BaseModel):
    id: int
    name: str
    description: str = ""
    animationId: int = -1
    iconTag: str = "potion"
    itypeId: int = 1
    price: int = 100
    consumable: bool = True
    scope: int = 7
    occasion: int = 0
    speed: int = 0
    repeats: int = 1
    successRate: int = 100
    tpGain: int = 0
    hitType: int = 0
    damage: RpgItemDamage = RpgItemDamage()
    effects: list[dict] = []
    note: str = ""


class ItemListOutput(BaseModel):
    items: list[RpgItem]


class RpgWeapon(BaseModel):
    id: int
    name: str
    description: str = ""
    iconTag: str = "sword"
    wtypeId: int = 1
    etypeId: int = 1
    power: int = 5  # 0~10. 시스템이 params/price 계산
    traits: list[dict] = []
    animationId: int = 0
    note: str = ""


class WeaponListOutput(BaseModel):
    items: list[RpgWeapon]


class RpgArmor(BaseModel):
    id: int
    name: str
    description: str = ""
    iconTag: str = "light_armor"
    atypeId: int = 1
    etypeId: int = 4
    power: int = 5  # 0~10. 시스템이 params/price 계산
    traits: list[dict] = []
    note: str = ""


class ArmorListOutput(BaseModel):
    items: list[RpgArmor]


# ── 적 tier별 스탯 테이블 (시뮬레이션 검증 완료) ────────────────────────────
# docs/The_world/BALANCE_IMPROVEMENT_PLAN.md Phase 1

_ENEMY_STAT_BY_TIER: dict[str, dict[str, int]] = {
    "weak": {
        "mhp": 200,
        "mmp": 20,
        "atk": 16,
        "def": 10,
        "mat": 11,
        "mdf": 8,
        "agi": 8,
        "luk": 5,
        "exp": 30,
        "gold": 15,
    },
    "normal": {
        "mhp": 500,
        "mmp": 50,
        "atk": 28,
        "def": 18,
        "mat": 20,
        "mdf": 14,
        "agi": 14,
        "luk": 8,
        "exp": 350,
        "gold": 50,
    },
    "elite": {
        "mhp": 1500,
        "mmp": 150,
        "atk": 45,
        "def": 30,
        "mat": 31,
        "mdf": 24,
        "agi": 22,
        "luk": 14,
        "exp": 2000,
        "gold": 150,
    },
    "boss": {
        "mhp": 4000,
        "mmp": 400,
        "atk": 60,
        "def": 42,
        "mat": 42,
        "mdf": 34,
        "agi": 30,
        "luk": 18,
        "exp": 4500,
        "gold": 500,
    },
}

# RPG Maker MZ 유효 trait 코드 (code:1 등 임의 코드는 무효)
_VALID_TRAIT_CODES: frozenset[int] = frozenset(
    [11, 12, 13, 14, 21, 22, 23, 31, 32, 33, 34, 41, 42, 43, 44, 51, 52, 53, 54, 55, 61, 62, 63, 64]
)

# RPG Maker MZ enemies.dropItems는 반드시 3개 슬롯 (kind=0: 드롭 없음)
_EMPTY_DROP_SLOT: dict = {"dataId": 1, "denominator": 1, "kind": 0}

# 적 파라미터 최솟값 [mhp, mmp, atk, def, mat, mdf, agi, luk]
# mmp=0은 허용 (마법 없는 적), 나머지는 최소 1 이상
_ENEMY_PARAM_MINS: list[int] = [1, 0, 1, 1, 1, 1, 1, 1]


class RpgEnemyAction(BaseModel):
    conditionParam1: int = 0
    conditionParam2: int = 0
    conditionType: int = 0
    rating: int = 5
    skillId: int = 1


VALID_BATTLER_NAMES: frozenset[str] = frozenset(
    [
        # 판타지 — Actor형 인간 적
        "Actor1_3",
        "Actor1_4",
        "Actor1_5",
        "Actor1_6",
        "Actor2_1",
        "Actor2_2",
        "Actor2_3",
        "Actor2_4",
        "Actor2_5",
        "Actor2_6",
        "Actor2_7",
        "Actor3_1",
        "Actor3_2",
        "Actor3_3",
        "Actor3_4",
        # 판타지 — 몬스터
        "Berserker",
        "Birdman",
        "Blackknight",
        "Caitsith",
        "Captain",
        "Crab",
        "Crow",
        "Darkelf",
        "Demon",
        "Demon_metamorphosis",
        "Demoncount",
        "Demonpot",
        "Dragon",
        "Evilbook",
        "Evilgod",
        "Foxman",
        "Frilledlizard",
        "Gatekeeper",
        "Gnome",
        "Goblin",
        "God_of_light",
        "Goddess",
        "Goddess_of_death",
        "Hakutaku",
        "Harpy",
        "Hi_monster",
        "Highking",
        "Hydra",
        "Ketos",
        "Kraken",
        "Lich",
        "Machinerybee",
        "Matango",
        "Mechascorpion",
        "Medusa",
        "Mercenary",
        "Mimic",
        "Oddegg",
        "Petitdevil",
        "Plasma",
        "Sailor",
        "Salamander",
        "Sandworm",
        "Siren",
        "Sorcerer",
        "Stoneknight",
        "Sylph",
        "Tigerbunny",
        "Treant",
        "Undine",
        "Unicorn",
        "Witch",
        "Wolfman",
        "Wraith",
        "Zombie",
        # SF 계열
        "SF_Agent",
        "SF_Anaconda",
        "SF_Armygorilla",
        "SF_Armymonkey",
        "SF_Blueogre",
        "SF_Boss",
        "SF_Brownbear",
        "SF_Cyborg",
        "SF_Demon_of_universe",
        "SF_Drone",
        "SF_Enmadaio",
        "SF_Evilteddybear",
        "SF_Hannyamask",
        "SF_Hermit",
        "SF_Jiangshi",
        "SF_Kamaitachi",
        "SF_Kappa",
        "SF_Madclown",
        "SF_Madscientist",
        "SF_Mafia",
        "SF_Mechasphere",
        "SF_Phoenix",
        "SF_Redogre",
        "SF_Securityrobot",
        "SF_Shadow",
        "SF_Skullmask",
        "SF_Slaughterrobot",
        "SF_Specialforces",
        "SF_Talkingmuppet",
        "SF_Timebomb",
        "SF_Whitewolf",
        "SF_Will_o_the_wisp",
        "SF_Wolf",
        "SF_Workrobot",
        "SF_Zombiedog",
    ]
)
_BATTLER_FALLBACK = "Goblin"

# ── 액터 이미지 유효 목록 (img/characters/, img/faces/, img/sv_actors/) ───────

VALID_CHARACTER_NAMES: frozenset[str] = frozenset(
    [
        "Actor1",
        "Actor2",
        "Actor3",
        "People1",
        "People2",
        "People3",
        "People4",
        "Evil",
        "Monster",
        "Nature",
        "Vehicle",
        "SF_Actor1",
        "SF_Actor2",
        "SF_Actor3",
        "SF_People1",
        "SF_People2",
        "SF_People3",
        "SF_Monster",
        "SF_Vehicle",
    ]
)
_CHARACTER_NAME_FALLBACK = "Actor1"

VALID_FACE_NAMES: frozenset[str] = frozenset(
    [
        "Actor1",
        "Actor2",
        "Actor3",
        "People1",
        "People2",
        "People3",
        "People4",
        "Evil",
        "Monster",
        "Nature",
        "SF_Actor1",
        "SF_Actor2",
        "SF_Actor3",
        "SF_Monster",
        "SF_People1",
    ]
)
_FACE_NAME_FALLBACK = "Actor1"

# sv_actors/ 에 실제 존재하는 파일명 (Actor3는 5~8만, SF_Actor3도 5~8만)
VALID_ACTOR_BATTLER_NAMES: frozenset[str] = frozenset(
    [
        *(f"Actor1_{i}" for i in range(1, 9)),
        *(f"Actor2_{i}" for i in range(1, 9)),
        *(f"Actor3_{i}" for i in range(5, 9)),
        *(f"SF_Actor1_{i}" for i in range(1, 9)),
        *(f"SF_Actor2_{i}" for i in range(1, 9)),
        *(f"SF_Actor3_{i}" for i in range(5, 9)),
        "",
    ]  # 빈 문자열 = SV 전투 미사용
)


class RpgEnemy(BaseModel):
    id: int
    name: str
    battlerName: str = _BATTLER_FALLBACK
    battlerHue: int = 0
    params: list[int]
    exp: int = 50
    gold: int = 20
    dropItems: list[dict] = []
    actions: list[RpgEnemyAction] = [RpgEnemyAction()]
    traits: list[dict] = []


class EnemyListOutput(BaseModel):
    items: list[RpgEnemy]


class RpgActor(BaseModel):
    id: int
    name: str
    nickname: str = ""
    classId: int
    initialLevel: int = 1
    maxLevel: int = 99
    characterName: str = "Actor1"
    characterIndex: int = 0
    faceName: str = "Actor1"
    faceIndex: int = 0
    battlerName: str = ""
    equips: list[int] = [0, 0, 0, 0, 0]
    traits: list[dict] = []
    note: str = ""
    profile: str = ""


class ActorListOutput(BaseModel):
    items: list[RpgActor]


# ── 배틀 포지션 ──────────────────────────────────────────────────────────────


# Troops.json pages[0] — RPG Maker MZ 스펙 기본 구조
def _default_troop_page() -> dict:
    return {
        "conditions": {
            "actorHp": 50,
            "actorId": 1,
            "actorValid": False,
            "enemyHp": 50,
            "enemyIndex": 0,
            "enemyValid": False,
            "switchId": 1,
            "switchValid": False,
            "turnA": 0,
            "turnB": 0,
            "turnEnding": False,
            "turnValid": False,
        },
        "list": [{"code": 0, "indent": 0, "parameters": []}],
        "span": 0,
    }


_BATTLE_POSITIONS = {
    1: [(400, 280)],
    2: [(250, 280), (550, 280)],
    3: [(150, 280), (400, 280), (650, 280)],
}
_BOSS_POSITION = (400, 200)


def _ensure_null_at_0(lst: list) -> list:
    """index 0을 None으로 보장."""
    if not lst:
        return [None]
    if lst[0] is not None:
        lst.insert(0, None)
    return lst


# ── iconTag → iconIndex DSL 매핑 (base_game IconSet.png 기준) ────────────────

SKILL_ICON_TAG: dict[str, int] = {
    # 마법 원소
    "fire_magic": 64,
    "ice_magic": 65,
    "thunder_magic": 66,
    "water_magic": 67,
    "earth_magic": 68,
    "wind_magic": 69,
    "holy_magic": 70,
    "dark_magic": 71,
    # 회복/흡수
    "heal": 72,
    "drain": 5,
    "mp_drain": 80,
    # 물리
    "physical_melee": 76,
    "physical_strong": 77,
    "physical_ranged": 78,
    # 상태이상
    "poison": 2,
    "blind": 3,
    "silence": 4,
    "confusion": 6,
    "sleep": 8,
    "paralyze": 9,
    # 버프/디버프
    "buff_atk": 34,
    "buff_def": 35,
    "buff_mat": 36,
    "buff_mdf": 37,
    "buff_agi": 38,
    "debuff_atk": 50,
    "debuff_def": 51,
    "debuff_mat": 52,
    "debuff_mdf": 53,
    "debuff_agi": 54,
    "buff": 34,
    "debuff": 50,
    # 특수
    "defense": 81,
    "escape": 82,
    "song": 80,
    "explosive": 78,
}

WEAPON_ICON_TAG: dict[str, int] = {
    "dagger": 96,
    "sword": 97,
    "mace": 98,
    "axe": 99,
    "staff": 101,
    "bow": 102,
    "crossbow": 103,
    "claw": 105,
    "gauntlet": 106,
    "spear": 107,
    "gun": 104,
}

ARMOR_ICON_TAG: dict[str, int] = {
    "light_armor": 135,
    "medium_armor": 136,
    "heavy_armor": 137,
    "robe": 139,
    "buckler": 129,
    "shield": 128,
    "bracelet": 144,
    "hat": 130,
    "cap": 130,
    "helmet": 132,
    "circlet": 133,
    "bandana": 150,
    "ring": 145,
    "stone": 147,
    "necklace": 151,
    "glasses": 151,
    "belt": 144,
    "boots": 135,
    "cloak": 139,
    "bell": 205,
}

ITEM_ICON_TAG: dict[str, int] = {
    "potion": 176,
    "ether": 178,
    "antidote": 176,
    "revive": 246,
    "feather": 297,
    "key_item": 195,
    "scroll": 189,
    "food": 208,
    "gem": 163,
    "stat_up_hp": 32,
    "stat_up_mp": 33,
    "stat_up_atk": 34,
    "stat_up_def": 35,
    "stat_up_mat": 36,
    "stat_up_mdf": 37,
    "stat_up_agi": 38,
    "stat_up_luk": 39,
    "encounter_down": 176,
    "drop_up": 176,
}

_WEAPON_WTYPE_FALLBACK: dict[int, int] = {
    1: 96,
    2: 97,
    3: 98,
    4: 99,
    6: 101,
    7: 102,
    8: 103,
    9: 104,
    10: 105,
    11: 106,
    12: 107,
}

_ARMOR_ETYPE_FALLBACK: dict[int, int] = {2: 129, 3: 130, 4: 135, 5: 145}

# ── 직업 traits (role_type → 스킬유형/무기유형/방어구유형 허용) ────────────────
# code 23: Skill Type 허용 (dataId = skillTypeId: 1=마법, 2=필살기)
# code 51: Weapon Type 허용 (dataId = wtypeId: 1=단검, 2=검, 3=도끼, 4=지팡이, 5=활)
# code 52: Armor Type 허용 (dataId = atypeId: 1=일반방어구, 2=마법방어구, 3=장신구)

_CLASS_TRAITS: dict[str, list[dict]] = {
    "warrior": [
        {"code": 23, "dataId": 2, "value": 0},  # 필살기
        {"code": 51, "dataId": 2, "value": 0},  # 검
        {"code": 51, "dataId": 1, "value": 0},  # 단검
        {"code": 52, "dataId": 1, "value": 0},  # 일반방어구
    ],
    "mage": [
        {"code": 23, "dataId": 1, "value": 0},  # 마법
        {"code": 51, "dataId": 4, "value": 0},  # 지팡이
        {"code": 52, "dataId": 2, "value": 0},  # 마법방어구
    ],
    "healer": [
        {"code": 23, "dataId": 1, "value": 0},  # 마법
        {"code": 51, "dataId": 4, "value": 0},  # 지팡이
        {"code": 52, "dataId": 2, "value": 0},  # 마법방어구
    ],
    "thief": [
        {"code": 23, "dataId": 2, "value": 0},  # 필살기
        {"code": 51, "dataId": 1, "value": 0},  # 단검
        {"code": 52, "dataId": 1, "value": 0},  # 일반방어구
        {"code": 52, "dataId": 3, "value": 0},  # 장신구
    ],
    "default": [
        {"code": 23, "dataId": 1, "value": 0},  # 마법
        {"code": 23, "dataId": 2, "value": 0},  # 필살기
        {"code": 51, "dataId": 2, "value": 0},  # 검
        {"code": 52, "dataId": 1, "value": 0},  # 일반방어구
    ],
}

# iconTag → wtypeId 매핑 (System.weaponTypes 범위 내)
_ICON_TAG_TO_WTYPE: dict[str, int] = {
    "dagger": 1,
    "sword": 2,
    "mace": 2,
    "axe": 3,
    "staff": 4,
    "bow": 5,
    "crossbow": 5,
    "gun": 5,
    "claw": 1,
    "gauntlet": 1,
    "spear": 2,
}

# System.weaponTypes 최대 인덱스
_MAX_WTYPE_ID = 5

# wtypeId → 기본 무기 이름/iconIndex (장착 가능 무기가 없을 때 자동 생성)
_DEFAULT_WEAPON_BY_WTYPE: dict[int, tuple[str, int, str]] = {
    1: ("단검", 96, "dagger"),  # 단검
    2: ("철 검", 97, "sword"),  # 검
    3: ("전투 도끼", 99, "axe"),  # 도끼
    4: ("나무 지팡이", 101, "staff"),  # 지팡이
    5: ("사냥 활", 102, "bow"),  # 활
}

# atypeId → 기본 방어구 이름/iconIndex/etypeId
_DEFAULT_ARMOR_BY_ATYPE: dict[int, tuple[str, int, int]] = {
    1: ("가죽 조끼", 135, 4),  # 일반방어구, 갑옷 슬롯
    2: ("면 로브", 139, 4),  # 마법방어구, 갑옷 슬롯
    3: ("구리 반지", 145, 5),  # 장신구, 장신구 슬롯
}


def _ensure_equippable_weapons(classes_json: list, weapons_json: list, id_table: IdTable) -> list:
    """직업별로 장착 가능한 무기가 최소 1개 있는지 검증. 없으면 자동 추가."""
    # 기존 무기의 wtypeId 집합
    existing_wtypes: set[int] = set()
    for w in weapons_json:
        if w and isinstance(w, dict):
            existing_wtypes.add(w.get("wtypeId", 0))

    # 직업이 허용하는 wtypeId 수집
    needed_wtypes: set[int] = set()
    for cls in classes_json:
        if cls and isinstance(cls, dict):
            for trait in cls.get("traits", []):
                if trait.get("code") == 51:  # Weapon Type 허용
                    needed_wtypes.add(trait["dataId"])

    # 부족한 wtypeId에 대해 기본 무기 생성
    missing = needed_wtypes - existing_wtypes
    if not missing:
        return weapons_json

    next_id = max((w["id"] for w in weapons_json if w and isinstance(w, dict)), default=0) + 1
    for wtype in sorted(missing):
        default = _DEFAULT_WEAPON_BY_WTYPE.get(wtype)
        if default is None:
            continue
        name, icon_index, icon_tag = default
        params, price = _calc_weapon_params(3, icon_tag)  # power=3 (초반 무기)
        weapons_json.append(
            {
                "id": next_id,
                "name": name,
                "description": "",
                "iconIndex": icon_index,
                "wtypeId": wtype,
                "etypeId": 1,
                "params": params,
                "price": price,
                "traits": [],
                "animationId": 0,
                "note": "(auto-generated)",
            }
        )
        logger.info("무기 자동 추가: [%d] %s (wtypeId=%d)", next_id, name, wtype)
        next_id += 1

    return weapons_json


def _ensure_equippable_armors(classes_json: list, armors_json: list, id_table: IdTable) -> list:
    """직업별로 장착 가능한 방어구가 최소 1개 있는지 검증. 없으면 자동 추가."""
    existing_atypes: set[int] = set()
    for a in armors_json:
        if a and isinstance(a, dict):
            existing_atypes.add(a.get("atypeId", 0))

    needed_atypes: set[int] = set()
    for cls in classes_json:
        if cls and isinstance(cls, dict):
            for trait in cls.get("traits", []):
                if trait.get("code") == 52:  # Armor Type 허용
                    needed_atypes.add(trait["dataId"])

    missing = needed_atypes - existing_atypes
    if not missing:
        return armors_json

    next_id = max((a["id"] for a in armors_json if a and isinstance(a, dict)), default=0) + 1
    for atype in sorted(missing):
        default = _DEFAULT_ARMOR_BY_ATYPE.get(atype)
        if default is None:
            continue
        name, icon_index, etype_id = default
        params, price = _calc_armor_params(3, etype_id)  # power=3 (초반 방어구)
        armors_json.append(
            {
                "id": next_id,
                "name": name,
                "description": "",
                "iconIndex": icon_index,
                "atypeId": atype,
                "etypeId": etype_id,
                "params": params,
                "price": price,
                "traits": [],
                "note": "(auto-generated)",
            }
        )
        logger.info("방어구 자동 추가: [%d] %s (atypeId=%d)", next_id, name, atype)
        next_id += 1

    return armors_json


# ── power(0~10) → params 변환 (밸런스 Phase 2) ──────────────────────────────
# params 순서: [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]

_WEAPON_MAX_STATS = {"atk": 50, "mat": 45, "mdf": 35, "agi": 30}
_WEAPON_PROFILE: dict[str, dict[str, float]] = {
    "sword": {"atk": 1.0},
    "dagger": {"atk": 1.0},
    "axe": {"atk": 1.0},
    "mace": {"atk": 1.0},
    "spear": {"atk": 1.0},
    "bow": {"atk": 0.8, "agi": 0.2},
    "crossbow": {"atk": 0.8, "agi": 0.2},
    "gun": {"atk": 0.8, "agi": 0.2},
    "staff": {"mat": 0.7, "mdf": 0.3},
    "claw": {"atk": 0.6, "agi": 0.4},
    "gauntlet": {"atk": 0.6, "agi": 0.4},
}
_STAT_INDEX = {"mhp": 0, "mmp": 1, "atk": 2, "def": 3, "mat": 4, "mdf": 5, "agi": 6, "luk": 7}

_ARMOR_MAX_STATS = {"def": 40, "mdf": 35, "luk": 25}
_ARMOR_PROFILE: dict[int, dict[str, float]] = {
    4: {"def": 1.0},  # 몸통
    2: {"def": 0.8, "mdf": 0.2},  # 방패
    3: {"def": 0.5, "mdf": 0.5},  # 머리
    5: {"mdf": 0.6, "luk": 0.4},  # 장신구
}

# 16전 골드 수입(2060G) 기반 장비 가격 — 구간별 수입의 80%로 1세트 구매 가능
_POWER_TO_PRICE_WEAPON = [10, 24, 48, 92, 137, 274, 412, 481, 550, 675, 800]
_POWER_TO_PRICE_ARMOR = [10, 10, 14, 21, 55, 90, 180, 270, 315, 360, 500]


def _calc_weapon_params(power: int, icon_tag: str) -> tuple[list[int], int]:
    """weapon power(0~10) + iconTag → params[8], price."""
    power = max(0, min(10, power))
    profile = _WEAPON_PROFILE.get(icon_tag, _WEAPON_PROFILE["sword"])
    params = [0] * 8
    for stat, ratio in profile.items():
        max_val = _WEAPON_MAX_STATS.get(stat, 50)
        idx = _STAT_INDEX[stat]
        params[idx] = round(power * max_val * ratio / 10)
    price = _POWER_TO_PRICE_WEAPON[power]
    return params, price


def _calc_armor_params(power: int, etype_id: int) -> tuple[list[int], int]:
    """armor power(0~10) + etypeId → params[8], price."""
    power = max(0, min(10, power))
    profile = _ARMOR_PROFILE.get(etype_id, _ARMOR_PROFILE[4])
    params = [0] * 8
    for stat, ratio in profile.items():
        max_val = _ARMOR_MAX_STATS.get(stat, 40)
        idx = _STAT_INDEX[stat]
        params[idx] = round(power * max_val * ratio / 10)
    price = _POWER_TO_PRICE_ARMOR[power]
    return params, price


# ── 스킬 power(0~10) → formula/mpCost 변환 (밸런스 Phase 4) ─────────────────

# iconTag 카테고리 분류
_PHYSICAL_TAGS = {"physical_melee", "physical_strong", "physical_ranged", "explosive"}
_MAGIC_TAGS = {
    "fire_magic",
    "ice_magic",
    "thunder_magic",
    "water_magic",
    "earth_magic",
    "wind_magic",
    "holy_magic",
    "dark_magic",
}
_HEAL_TAGS = {"heal"}
_DRAIN_TAGS = {"drain", "mp_drain"}


def _calc_skill_formula(power: int, icon_tag: str, scope: int) -> tuple[str, int, dict]:
    """스킬 power(0~10) + iconTag + scope → (formula, mpCost, damage_dict)."""
    power = max(0, min(10, power))
    t = power / 10.0
    # scope 보정: 전체 공격은 약하게
    scope_mult = 0.6 if scope == 2 else (0.7 if scope == 8 else 1.0)

    if icon_tag in _PHYSICAL_TAGS:
        atk_mult = round((1.5 + 3.5 * t) * scope_mult, 2)
        def_mult = round((1.0 + 1.0 * t) * scope_mult, 2)
        formula = f"a.atk * {atk_mult} - b.def * {def_mult}"
        damage = {
            "type": 1,
            "elementId": -1,
            "formula": formula,
            "variance": 20,
            "critical": power >= 7,
        }
    elif icon_tag in _MAGIC_TAGS:
        mat_mult = round((1.5 + 3.5 * t) * scope_mult, 2)
        mdf_mult = round((1.0 + 1.0 * t) * scope_mult, 2)
        formula = f"a.mat * {mat_mult} - b.mdf * {mdf_mult}"
        # elementId: iconTag → element
        elem_map = {
            "fire_magic": 2,
            "ice_magic": 3,
            "thunder_magic": 4,
            "water_magic": 5,
            "earth_magic": 6,
            "wind_magic": 7,
            "holy_magic": 8,
            "dark_magic": 9,
        }
        damage = {
            "type": 1,
            "elementId": elem_map.get(icon_tag, 0),
            "formula": formula,
            "variance": 20,
            "critical": False,
        }
    elif icon_tag in _HEAL_TAGS:
        mat_mult = round((0.5 + 2.5 * t) * scope_mult, 2)
        flat = round((20 + 180 * t) * scope_mult)
        formula = f"a.mat * {mat_mult} + {flat}"
        damage = {"type": 3, "elementId": 0, "formula": formula, "variance": 10, "critical": False}
    elif icon_tag in _DRAIN_TAGS:
        atk_mult = round(1.5 + 2.0 * t, 2)
        def_mult = round(1.0 + 0.5 * t, 2)
        formula = f"a.atk * {atk_mult} - b.def * {def_mult}"
        dtype = 5 if icon_tag == "drain" else 6
        damage = {
            "type": dtype,
            "elementId": 0,
            "formula": formula,
            "variance": 20,
            "critical": False,
        }
    else:
        # 버프/디버프/상태이상/특수 → 데미지 없음
        formula = "0"
        damage = {"type": 0, "elementId": 0, "formula": "0", "variance": 0, "critical": False}

    mp_cost = power * 2
    return formula, mp_cost, damage


# ── 스킬 애니메이션 매핑 (base_game Animations.json 기준) ────────────────────

# (iconTag, scope_type) → (weak_animId, strong_animId)
# scope_type: "single"(1,3~6), "aoe"(2), "ally"(7), "ally_all"(8), "self"(11)
_ANIM_MAP: dict[tuple[str, str], tuple[int, int]] = {
    # 마법 원소 — 단일
    ("fire_magic", "single"): (66, 67),
    ("ice_magic", "single"): (71, 72),
    ("thunder_magic", "single"): (76, 77),
    ("water_magic", "single"): (81, 82),
    ("earth_magic", "single"): (86, 87),
    ("wind_magic", "single"): (91, 92),
    ("holy_magic", "single"): (96, 97),
    ("dark_magic", "single"): (101, 102),
    # 마법 원소 — 전체
    ("fire_magic", "aoe"): (68, 70),
    ("ice_magic", "aoe"): (73, 75),
    ("thunder_magic", "aoe"): (78, 80),
    ("water_magic", "aoe"): (83, 85),
    ("earth_magic", "aoe"): (88, 90),
    ("wind_magic", "aoe"): (93, 95),
    ("holy_magic", "aoe"): (98, 100),
    ("dark_magic", "aoe"): (103, 105),
    # 물리
    ("physical_melee", "single"): (1, 6),
    ("physical_melee", "aoe"): (1, 6),
    ("physical_strong", "single"): (21, 25),
    ("physical_strong", "aoe"): (21, 25),
    ("physical_ranged", "single"): (29, 112),
    ("physical_ranged", "aoe"): (29, 114),
    ("explosive", "single"): (106, 107),
    ("explosive", "aoe"): (108, 110),
    # 회복
    ("heal", "ally"): (41, 42),
    ("heal", "ally_all"): (43, 44),
    ("heal", "self"): (41, 42),
    # 흡수
    ("drain", "single"): (58, 58),
    ("mp_drain", "single"): (58, 58),
    # 버프/디버프
    ("buff", "ally"): (51, 52),
    ("buff", "ally_all"): (51, 53),
    ("buff", "self"): (51, 52),
    ("buff_atk", "ally"): (51, 52),
    ("buff_def", "ally"): (51, 52),
    ("buff_mat", "ally"): (51, 52),
    ("buff_mdf", "ally"): (51, 52),
    ("buff_agi", "ally"): (51, 52),
    ("debuff", "single"): (54, 55),
    ("debuff", "aoe"): (54, 56),
    ("debuff_atk", "single"): (54, 55),
    ("debuff_def", "single"): (54, 55),
    ("debuff_mat", "single"): (54, 55),
    ("debuff_mdf", "single"): (54, 55),
    ("debuff_agi", "single"): (54, 55),
    # 상태이상
    ("poison", "single"): (59, 59),
    ("blind", "single"): (60, 60),
    ("blind", "aoe"): (40, 40),
    ("silence", "single"): (61, 61),
    ("confusion", "single"): (34, 63),
    ("confusion", "aoe"): (34, 34),
    ("sleep", "single"): (62, 62),
    ("sleep", "aoe"): (36, 36),
    ("paralyze", "single"): (64, 64),
    # 특수
    ("defense", "self"): (0, 0),
    ("escape", "self"): (0, 0),
    ("song", "aoe"): (36, 36),
}


def _scope_type(scope: int) -> str:
    """scope 값 → 카테고리."""
    if scope == 2:
        return "aoe"
    if scope == 7:
        return "ally"
    if scope == 8:
        return "ally_all"
    if scope in (11, 12):
        return "self"
    return "single"


def _resolve_animation(icon_tag: str, scope: int, power: int) -> int:
    """(iconTag, scope, power) → animationId."""
    st = _scope_type(scope)
    key = (icon_tag, st)
    if key in _ANIM_MAP:
        weak_id, strong_id = _ANIM_MAP[key]
        return strong_id if power > 5 else weak_id

    # fallback: scope 타입별 기본 애니메이션
    if st in ("ally", "ally_all", "self"):
        return 51  # 강화
    if st == "aoe":
        return 108  # 전체 폭발
    return 1  # 물리 타격


def _resolve_icon(tag: str, tag_map: dict[str, int], fallback: int) -> int:
    """iconTag → iconIndex 변환. 알 수 없는 태그면 fallback."""
    return tag_map.get(tag, fallback)


# effects code 31=버프, 32=디버프 → dataId별 구체 태그
_BUFF_DATAID_TAG: dict[int, str] = {
    0: "buff_atk",
    1: "buff_atk",
    2: "buff_atk",
    3: "buff_def",
    4: "buff_mat",
    5: "buff_mdf",
    6: "buff_agi",
    7: "buff_agi",
}
_DEBUFF_DATAID_TAG: dict[int, str] = {
    0: "debuff_atk",
    1: "debuff_atk",
    2: "debuff_atk",
    3: "debuff_def",
    4: "debuff_mat",
    5: "debuff_mdf",
    6: "debuff_agi",
    7: "debuff_agi",
}


def _refine_buff_tag(tag: str, effects: list[dict]) -> str:
    """'buff'/'debuff' 범용 태그를 effects dataId 기반으로 세분화."""
    if tag not in ("buff", "debuff") or not effects:
        return tag
    first = effects[0]
    code = first.get("code", 0)
    data_id = first.get("dataId", 0)
    if code == 31:  # Add Buff
        return _BUFF_DATAID_TAG.get(data_id, "buff")
    if code == 32:  # Add Debuff
        return _DEBUFF_DATAID_TAG.get(data_id, "debuff")
    return tag


def _inject_fallback_effect(d: dict) -> None:
    """damage.type=0 + effects=[] 스킬에 기본 효과 주입."""
    scope = d.get("scope", 1)
    if scope in (1, 2, 3, 4, 5, 6):
        d["effects"] = [{"code": 32, "dataId": 6, "value1": 3, "value2": 0}]
    else:
        d["effects"] = [{"code": 31, "dataId": 2, "value1": 3, "value2": 0}]


# ── 개별 에셋 생성 함수 ──────────────────────────────────────────────────────


async def generate_classes(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_classes_prompt(spec, id_table)
    result = cast(
        LlmClassList,
        await invoke_llm(messages, structured_output=LlmClassList, temperature=_TEMPERATURE),
    )

    # role_type 직접 사용 (Phase 3), fallback: _normalize_role
    class_roles: dict[str, str] = {
        c.class_name: (
            c.role_type
            if hasattr(c, "role_type") and c.role_type in _CLASS_STAT_TEMPLATE
            else _normalize_role(c.role)
        )
        for c in spec.characters
    }
    llm_by_name = {cls.name: cls for cls in result.classes}
    # 시스템(id=1,2) + 적 전용 스킬 제외 → 플레이어 스킬만
    player_skill_ids = {
        sid for name, sid in id_table.skills.items() if sid >= 3 and not name.startswith("적_")
    }
    valid_skill_ids = player_skill_ids

    # Bug 1-C: 클래스별 허용 스킬 ID 집합 구축
    class_skill_ids: dict[str, set[int]] = {}
    for s in spec.skills:
        sid = id_table.skills.get(s.name)
        if sid is not None:
            class_skill_ids.setdefault(s.class_name, set()).add(sid)

    output: list[Any] = [None]
    for cls_name, cid in sorted(id_table.classes.items(), key=lambda x: x[1]):
        role = class_roles.get(cls_name, "default")
        llm_cls = llm_by_name.get(cls_name)
        if llm_cls is None:
            logger.warning("LLM이 직업 '%s'를 누락, 기본값 사용", cls_name)
            llm_cls = LlmClass(id=cid, name=cls_name, expParams=[5, 5, 2, 30], learnings=[])

        # 이 클래스에 배정된 스킬 + "공용" 스킬만 허용
        allowed = class_skill_ids.get(cls_name, set()) | class_skill_ids.get("공용", set())
        seen_skills: set[int] = set()
        learnings: list[dict] = []
        for lr in llm_cls.learnings:
            sid = lr.skillId
            if sid in seen_skills:
                continue  # 중복 스킬 제거
            if sid not in valid_skill_ids:
                continue
            if allowed and sid not in allowed:
                continue
            seen_skills.add(sid)
            learnings.append({"level": lr.level, "skillId": sid, "note": ""})

        # 허용된 스킬 중 learnings에 빠진 것을 레벨 균등 분배로 추가
        missing = (allowed - seen_skills) & valid_skill_ids
        if missing:
            max_lv = 20
            step = max(1, max_lv // (len(missing) + 1))
            for i, sid in enumerate(sorted(missing)):
                lv = min(max_lv, step * (i + 1))
                learnings.append({"level": lv, "skillId": sid, "note": ""})
            learnings.sort(key=lambda x: x["level"])
        output.append(
            {
                "id": cid,
                "name": cls_name,
                "expParams": _validate_exp_params(llm_cls.expParams),
                "params": _build_params_2d(role),
                "learnings": learnings,
                "traits": _CLASS_TRAITS.get(role, _CLASS_TRAITS["default"]),
                "note": llm_cls.note,
            }
        )
    return output


# ── 시스템 스킬 (id=1 공격, id=2 방어) ─────────────────────────────────────

_SYSTEM_SKILL_ATTACK: dict[str, Any] = {
    "id": 1,
    "name": "공격",
    "description": "",
    "animationId": -1,
    "iconIndex": 76,
    "stypeId": 0,
    "scope": 1,
    "occasion": 1,
    "mpCost": 0,
    "tpCost": 0,
    "tpGain": 5,
    "speed": 0,
    "repeats": 1,
    "successRate": 100,
    "hitType": 1,
    "messageType": 1,
    "message1": "%1이(가) 공격합니다!",
    "message2": "",
    "requiredWtypeId1": 0,
    "requiredWtypeId2": 0,
    "damage": {
        "type": 1,
        "elementId": -1,
        "formula": "a.atk * 4 - b.def * 2",
        "variance": 20,
        "critical": True,
    },
    "effects": [{"code": 21, "dataId": 0, "value1": 1, "value2": 0}],
    "note": "",
}

_SYSTEM_SKILL_GUARD: dict[str, Any] = {
    "id": 2,
    "name": "방어",
    "description": "",
    "animationId": 0,
    "iconIndex": 81,
    "stypeId": 0,
    "scope": 11,
    "occasion": 1,
    "mpCost": 0,
    "tpCost": 0,
    "tpGain": 10,
    "speed": 2000,
    "repeats": 1,
    "successRate": 100,
    "hitType": 0,
    "messageType": 1,
    "message1": "%1이(가) 방어합니다.",
    "message2": "",
    "requiredWtypeId1": 0,
    "requiredWtypeId2": 0,
    "damage": {"type": 0, "elementId": 0, "formula": "0", "variance": 20, "critical": False},
    "effects": [{"code": 21, "dataId": 2, "value1": 1, "value2": 0}],
    "note": "",
}

# ── 적 전용 스킬 템플릿 ────────────────────────────────────────────────────

_ENEMY_SKILL_DATA: dict[str, dict[str, Any]] = {
    "적_강타": {
        "name": "강타",
        "iconIndex": 77,
        "stypeId": 2,
        "scope": 1,
        "hitType": 1,
        "messageType": 1,
        "message1": "%1이(가) 강타합니다!",
        "damage": {
            "type": 1,
            "elementId": -1,
            "formula": "a.atk * 5 - b.def * 2",
            "variance": 20,
            "critical": True,
        },
        "effects": [{"code": 21, "dataId": 0, "value1": 1, "value2": 0}],
    },
    "적_전체공격": {
        "name": "전체 공격",
        "iconIndex": 78,
        "stypeId": 2,
        "scope": 2,
        "hitType": 1,
        "messageType": 1,
        "message1": "%1이(가) 전체 공격을 가합니다!",
        "damage": {
            "type": 1,
            "elementId": -1,
            "formula": "a.atk * 3 - b.def * 2",
            "variance": 20,
            "critical": False,
        },
        "effects": [],
    },
    "적_자가회복": {
        "name": "자가 회복",
        "iconIndex": 72,
        "stypeId": 1,
        "scope": 11,
        "hitType": 0,
        "messageType": 1,
        "message1": "%1이(가) 회복합니다!",
        "damage": {
            "type": 3,
            "elementId": 0,
            "formula": "b.mhp * 0.15",
            "variance": 0,
            "critical": False,
        },
        "effects": [],
    },
    "적_버프": {
        "name": "기합",
        "iconIndex": 34,
        "stypeId": 2,
        "scope": 11,
        "hitType": 0,
        "messageType": 1,
        "message1": "%1이(가) 기합을 넣습니다!",
        "damage": {"type": 0, "elementId": 0, "formula": "0", "variance": 0, "critical": False},
        "effects": [{"code": 31, "dataId": 2, "value1": 3, "value2": 0}],
    },
}


_ENEMY_SKILL_ANIM: dict[str, int] = {
    "적_강타": 25,  # 강한 베기
    "적_전체공격": 108,  # 전체 폭발
    "적_자가회복": 41,  # 1인 회복
    "적_버프": 51,  # 강화
}


def _build_enemy_skill(template_name: str, skill_id: int) -> dict[str, Any]:
    """적 스킬 템플릿 → 완전한 RPG Maker MZ 스킬 dict."""
    tmpl = _ENEMY_SKILL_DATA[template_name]
    return {
        "id": skill_id,
        "name": tmpl["name"],
        "description": "",
        "animationId": _ENEMY_SKILL_ANIM.get(template_name, -1),
        "iconIndex": tmpl["iconIndex"],
        "stypeId": tmpl["stypeId"],
        "scope": tmpl["scope"],
        "occasion": 1,
        "mpCost": 0,
        "tpCost": 0,
        "tpGain": 0,
        "speed": 0,
        "repeats": 1,
        "successRate": 100,
        "hitType": tmpl["hitType"],
        "messageType": tmpl["messageType"],
        "message1": tmpl["message1"],
        "message2": "",
        "requiredWtypeId1": 0,
        "requiredWtypeId2": 0,
        "damage": tmpl["damage"],
        "effects": tmpl["effects"],
        "note": "",
    }


async def generate_skills(spec: GameSpec, id_table: IdTable) -> list:
    if not id_table.skills:
        return [None]

    # 1. 시스템 스킬 (id=1 공격, id=2 방어)
    output: list[Any] = [None, _SYSTEM_SKILL_ATTACK, _SYSTEM_SKILL_GUARD]

    # 2. LLM 생성 플레이어 스킬 (id=3~)
    player_skill_ids = {
        sid for name, sid in id_table.skills.items() if sid >= 3 and name not in _ENEMY_SKILL_DATA
    }
    enemy_skill_ids = {sid for name, sid in id_table.skills.items() if name in _ENEMY_SKILL_DATA}
    if player_skill_ids:
        messages = build_skills_prompt(spec, id_table)
        result = cast(
            SkillListOutput,
            await invoke_llm(messages, structured_output=SkillListOutput, temperature=_TEMPERATURE),
        )
        for skill in sorted(result.items, key=lambda s: s.id):
            d = skill.model_dump()
            # B: 시스템/적 스킬 ID 필터 (LLM이 생성해도 무시)
            if d["id"] < 3 or d["id"] in enemy_skill_ids:
                continue
            tag = d.pop("iconTag", "physical_melee")
            power = d.pop("power", 5)
            tag = _refine_buff_tag(tag, d.get("effects", []))
            d["iconIndex"] = _resolve_icon(tag, SKILL_ICON_TAG, 0)
            # power → formula/mpCost/animationId 자동 계산
            scope = d.get("scope", 1)
            _, mp_cost, damage = _calc_skill_formula(power, tag, scope)
            d["damage"] = damage
            d["mpCost"] = mp_cost
            d["animationId"] = _resolve_animation(tag, scope, power)
            if d.get("message1") and d.get("messageType") == 0:
                d["messageType"] = 1
            if d["damage"]["type"] == 0 and not d.get("effects"):
                _inject_fallback_effect(d)
            output.append(d)

    # 3. 적 전용 스킬 (알고리즘 생성)
    for sname, sid in sorted(id_table.skills.items(), key=lambda x: x[1]):
        if sname in _ENEMY_SKILL_DATA:
            output.append(_build_enemy_skill(sname, sid))

    # C: 최종 id 중복 제거 (선착순 유지)
    seen_ids: set[int] = set()
    deduped: list[Any] = [None]
    for skill in output[1:]:
        sid = skill["id"]
        if sid in seen_ids:
            logger.warning("Skills.json id=%d 중복 제거: '%s'", sid, skill.get("name"))
            continue
        seen_ids.add(sid)
        deduped.append(skill)

    return deduped


async def generate_items(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_items_prompt(spec, id_table)
    result = cast(
        ItemListOutput,
        await invoke_llm(messages, structured_output=ItemListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for item in sorted(result.items, key=lambda i: i.id):
        d = item.model_dump()
        tag = d.pop("iconTag", "potion")
        d["iconIndex"] = _resolve_icon(tag, ITEM_ICON_TAG, 302)
        output.append(d)
    return _ensure_null_at_0(output)


async def generate_weapons(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_weapons_prompt(spec, id_table)
    result = cast(
        WeaponListOutput,
        await invoke_llm(messages, structured_output=WeaponListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for weapon in sorted(result.items, key=lambda w: w.id):
        d = weapon.model_dump()
        # iconTag → iconIndex 변환
        tag = d.pop("iconTag", "sword")
        d["iconIndex"] = _resolve_icon(tag, WEAPON_ICON_TAG, 0)
        # iconTag → wtypeId 강제 매핑 (LLM이 범위 초과 wtypeId를 생성하는 문제 방지)
        d["wtypeId"] = _ICON_TAG_TO_WTYPE.get(tag, 2)  # 매핑 없으면 검(2)
        if d["wtypeId"] > _MAX_WTYPE_ID:
            d["wtypeId"] = 2  # 범위 초과 시 검으로 폴백
        # power → params/price 알고리즘 (LLM params 무시)
        power = d.pop("power", 5)
        d["params"], d["price"] = _calc_weapon_params(power, tag)
        output.append(d)
    return _ensure_null_at_0(output)


async def generate_armors(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_armors_prompt(spec, id_table)
    result = cast(
        ArmorListOutput,
        await invoke_llm(messages, structured_output=ArmorListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for armor in sorted(result.items, key=lambda a: a.id):
        d = armor.model_dump()
        # iconTag → iconIndex 변환
        tag = d.pop("iconTag", "light_armor")
        d["iconIndex"] = _resolve_icon(tag, ARMOR_ICON_TAG, 0)
        # power → params/price 알고리즘 (LLM params 무시)
        power = d.pop("power", 5)
        d["params"], d["price"] = _calc_armor_params(power, d.get("etypeId", 4))
        output.append(d)
    return _ensure_null_at_0(output)


async def generate_enemies(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_enemies_prompt(spec, id_table)
    result = cast(
        EnemyListOutput,
        await invoke_llm(messages, structured_output=EnemyListOutput, temperature=_TEMPERATURE),
    )
    # 이름 → EnemySpec 빠른 조회용
    spec_by_name: dict[str, Any] = {e.name: e for e in spec.enemies}

    output: list[Any] = [None]
    for enemy in sorted(result.items, key=lambda e: e.id):
        d = enemy.model_dump()

        # note + tier별 params/actions 강제 배정
        enemy_spec = spec_by_name.get(d.get("name", ""))
        if enemy_spec:
            d["note"] = f"tier:{enemy_spec.tier} location:{enemy_spec.location}"

            # tier 기반 params 강제 주입 (LLM params 무시)
            tier_stats = _ENEMY_STAT_BY_TIER.get(enemy_spec.tier)
            if tier_stats:
                d["params"] = [
                    tier_stats["mhp"],
                    tier_stats["mmp"],
                    tier_stats["atk"],
                    tier_stats["def"],
                    tier_stats["mat"],
                    tier_stats["mdf"],
                    tier_stats["agi"],
                    tier_stats["luk"],
                ]
                d["exp"] = tier_stats["exp"]
                d["gold"] = tier_stats["gold"]
        else:
            # spec 매칭 실패 시 기본 보정
            if len(d["params"]) != 8:
                d["params"] = [200, 20, 16, 10, 11, 8, 8, 5]
            for i, min_val in enumerate(_ENEMY_PARAM_MINS):
                if d["params"][i] < min_val:
                    d["params"][i] = min_val

        if enemy_spec:
            # tier별 적 스킬 배정 (id=1 "공격" 기본 + 적 전용 스킬)
            from agent.generation.nodes.asset_planner import _ENEMY_SKILL_TEMPLATES

            tier_skills = _ENEMY_SKILL_TEMPLATES.get(enemy_spec.tier, [])
            actions = [
                {
                    "conditionParam1": 0,
                    "conditionParam2": 0,
                    "conditionType": 0,
                    "rating": 5,
                    "skillId": 1,
                }
            ]  # 기본 공격
            for sname in tier_skills:
                sid = id_table.skills.get(sname)
                if sid:
                    actions.append(
                        {
                            "conditionParam1": 0,
                            "conditionParam2": 0,
                            "conditionType": 0,
                            "rating": 4,
                            "skillId": sid,
                        }
                    )
            d["actions"] = actions

        # battlerName 유효성 확인
        if d.get("battlerName") not in VALID_BATTLER_NAMES:
            logger.warning(
                "enemy '%s' battlerName='%s' not valid → fallback '%s'",
                d.get("name"),
                d.get("battlerName"),
                _BATTLER_FALLBACK,
            )
            d["battlerName"] = _BATTLER_FALLBACK
            existing_note = d.get("note") or ""
            d["note"] = f"{existing_note} (fallback)".strip()

        # dropItems: RPG Maker MZ 스펙상 반드시 3개 슬롯
        drops = d.get("dropItems") or []
        drops = drops[:3]  # 최대 3개
        while len(drops) < 3:
            drops.append(dict(_EMPTY_DROP_SLOT))
        d["dropItems"] = drops

        # traits: 유효하지 않은 code 및 여분 필드(kind 등) 제거
        d["traits"] = [
            {"code": t["code"], "dataId": t.get("dataId", 0), "value": t.get("value", 0)}
            for t in d.get("traits", [])
            if t.get("code") in _VALID_TRAIT_CODES
        ]

        output.append(d)
    return _ensure_null_at_0(output)


async def generate_actors(
    spec: GameSpec,
    id_table: IdTable,
    classes_json: list,
) -> list:
    messages = build_actors_prompt(spec, id_table, classes_json)
    result = cast(
        ActorListOutput,
        await invoke_llm(messages, structured_output=ActorListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for actor in sorted(result.items, key=lambda a: a.id):
        d = actor.model_dump()

        # characterName 검증
        if d.get("characterName") not in VALID_CHARACTER_NAMES:
            logger.warning(
                "actor '%s' characterName='%s' 유효하지 않음 → fallback '%s'",
                d.get("name"),
                d.get("characterName"),
                _CHARACTER_NAME_FALLBACK,
            )
            d["characterName"] = _CHARACTER_NAME_FALLBACK

        # characterIndex 범위 보정
        if not (0 <= d.get("characterIndex", 0) <= 7):
            d["characterIndex"] = 0

        # faceName 검증
        if d.get("faceName") not in VALID_FACE_NAMES:
            logger.warning(
                "actor '%s' faceName='%s' 유효하지 않음 → fallback '%s'",
                d.get("name"),
                d.get("faceName"),
                _FACE_NAME_FALLBACK,
            )
            d["faceName"] = _FACE_NAME_FALLBACK

        # faceIndex 범위 보정
        if not (0 <= d.get("faceIndex", 0) <= 7):
            d["faceIndex"] = 0

        # 이미지 일관성 강제: characterName/characterIndex를 faceName/faceIndex에 맞춤
        d["characterName"] = d["faceName"]
        d["characterIndex"] = d["faceIndex"]

        # battlerName을 faceName/faceIndex 기반으로 자동 계산 (1-based)
        derived_battler = f"{d['faceName']}_{d['faceIndex'] + 1}"
        if derived_battler in VALID_ACTOR_BATTLER_NAMES:
            d["battlerName"] = derived_battler
        else:
            # Actor3/SF_Actor3의 index 0~3 등 sv_actors에 없는 경우
            if d.get("battlerName") not in VALID_ACTOR_BATTLER_NAMES:
                d["battlerName"] = ""

        output.append(d)
    return _ensure_null_at_0(output)


def generate_troops(spec: GameSpec, id_table: IdTable, enemies_json: list) -> list:
    """Troops.json 알고리즘 생성 (LLM 없음)."""
    output: list[Any] = [None]
    tid = 1

    # 적별 troop 생성
    for enemy in spec.enemies:
        enemy_id = id_table.enemies.get(enemy.name)
        if enemy_id is None:
            continue

        if enemy.tier == "boss":
            bx, by = _BOSS_POSITION
            output.append(
                {
                    "id": tid,
                    "name": f"{enemy.name}_단독",
                    "members": [{"enemyId": enemy_id, "x": bx, "y": by, "hidden": False}],
                    "pages": [_default_troop_page()],
                }
            )
            tid += 1
        elif enemy.tier == "elite":
            x, y = _BATTLE_POSITIONS[1][0]
            output.append(
                {
                    "id": tid,
                    "name": f"{enemy.name}_단독",
                    "members": [{"enemyId": enemy_id, "x": x, "y": y, "hidden": False}],
                    "pages": [_default_troop_page()],
                }
            )
            tid += 1
        else:
            for count in (1, 2, 3):
                positions = _BATTLE_POSITIONS.get(count, _BATTLE_POSITIONS[1])
                members = [
                    {"enemyId": enemy_id, "x": px, "y": py, "hidden": False} for px, py in positions
                ]
                output.append(
                    {
                        "id": tid,
                        "name": f"{enemy.name}×{count}",
                        "members": members,
                        "pages": [_default_troop_page()],
                    }
                )
                tid += 1

    return output


# ── C 노드 메인 ──────────────────────────────────────────────────────────────


async def asset_generator(state: GenerationState) -> dict:
    """C 노드: LLM 병렬 호출 → 에셋 JSON 생성."""
    gen_id = state["generation_id"]
    spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "assets",
            "progress": 13,
            "message": "에셋 생성 중 (클래스·스킬·아이템·무기·방어구·적)...",
        },
    )

    # 1단계: 독립 에셋 병렬
    results = await asyncio.gather(
        generate_classes(spec, id_table),
        generate_skills(spec, id_table),
        generate_items(spec, id_table),
        generate_weapons(spec, id_table),
        generate_armors(spec, id_table),
        generate_enemies(spec, id_table),
        return_exceptions=True,
    )

    file_names = [
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
    ]
    # 실패한 에셋 재시도 (타임아웃/네트워크 오류 대비)
    _retry_fns = {
        "Classes.json": lambda: generate_classes(spec, id_table),
        "Skills.json": lambda: generate_skills(spec, id_table),
        "Items.json": lambda: generate_items(spec, id_table),
        "Weapons.json": lambda: generate_weapons(spec, id_table),
        "Armors.json": lambda: generate_armors(spec, id_table),
        "Enemies.json": lambda: generate_enemies(spec, id_table),
    }
    _critical = {"Classes.json", "Enemies.json"}  # 이것만 실패 시 파이프라인 중단

    assets: dict[str, Any] = {}
    for fname, result in zip(file_names, results):
        if isinstance(result, Exception):
            logger.warning("%s 생성 실패, 재시도 중: %s", fname, result)
            try:
                result = await _retry_fns[fname]()
            except Exception as retry_err:
                if fname in _critical:
                    raise RuntimeError(f"{fname} 생성 실패: {retry_err}") from retry_err
                logger.error("%s 재시도도 실패 → 빈 데이터로 계속 진행: %s", fname, retry_err)
                result = [None]
        assets[fname] = result

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "assets",
            "progress": 42,
            "message": "캐릭터·부대 생성 중...",
        },
    )

    # 2단계: actors ← classes
    assets["Actors.json"] = await generate_actors(spec, id_table, assets["Classes.json"])

    # 3단계: troops (알고리즘)
    assets["Troops.json"] = generate_troops(spec, id_table, assets["Enemies.json"])

    # 4단계: 직업별 장착 가능 무기/방어구 보장
    assets["Weapons.json"] = _ensure_equippable_weapons(
        assets["Classes.json"], assets["Weapons.json"], id_table
    )
    assets["Armors.json"] = _ensure_equippable_armors(
        assets["Classes.json"], assets["Armors.json"], id_table
    )

    logger.info(
        "asset_generator 완료: actors=%d classes=%d skills=%d enemies=%d",
        len(assets["Actors.json"]) - 1,
        len(assets["Classes.json"]) - 1,
        len(assets["Skills.json"]) - 1,
        len(assets["Enemies.json"]) - 1,
    )

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "assets",
            "summary": (
                f"캐릭터 {len(assets['Actors.json']) - 1}명, "
                f"스킬 {len(assets['Skills.json']) - 1}개, "
                f"적 {len(assets['Enemies.json']) - 1}종 생성 완료"
            ),
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("assets")
    return {"generated_assets": assets, "completed_phases": completed}
