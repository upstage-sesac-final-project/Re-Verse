"""DSL 이벤트 모델 — event_planner(F) 출력 스키마.

canonical: docs/The_world/dsl_specification.md
canonical: docs/The_world/npc_conditional_and_shop.md
canonical: docs/The_world/game_ending_design.md
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str
    x: int
    y: int
    trigger: Literal["action_button"] = "action_button"
    character_name: str = "People1"  # 맵 위 스프라이트 파일명 (확장자 제외)
    character_index: int = 0  # 스프라이트 시트 내 인덱스 (0-7)
    face_image: str = ""
    face_index: int = 0
    dialogue: list[str]
    condition_switch: str | None = None
    alt_dialogue: list[str] | None = None
    set_switch: str | None = None


class TransferEvent(BaseModel):
    type: Literal["transfer"]
    name: str
    x: int
    y: int
    trigger: Literal["player_touch", "event_touch"] = "player_touch"
    to_map: str
    to_x: int
    to_y: int
    direction: str = "retain"
    set_switch: str | None = None
    character_name: str = "!Crystal"  # 워프 스프라이트 (기본: 크리스탈 포털)
    character_index: int = 0
    condition_switch: str | None = None  # 이 스위치 ON일 때만 이동 허용
    blocked_message: str = ""  # 조건 미충족 시 표시할 메시지


class ChestEvent(BaseModel):
    type: Literal["chest"]
    name: str
    x: int
    y: int
    item: str
    item_type: str = "item"  # "item" | "weapon" | "armor"
    amount: int = 1
    one_time: bool = True
    chest_switch: str | None = None
    dialogue_before: str = ""
    dialogue_after: str = ""
    character_name: str = "!Chest"  # 보물상자 스프라이트
    character_index: int = 0
    condition_switch: str | None = None  # 이 스위치 ON일 때만 보물상자 출현


class BattleOnWinAction(BaseModel):
    give_item: dict | None = None  # {"item": str, "amount": int}
    give_exp: int | None = None
    set_switch: str | None = None


class BattleEvent(BaseModel):
    type: Literal["battle"]
    name: str
    x: int
    y: int
    trigger: Literal["player_touch", "event_touch"] = "player_touch"
    troop: str
    escape_allowed: bool = True
    lose_condition: str = "game_over"
    on_win: list[BattleOnWinAction] = Field(default_factory=list)
    one_time: bool = True
    battle_switch: str | None = None
    character_name: str = "Monster"  # 몬스터 스프라이트
    character_index: int = 0


class ShopItem(BaseModel):
    item: str = ""
    item_type: str = "item"  # "item" | "weapon" | "armor"

    @model_validator(mode="before")
    @classmethod
    def _normalize_item_key(cls, v: dict) -> dict:
        """LLM이 {weapon: "검"} 또는 {armor: "갑옷"}으로 출력해도 item 키로 정규화."""
        if isinstance(v, dict) and not v.get("item"):
            for alt in ("weapon", "armor"):
                if alt in v:
                    v["item"] = v.pop(alt)
                    if "item_type" not in v:
                        v["item_type"] = alt
        return v


class ShopEvent(BaseModel):
    type: Literal["shop"]
    name: str
    x: int
    y: int
    trigger: Literal["action_button"] = "action_button"
    dialogue: str = ""
    items: list[ShopItem]
    purchase_only: bool = False
    character_name: str = "People1"  # 상점 NPC 스프라이트
    character_index: int = 0


class EndingEvent(BaseModel):
    type: Literal["ending"]
    name: str
    x: int
    y: int
    condition_switch: str
    lines: list[str]
    fade_type: Literal["black", "white"] = "black"
    action: Literal["title", "gameover"] = "title"


class GateEvent(BaseModel):
    """NPC 문지기 → 워프 전환 이벤트.

    조건 스위치가 모두 ON 되기 전까지는 NPC로 표시되어 힌트를 주고,
    모두 충족되면 자동으로 워프 스프라이트로 바뀌어 이동을 허용한다.
    """

    type: Literal["gate"]
    name: str
    x: int
    y: int
    to_map: str
    to_x: int
    to_y: int
    direction: str = "retain"
    # 조건 미충족 시 표시할 NPC 스프라이트
    keeper_character_name: str = "People1"
    keeper_character_index: int = 0
    # 조건별 힌트 대사 (len = len(condition_switches))
    condition_switches: list[str]  # 1~2개 스위치
    stage_dialogues: list[str]  # 조건 미충족 단계별 대사
    # 조건 충족 시 표시할 워프 스프라이트
    gate_character_name: str = "!Crystal"
    gate_character_index: int = 0


class QuestChestEvent(BaseModel):
    """퀘스트(NPC 대화 또는 몬스터 처치) 완료 후 보물상자로 전환되는 이벤트.

    quest_type="npc":    NPC 대화 → quest_switch ON → 보물상자 등장
    quest_type="battle": 몬스터 전투 → 승리 시만 quest_switch ON → 보물상자 등장
                         (도망/패배 시 quest_switch 미변경 → 몬스터 유지)
    """

    type: Literal["quest_chest"]
    name: str
    x: int
    y: int
    quest_type: Literal["npc", "battle"]
    quest_switch: str  # 퀘스트 완료 시 ON할 스위치
    # NPC 퀘스트 전용
    quest_dialogue: list[str] = []
    quest_character_name: str = "People1"
    quest_character_index: int = 0
    # 몬스터 전투 전용
    troop: str | None = None
    escape_allowed: bool = True
    lose_condition: str = "game_over"  # "game_over" | "continue"
    battle_character_name: str = "Monster"
    battle_character_index: int = 0
    # 보물상자 (공통)
    item: str
    item_type: str = "item"  # "item" | "weapon" | "armor"
    amount: int = 1
    chest_switch: str  # 상자 열림 one_time 스위치
    dialogue_before: str = ""
    dialogue_after: str = ""
    chest_character_name: str = "!Chest"
    chest_character_index: int = 0


DslEvent = Annotated[
    NpcEvent
    | TransferEvent
    | ChestEvent
    | BattleEvent
    | ShopEvent
    | EndingEvent
    | GateEvent
    | QuestChestEvent,
    Field(discriminator="type"),
]
