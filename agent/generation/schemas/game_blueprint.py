"""GameBlueprint — 2차 LLM(Architect) 출력 스키마 (창작 콘텐츠 전용).

RPG Maker MZ의 구조적/정적 필드(damage 객체, effects[], hitType 등)는
Builder가 조립하므로 여기에 포함하지 않는다.
"""

from pydantic import BaseModel, ConfigDict, Field

# ── System ──


class SystemBlueprint(BaseModel):
    game_title: str
    locale: str = "ko_KR"
    currency_unit: str = "G"
    party_members: list[int]  # actor id 목록
    start_map_id: int = 1
    start_x: int = 8
    start_y: int = 6
    skill_types: list[str] = Field(default_factory=lambda: ["", "마법", "필살기"])
    weapon_types: list[str] = Field(default_factory=lambda: ["", "검", "지팡이", "단검", "활"])
    armor_types: list[str] = Field(default_factory=lambda: ["", "방어구", "마법 방어구"])
    elements: list[str] = Field(
        default_factory=lambda: [
            "",
            "물리적",
            "불",
            "얼음",
            "천둥",
            "물",
            "흙",
            "바람",
            "빛",
            "어둠",
        ]
    )


# ── Class ──


class LearningEntry(BaseModel):
    level: int
    skill_id: int


class ClassBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    role: str = "default"  # "warrior", "mage", "healer", "thief", "default"
    exp_params: list[int] = Field(default_factory=lambda: [30, 20, 30, 30])
    learnings: list[LearningEntry] = Field(default_factory=list)
    note: str = ""


# ── Actor ──


class ActorBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    class_id: int
    initial_level: int = 1
    max_level: int = 99
    equip_weapon_id: int = 0
    equip_armor_ids: list[int] = Field(default_factory=lambda: [0, 0, 0, 0])
    face_name: str = "Actor1"
    face_index: int = 0  # 0~7
    character_name: str = "Actor1"
    character_index: int = 0  # 0~7
    battler_name: str = "Actor1_1"


# ── Skill ──


class SkillBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    description: str = ""
    skill_type_id: int = 1  # 1=마법, 2=필살기
    mp_cost: int = 0
    tp_cost: int = 0
    scope: int = 1
    """scope: 0=없음, 1=적1명, 2=적전체, 7=아군1명, 8=아군전체, 11=사용자"""
    occasion: int = 1
    """occasion: 0=항상, 1=전투중만, 2=메뉴에서만, 3=사용불가"""
    damage_type: int = 1
    """damage_type: 0=없음, 1=HP데미지, 2=MP데미지, 3=HP회복, 4=MP회복"""
    element: str = "물리적"  # 원소 이름
    formula: str = "a.atk * 2 - b.def"


# ── Item ──


class ItemBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    description: str = ""
    price: int = 0
    scope: int = 7  # 7=아군1명
    occasion: int = 0  # 0=항상
    recover_hp_rate: int = 0  # HP 회복 % (0~100)
    recover_hp_flat: int = 0
    recover_mp_rate: int = 0
    recover_mp_flat: int = 0


# ── Weapon ──


class WeaponBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    description: str = ""
    weapon_type: str = "검"
    price: int = 0
    params: list[int] = Field(default_factory=lambda: [0, 0, 0, 0, 0, 0, 0, 0])


# ── Armor ──


class ArmorBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    description: str = ""
    armor_type: str = "방어구"
    equip_slot: str = "body"  # "shield"|"head"|"body"|"accessory"
    price: int = 0
    params: list[int] = Field(default_factory=lambda: [0, 0, 0, 0, 0, 0, 0, 0])


# ── Enemy ──


class EnemyDropSpec(BaseModel):
    kind: str  # "item"|"weapon"|"armor"
    name: str
    denominator: int = 3  # 1/N 확률


class EnemyBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = 0  # repair 함수가 IdTable에서 채움
    name: str
    battler_name: str = "Slime"  # repair 함수가 tier 기반으로 채움
    tier: str = "normal"  # "weak"|"normal"|"elite"|"boss"
    exp: int = 10
    gold: int = 5
    drop_items: list[EnemyDropSpec] = Field(default_factory=list)
    skill_ids: list[int] = Field(default_factory=lambda: [1])


# ── Troop ──


class TroopMember(BaseModel):
    enemy_id: int
    x: int = 400
    y: int = 400


class TroopBlueprint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    members: list[TroopMember] = Field(default_factory=list)


# ── GameBlueprint (루트) ──


class GameBlueprint(BaseModel):
    """2차 LLM(Architect)이 생성하는 창작 콘텐츠.
    LLM이 빠뜨린 섹션은 repair 함수가 WorldSpec + IdTable에서 채운다.
    """

    model_config = ConfigDict(extra="ignore")

    system: SystemBlueprint
    classes: list[ClassBlueprint] = Field(default_factory=list)
    actors: list[ActorBlueprint] = Field(default_factory=list)
    skills: list[SkillBlueprint] = Field(default_factory=list)
    items: list[ItemBlueprint] = Field(default_factory=list)
    weapons: list[WeaponBlueprint] = Field(default_factory=list)
    armors: list[ArmorBlueprint] = Field(default_factory=list)
    enemies: list[EnemyBlueprint] = Field(default_factory=list)
    troops: list[TroopBlueprint] = Field(default_factory=list)
