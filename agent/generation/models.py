"""Full Generation 핵심 데이터 모델.

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §3
"""

from typing import Literal

from pydantic import BaseModel, field_validator

# ── A 노드 (game_designer) 출력 ─────────────────────────────────────────────


class CharacterSpec(BaseModel):
    name: str
    class_name: str
    role: str  # "주인공" | "서포터"
    personality: str


class EnemySpec(BaseModel):
    name: str
    tier: str  # "weak" | "normal" | "elite" | "boss"
    location: str


class GameMapInfo(BaseModel):
    """GameSpec 내부의 단순 맵 정보.

    D 노드 출력의 상세 MapSpec과 구분 (D-1 설계 결정).
    """

    name: str
    type: str  # "town" | "dungeon" | "boss" | "field"
    description: str
    connects_to: list[str]


class SkillSpec(BaseModel):
    name: str
    class_name: str = "공용"


class GameSpec(BaseModel):
    title: str
    theme: str
    playtime_minutes: int = 7
    story: dict  # {"synopsis": str, "acts": list[str]}
    characters: list[CharacterSpec]
    enemies: list[EnemySpec]
    maps: list[GameMapInfo]
    key_items: list[str] = []
    skills: list[SkillSpec] = []
    weapons: list[str] = []
    armors: list[str] = []

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, v: list) -> list:
        """하위 호환: list[str] → list[SkillSpec] 자동 변환."""
        return [SkillSpec(name=s) if isinstance(s, str) else s for s in v]


# ── D 노드 (map_designer) 출력 ──────────────────────────────────────────────


class LandmarkSpec(BaseModel):
    name: str
    landmark_type: str  # "building" | "exit" | "decoration"
    position_hint: str  # "north" | "south-center" | "center" 등
    npc: str | None = None


class ExitSpec(BaseModel):
    direction: str  # "north" | "south" | "east" | "west"
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
    spawn_point: tuple[int, int]


# Solar Pro 2 래퍼 (list 직접 반환 불가)
class MapSpecListOutput(BaseModel):
    items: list[MapSpec]


# ── F 노드 (story_planner) 출력 ────────────────────────────────────────────


class NpcInfo(BaseModel):
    """story_planner가 사전 확정하는 NPC 1명의 명세.

    event_planner는 이 목록에서 NPC 이름·대사를 가져와 이벤트를 생성한다.
    이름은 story_planner 단계에서 주인공 이름과 겹치지 않도록 중앙 관리된다.
    """

    name: str  # NPC 고유 이름
    role: str  # 역할 설명 (예: "퀘스트 부여 촌장", "무기 상인")
    before_dialogue: list[str]  # 스토리 조건 충족 전 대사
    after_dialogue: list[str] = []  # 스토리 조건 충족 후 대사 (condition_switch ON 시)
    condition_switch: str | None = None  # 조건 스위치 이름 (None이면 항상 before_dialogue)


class MapStoryScript(BaseModel):
    """맵 1개의 스토리 스크립트.

    story_planner가 생성하고, event_planner가 이벤트 기획의 기준으로 사용한다.
    """

    map_id: int
    act_index: int  # 0=1막, 1=2막, 2=3막
    story_role: str  # 이 맵이 전체 스토리에서 담당하는 역할 (1~2문장)
    npcs: list[NpcInfo]  # 이 맵에 등장할 NPC 목록 (이름 사전 확정)
    required_events: list[str]  # event_planner에 대한 이벤트 생성 지시사항
    story_flags: list[str] = []  # 이 맵에서 ON되어야 하는 스위치 이름 목록


# Solar Pro 2 래퍼 (list 직접 반환 불가)
class StoryScriptOutput(BaseModel):
    maps: list[MapStoryScript]


# ── E 노드 (tile_generator) 출력 보조 ──────────────────────────────────────


class MapConnectionInfo(BaseModel):
    """맵 출구 좌표 정보. tile_generator 에서 확정, F 노드에 전달."""

    map_id: int
    exit_tiles: list[dict]  # [{"direction": "north", "x": 15, "y": 0}, ...]
    entry_tiles: list[dict]  # [{"from_map_id": 2, "x": 15, "y": 1}, ...]
