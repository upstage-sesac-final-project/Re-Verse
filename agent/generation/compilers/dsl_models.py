from typing import Literal

from pydantic import BaseModel, Field


class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str
    x: int
    y: int
    trigger: str = "action_button"
    character_name: str = "People1"  # img/characters/ 파일명 (확장자 제외)
    character_index: int = 0  # 0~7, 스프라이트 시트 내 위치
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
    direction: str = "down"
    set_switch: str | None = None


class ChestItem(BaseModel):
    item: str
    item_type: Literal["item", "weapon", "armor", "gold"]
    amount: int = 1


class ChestEvent(BaseModel):
    type: Literal["chest"]
    name: str
    x: int
    y: int
    item: str
    item_type: Literal["item", "weapon", "armor", "gold"]
    amount: int = 1
    one_time: bool = True
    chest_switch: str | None = None
    dialogue_before: str = ""
    dialogue_after: str = ""


class ShopItem(BaseModel):
    item: str
    item_type: Literal["item", "weapon", "armor"]


class ShopEvent(BaseModel):
    type: Literal["shop"]
    name: str
    x: int
    y: int
    trigger: str = "action_button"
    dialogue: str = ""
    items: list[ShopItem]
    purchase_only: bool = False


class BattleWinAction(BaseModel):
    give_item: dict | None = None
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
    lose_condition: Literal["game_over", "continue"] = "game_over"
    on_win: list[BattleWinAction] = Field(default_factory=list)
    one_time: bool = True
    battle_switch: str | None = None


DslEvent = NpcEvent | TransferEvent | ChestEvent | ShopEvent | BattleEvent


class DslEventList(BaseModel):
    events: list[DslEvent]
