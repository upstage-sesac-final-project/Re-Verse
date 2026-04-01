from __future__ import annotations

import builtins
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .events import EventAudio, EventCommand, MoveRoute


class MapEventPageConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorId: int = Field(default=1, ge=1)
    actorValid: bool = Field(default=False)
    itemId: int = Field(default=1, ge=1)
    itemValid: bool = Field(default=False)
    selfSwitchCh: str = Field(default="A", min_length=1, max_length=1)
    selfSwitchValid: bool = Field(default=False)
    switch1Id: int = Field(default=1, ge=1)
    switch1Valid: bool = Field(default=False)
    switch2Id: int = Field(default=1, ge=1)
    switch2Valid: bool = Field(default=False)
    variableId: int = Field(default=1, ge=1)
    variableValid: bool = Field(default=False)
    variableValue: int = Field(default=0)


class MapEventPageImage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characterIndex: int = Field(default=0, ge=0)
    characterName: str = Field(default="")
    direction: int = Field(default=2)
    pattern: int = Field(default=0, ge=0)
    tileId: int = Field(default=0, ge=0)


class MapEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conditions: MapEventPageConditions
    directionFix: bool = Field(default=False)
    image: MapEventPageImage
    list: builtins.list[EventCommand] = Field(default_factory=list)
    moveFrequency: int = Field(default=3, ge=1, le=6)
    moveRoute: MoveRoute
    moveSpeed: int = Field(default=3, ge=1, le=6)
    moveType: int = Field(default=0, ge=0, le=3)
    priorityType: int = Field(default=0, ge=0, le=2)
    stepAnime: bool = Field(default=False)
    through: bool = Field(default=False)
    trigger: int = Field(default=0, ge=0, le=4)
    walkAnime: bool = Field(default=True)


class MapEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    name: str = Field(default="")
    note: str = Field(default="")
    pages: list[MapEventPage] = Field(default_factory=list, min_length=1)
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)


class MapFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autoplayBgm: bool = Field(default=False)
    autoplayBgs: bool = Field(default=False)
    battleback1Name: str = Field(default="")
    battleback2Name: str = Field(default="")
    bgm: EventAudio
    bgs: EventAudio
    disableDashing: bool = Field(default=False)
    displayName: str = Field(default="")
    encounterList: list[Any] = Field(default_factory=list)
    encounterStep: int = Field(default=30, ge=1)
    height: int = Field(ge=1)
    note: str = Field(default="")
    parallaxLoopX: bool = Field(default=False)
    parallaxLoopY: bool = Field(default=False)
    parallaxName: str = Field(default="")
    parallaxShow: bool = Field(default=True)
    parallaxSx: int = Field(default=0)
    parallaxSy: int = Field(default=0)
    scrollType: int = Field(default=0, ge=0, le=3)
    specifyBattleback: bool = Field(default=False)
    tilesetId: int = Field(default=0, ge=0)
    width: int = Field(ge=1)
    data: list[int] = Field(default_factory=list)
    events: list[MapEvent | None] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_map_shape(self):
        if self.events and self.events[0] is not None:
            raise ValueError("Map*.json events[0] must be null")

        layer_size = self.width * self.height
        if self.data and layer_size > 0 and len(self.data) % layer_size != 0:
            raise ValueError("Map*.json data length must be a multiple of width * height")

        return self
