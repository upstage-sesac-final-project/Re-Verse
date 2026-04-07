from typing import Literal

from pydantic import BaseModel, Field


class CharacterSpec(BaseModel):
    name: str
    class_name: str
    role: Literal["주인공", "서포터", "딜러", "탱커"]
    personality: str


class EnemySpec(BaseModel):
    name: str
    tier: Literal["weak", "normal", "elite", "boss"]
    location: str


class GameMapInfo(BaseModel):
    name: str
    map_type: Literal["town", "dungeon", "boss", "field"]
    description: str
    connects_to: list[str]


class GameSpec(BaseModel):
    title: str
    theme: str
    playtime_minutes: int = Field(default=10)
    story: dict = Field(description="synopsis, acts 등을 포함한 스토리 구조")
    characters: list[CharacterSpec]
    enemies: list[EnemySpec]
    maps: list[GameMapInfo] = Field(max_length=3)  # 최대 3개로 엄격히 제한
    key_items: list[str]
    skills: list[str] = Field(default_factory=list)


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
    battlerName: str = "Actor1_1"  # img/sv_actors/ 파일명 (확장자 제외)
    equips: list[int] = [0, 0, 0, 0, 0]
    traits: list[dict] = []
    note: str = ""
    profile: str = ""


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
    iconIndex: int = 0
    stypeId: int = 1
    scope: int = 1
    occasion: int = 1
    mpCost: int = 0
    tpCost: int = 0
    damage: RpgSkillDamage = Field(default_factory=RpgSkillDamage)
    effects: list[dict] = []
    note: str = ""


class RpgItem(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    itypeId: int = 1
    price: int = 100
    consumable: bool = True
    scope: int = 7
    occasion: int = 0
    effects: list[dict] = []
    note: str = ""


class RpgWeapon(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    wtypeId: int = 1
    price: int = 500
    params: list[int] = Field(default_factory=lambda: [0] * 8)
    traits: list[dict] = []
    animationId: int = 0
    note: str = ""


class RpgArmor(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    atypeId: int = 1
    price: int = 300
    params: list[int] = Field(default_factory=lambda: [0] * 8)
    traits: list[dict] = []
    note: str = ""


class RpgEnemyAction(BaseModel):
    conditionParam1: int = 0
    conditionParam2: int = 0
    conditionType: int = 0
    rating: int = 5
    skillId: int = 1


class RpgEnemy(BaseModel):
    id: int
    name: str
    battlerName: str = "Slime"
    battlerHue: int = 0
    params: list[int] = Field(default_factory=lambda: [100, 0, 10, 10, 10, 10, 10, 10])
    exp: int = 50
    gold: int = 20
    dropItems: list[dict] = []
    actions: list[RpgEnemyAction] = Field(default_factory=lambda: [RpgEnemyAction()])
    traits: list[dict] = []
    note: str = ""


class RpgTroopMember(BaseModel):
    enemyId: int
    x: int
    y: int
    hidden: bool = False


class RpgTroop(BaseModel):
    id: int
    name: str
    members: list[RpgTroopMember]
    pages: list[dict] = Field(
        default_factory=lambda: [
            {
                "conditions": {
                    "turnEnding": False,
                    "turnValid": False,
                    "turnA": 0,
                    "turnB": 0,
                    "enemyValid": False,
                    "enemyIndex": 0,
                    "enemyHp": 50,
                    "actorValid": False,
                    "actorId": 1,
                    "actorHp": 50,
                    "switchValid": False,
                    "switchId": 1,
                },
                "list": [{"code": 0, "indent": 0, "parameters": []}],
                "span": 0,
            }
        ]
    )


class RpgClassSpec(BaseModel):
    """LLM이 생성하는 직업 명세. params 2D 배열은 알고리즘으로 별도 생성."""

    id: int
    name: str
    # params 성장 곡선 결정용 힌트. 자유 문자열 (검사, 마법사, 성직자, 사이버네틱 전사 등 뭐든 가능)
    # asset_generator가 키워드 매칭으로 4가지 기본 곡선 중 하나로 분류
    combat_style: str = "warrior"
    traits: list[dict] = []
    learnings: list[dict] = []
    note: str = ""


class ClassesList(BaseModel):
    items: list[RpgClassSpec | None]


class ActorsList(BaseModel):
    items: list[RpgActor | None]


class SkillsList(BaseModel):
    items: list[RpgSkill | None]


class ItemsList(BaseModel):
    items: list[RpgItem | None]


class WeaponsList(BaseModel):
    items: list[RpgWeapon | None]


class ArmorsList(BaseModel):
    items: list[RpgArmor | None]


class EnemiesList(BaseModel):
    items: list[RpgEnemy | None]


class LandmarkSpec(BaseModel):
    name: str
    landmark_type: str  # "building", "exit", "decoration"
    position_hint: str  # "north", "south", "east", "west", "center" 등
    npc: str | None = None


class ExitSpec(BaseModel):
    direction: str  # "north", "south", "east", "west"
    to_map_id: int
    label: str


class MapSpec(BaseModel):
    map_id: int
    name: str
    map_type: Literal["town", "dungeon", "boss", "field"]
    width: int
    height: int
    tileset_id: int
    bgm: str
    atmosphere: str
    landmarks: list[LandmarkSpec]
    exits: list[ExitSpec]
    spawn_point: list[int] = Field(default_factory=lambda: [8, 6])  # [x, y]


class MapConnectionInfo(BaseModel):
    map_id: int
    spawn_point: list[int]
    exit_points: dict[int, list[int]]  # to_map_id -> [x, y]
