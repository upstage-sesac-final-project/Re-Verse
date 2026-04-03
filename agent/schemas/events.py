from __future__ import annotations

import builtins
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventAudio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="")
    pan: int = Field(default=0, ge=-100, le=100)
    pitch: int = Field(default=100, ge=50, le=150)
    volume: int = Field(default=90, ge=0, le=100)


class MoveRouteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int
    parameters: list[Any] = Field(default_factory=list)


class MoveRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeat: bool = Field(default=False)
    skippable: bool = Field(default=False)
    wait: bool = Field(default=False)
    list: builtins.list[MoveRouteCommand] = Field(default_factory=list)


class EventCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int
    indent: int = Field(ge=0)
    parameters: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_known_shapes(self):
        code = self.code
        params = self.parameters

        if code in {0, 351, 352, 353, 354} and params != []:
            raise ValueError(f"code={code} expects an empty parameters array")

        if code == 101 and len(params) != 4:
            raise ValueError("code=101 expects exactly 4 parameters")

        if code == 401 and (len(params) != 1 or not isinstance(params[0], str)):
            raise ValueError("code=401 expects a single text string")

        if code == 102 and len(params) < 5:
            raise ValueError("code=102 expects at least 5 parameters")

        if code == 108 and (len(params) != 1 or not isinstance(params[0], str)):
            raise ValueError("code=108 expects a single comment string")

        if code == 117 and len(params) != 1:
            raise ValueError("code=117 expects [commonEventId]")

        if code == 121 and len(params) != 3:
            raise ValueError("code=121 expects [startId, endId, value]")

        if code == 205:
            if len(params) != 2:
                raise ValueError("code=205 expects [characterId, moveRoute]")
            if not isinstance(params[1], dict | MoveRoute):
                raise ValueError("code=205 second parameter must be a moveRoute object")

        if code == 230 and len(params) != 1:
            raise ValueError("code=230 expects [duration]")

        if code in {241, 245, 249, 250}:
            if len(params) != 1:
                raise ValueError(f"code={code} expects [audio]")
            if not isinstance(params[0], dict | EventAudio):
                raise ValueError(f"code={code} first parameter must be an audio object")

        if code == 320 and len(params) != 2:
            raise ValueError("code=320 expects [actorId, nickname]")

        if code in {355, 655} and (len(params) != 1 or not isinstance(params[0], str)):
            raise ValueError(f"code={code} expects [scriptText]")

        return self
