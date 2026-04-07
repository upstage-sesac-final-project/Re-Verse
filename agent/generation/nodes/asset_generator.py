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

_CLASS_STAT_TEMPLATE: dict[str, dict[str, tuple[int, int]]] = {
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

_STAT_ORDER = ["mhp", "mmp", "atk", "def", "mat", "mdf", "agi", "luk"]


def _generate_class_params(lv1: int, lv99: int, growth: str = "linear") -> list[int]:
    """lv1~lv99 값의 99개 정수 배열 생성."""
    result = []
    for lv in range(1, 100):
        t = (lv - 1) / 98.0
        if growth == "accelerate":
            t = t * t
        val = round(lv1 + (lv99 - lv1) * t)
        result.append(val)
    assert len(result) == 99, f"params row length error: {len(result)}"
    return result


def _build_params_2d(role: str) -> list[list[int]]:
    """8 × 99 params 2D 배열 생성."""
    template = _CLASS_STAT_TEMPLATE.get(role, _CLASS_STAT_TEMPLATE["default"])
    params_2d = []
    for stat in _STAT_ORDER:
        lv1, lv99 = template[stat]
        growth = "accelerate" if stat in ("mhp", "mmp") else "linear"
        params_2d.append(_generate_class_params(lv1, lv99, growth=growth))
    return params_2d


def _validate_exp_params(ep: list[int]) -> list[int]:
    if len(ep) != 4:
        return [30, 20, 30, 30]
    return [
        max(10, min(50, ep[0])),
        max(10, min(40, ep[1])),
        max(15, min(50, ep[2])),
        max(20, min(50, ep[3])),
    ]


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
    animationId: int = -1
    iconIndex: int = 0
    stypeId: int = 1
    scope: int = 1
    occasion: int = 1
    mpCost: int = 0
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
    iconIndex: int = 0
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
    iconIndex: int = 0
    wtypeId: int = 1
    etypeId: int = 1
    price: int = 500
    params: list[int] = [0] * 8
    traits: list[dict] = []
    animationId: int = 0
    note: str = ""


class WeaponListOutput(BaseModel):
    items: list[RpgWeapon]


class RpgArmor(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    atypeId: int = 1
    etypeId: int = 4
    price: int = 300
    params: list[int] = [0] * 8
    traits: list[dict] = []
    note: str = ""


class ArmorListOutput(BaseModel):
    items: list[RpgArmor]


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
    note: str = ""


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


# ── 개별 에셋 생성 함수 ──────────────────────────────────────────────────────


async def generate_classes(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_classes_prompt(spec, id_table)
    result = cast(
        LlmClassList,
        await invoke_llm(messages, structured_output=LlmClassList, temperature=_TEMPERATURE),
    )

    class_roles: dict[str, str] = {c.class_name: _normalize_role(c.role) for c in spec.characters}
    llm_by_name = {cls.name: cls for cls in result.classes}
    valid_skill_ids = set(id_table.skills.values())

    output: list[Any] = [None]
    for cls_name, cid in sorted(id_table.classes.items(), key=lambda x: x[1]):
        role = class_roles.get(cls_name, "default")
        llm_cls = llm_by_name.get(cls_name)
        if llm_cls is None:
            logger.warning("LLM이 직업 '%s'를 누락, 기본값 사용", cls_name)
            llm_cls = LlmClass(id=cid, name=cls_name, expParams=[30, 20, 30, 30], learnings=[])

        learnings = [
            {"level": lr.level, "skillId": lr.skillId, "note": ""}
            for lr in llm_cls.learnings
            if lr.skillId in valid_skill_ids
        ]
        output.append(
            {
                "id": cid,
                "name": cls_name,
                "expParams": _validate_exp_params(llm_cls.expParams),
                "params": _build_params_2d(role),
                "learnings": learnings,
                "traits": [],
                "note": llm_cls.note,
            }
        )
    return output


async def generate_skills(spec: GameSpec, id_table: IdTable) -> list:
    if not id_table.skills:
        return [None]
    messages = build_skills_prompt(spec, id_table)
    result = cast(
        SkillListOutput,
        await invoke_llm(messages, structured_output=SkillListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for skill in sorted(result.items, key=lambda s: s.id):
        output.append(skill.model_dump())
    return _ensure_null_at_0(output)


async def generate_items(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_items_prompt(spec, id_table)
    result = cast(
        ItemListOutput,
        await invoke_llm(messages, structured_output=ItemListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for item in sorted(result.items, key=lambda i: i.id):
        output.append(item.model_dump())
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
        if len(d["params"]) != 8:
            d["params"] = [0] * 8
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
        if len(d["params"]) != 8:
            d["params"] = [0] * 8
        output.append(d)
    return _ensure_null_at_0(output)


async def generate_enemies(spec: GameSpec, id_table: IdTable) -> list:
    messages = build_enemies_prompt(spec, id_table)
    result = cast(
        EnemyListOutput,
        await invoke_llm(messages, structured_output=EnemyListOutput, temperature=_TEMPERATURE),
    )
    output: list[Any] = [None]
    for enemy in sorted(result.items, key=lambda e: e.id):
        d = enemy.model_dump()

        # params 길이/최솟값 보정
        if len(d["params"]) != 8:
            d["params"] = [60, 0, 10, 5, 5, 5, 8, 8]
        for i, min_val in enumerate(_ENEMY_PARAM_MINS):
            if d["params"][i] < min_val:
                d["params"][i] = min_val

        # battlerName 유효성 확인
        if d.get("battlerName") not in VALID_BATTLER_NAMES:
            logger.warning(
                "enemy '%s' battlerName='%s' not valid → fallback '%s'",
                d.get("name"),
                d.get("battlerName"),
                _BATTLER_FALLBACK,
            )
            d["battlerName"] = _BATTLER_FALLBACK

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

        # battlerName 검증 (sv_actors/)
        if d.get("battlerName") not in VALID_ACTOR_BATTLER_NAMES:
            logger.warning(
                "actor '%s' battlerName='%s' 유효하지 않음 → 빈 문자열로 초기화",
                d.get("name"),
                d.get("battlerName"),
            )
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
    assets: dict[str, Any] = {}
    for fname, result in zip(file_names, results):
        if isinstance(result, Exception):
            raise RuntimeError(f"{fname} 생성 실패: {result}") from result
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
