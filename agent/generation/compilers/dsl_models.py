"""DSL 이벤트 모델 — event_planner(F) 출력 스키마.

canonical: docs/The_world/dsl_specification.md
canonical: docs/The_world/npc_conditional_and_shop.md
canonical: docs/The_world/game_ending_design.md
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str
    x: int
    y: int
    trigger: str = "action_button"
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
    trigger: str = "player_touch"
    to_map: str
    to_x: int
    to_y: int
    direction: str = "retain"
    set_switch: str | None = None
    character_name: str = ""  # 워프 스프라이트 (기본 투명)
    character_index: int = 0


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


class BattleOnWinAction(BaseModel):
    give_item: dict | None = None  # {"item": str, "amount": int}
    give_exp: int | None = None
    set_switch: str | None = None


class BattleEvent(BaseModel):
    type: Literal["battle"]
    name: str
    x: int
    y: int
    trigger: str = "player_touch"
    troop: str
    escape_allowed: bool = True
    lose_condition: str = "game_over"
    on_win: list[BattleOnWinAction] = Field(default_factory=list)
    one_time: bool = True
    battle_switch: str | None = None
    character_name: str = "Monster"  # 몬스터 스프라이트
    character_index: int = 0


class ShopItem(BaseModel):
    item: str
    item_type: str = "item"  # "item" | "weapon" | "armor"


class ShopEvent(BaseModel):
    type: Literal["shop"]
    name: str
    x: int
    y: int
    trigger: str = "action_button"
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


DslEvent = Annotated[
    NpcEvent | TransferEvent | ChestEvent | BattleEvent | ShopEvent | EndingEvent,
    Field(discriminator="type"),
]
