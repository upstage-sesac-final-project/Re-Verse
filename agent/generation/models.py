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
    role_type: str = "balanced"  # "warrior" | "mage" | "healer" | "thief" | "balanced"
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


# ── E 노드 (tile_generator) 출력 보조 ──────────────────────────────────────


class MapConnectionInfo(BaseModel):
    """맵 출구 좌표 정보. tile_generator 에서 확정, F 노드에 전달."""

    map_id: int
    exit_tiles: list[dict]  # [{"direction": "north", "x": 15, "y": 0}, ...]
    entry_tiles: list[dict]  # [{"from_map_id": 2, "x": 15, "y": 1}, ...]
