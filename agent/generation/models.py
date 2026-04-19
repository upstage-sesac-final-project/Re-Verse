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


class GuardrailResult(BaseModel):
    decision: Literal["safe", "unsafe"]
    reason: str


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
    original_file_name: str | None = None  # 예: "Map284.json"


# Solar Pro 2 래퍼 (list 직접 반환 불가)
class MapSpecListOutput(BaseModel):
    items: list[MapSpec]


# ── F 노드 (story_planner) 출력 ────────────────────────────────────────────


class NpcScript(BaseModel):
    """대본의 NPC 항목.

    story_planner가 이름·역할·대사를 사전 확정한다.
    event_planner는 이 목록 그대로 NPC 이벤트를 생성한다.
    """

    name: str  # NPC 고유 이름 (주인공 이름과 달라야 함)
    role: str  # 역할 설명 (예: "퀘스트 부여 촌장", "무기 상인")
    dialogues: list[str]  # 대사 목록 (한 문장씩)
    set_switch: str | None = None  # 대화 완료 후 ON할 스위치 (switch_table에서 선택)


class ItemAcquisition(BaseModel):
    """대본의 아이템/무기/방어구 획득 항목.

    event_planner는 이 항목을 quest_chest 이벤트로 구현한다.
    """

    item_name: str  # id_table 정확한 이름
    item_type: str  # "item" | "weapon" | "armor"
    chest_switch: str  # 획득 후 ON할 스위치 (switch_table에서 선택, 게이트 조건으로 사용 가능)


class MoveScript(BaseModel):
    """대본의 이동 항목.

    forward: 다음 맵으로 이동 (gate 이벤트, 최대 1개)
    backward: 이전 맵으로 귀환 (transfer 이벤트, 조건 없음, 최대 1개)
    """

    direction: Literal["forward", "backward"]
    to_map_name: str  # game_spec.maps의 정확한 맵 이름
    stage_dialogues: list[str] = []  # forward만: 조건 미충족 힌트 대사
    # len(stage_dialogues) == len(acquisitions) — 코드가 condition_switches를 acquisitions.chest_switch로 자동 구성


class MapScreenplay(BaseModel):
    """맵 1개의 대본 + 이벤트 체크리스트 (B 방식).

    story_planner가 생성하고, event_planner가 이 체크리스트를 1:1로 이벤트로 구현한다.
    대본에 없는 이벤트는 생성하지 않는다.
    """

    map_id: int
    narrative: str  # 자연어 대본 (2~4문장, 스토리 흐름 서술)
    npcs: list[NpcScript]  # NPC 목록 (최대 3명, boss 맵은 0명 가능)
    acquisitions: list[ItemAcquisition]  # 획득 가능한 아이템/무기/방어구 (맵당 1~2개)
    moves: list[MoveScript]  # 이동 목록 (forward 최대 1개, backward 최대 1개)
    has_boss: bool = False  # 보스 전투 포함 여부 (boss 맵 타입에만 true)
    boss_name: str | None = None  # 보스 이름 (has_boss=True일 때, id_table.troops 기준)


# Solar Pro 2 래퍼 (list 직접 반환 불가)
class ScreenplayOutput(BaseModel):
    maps: list[MapScreenplay]


# ── E 노드 (tile_generator) 출력 보조 ──────────────────────────────────────


class MapConnectionInfo(BaseModel):
    """맵 출구 좌표 정보. tile_generator 에서 확정, F 노드에 전달."""

    map_id: int
    exit_tiles: list[dict]  # [{"direction": "north", "x": 15, "y": 0}, ...]
    entry_tiles: list[dict]  # [{"from_map_id": 2, "x": 15, "y": 1}, ...]
