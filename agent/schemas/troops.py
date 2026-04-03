from __future__ import annotations

import builtins
from typing import Annotated

from pydantic import BaseModel, Field, RootModel, model_validator

from .events import EventCommand


class TroopMember(BaseModel):
    enemyId: int = Field(default=1, ge=0)
    hidden: bool = Field(default=False)
    x: int = Field(default=0)
    y: int = Field(default=0)


class TroopPageCondition(BaseModel):
    turnEnding: bool = Field(default=False)
    turnValid: bool = Field(default=False)
    turnA: int = Field(default=0, ge=0)
    turnB: int = Field(default=0, ge=0)
    enemyValid: bool = Field(default=False)
    enemyIndex: int = Field(default=0, ge=0)
    enemyHp: int = Field(default=50, ge=0, le=100)
    actorValid: bool = Field(default=False)
    actorId: int = Field(default=1, ge=0)
    actorHp: int = Field(default=50, ge=0, le=100)
    switchValid: bool = Field(default=False)
    switchId: int = Field(default=1, ge=0)


class TroopPage(BaseModel):
    conditions: TroopPageCondition
    list: builtins.list[EventCommand] = Field(default_factory=list)
    span: int = Field(default=0, ge=0, le=2)


class Troop(BaseModel):
    id: int
    name: str = Field(default="")
    members: list[TroopMember] = Field(default_factory=list)
    pages: list[TroopPage] = Field(default_factory=list)


class TroopsFile(RootModel[Annotated[list[Troop | None], Field(min_length=1)]]):
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Troops.json cannot be empty")
        if self.root[0] is not None:
            raise ValueError("Troops.json first element must be null")
        return self
