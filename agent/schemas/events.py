from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventAudio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", description="오디오 파일명")
    pan: int = Field(default=0, ge=-100, le=100, description="패닝")
    pitch: int = Field(default=100, ge=50, le=150, description="피치")
    volume: int = Field(default=90, ge=0, le=100, description="볼륨")


class MoveRouteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int = Field(description="이동경로 명령 코드")
    parameters: list[Any] = Field(default_factory=list, description="이동경로 명령 파라미터")


class MoveRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeat: bool = Field(default=False, description="반복 여부")
    skippable: bool = Field(default=False, description="실행 불가 시 스킵 여부")
    wait: bool = Field(default=False, description="완료까지 대기 여부")
    list: list[MoveRouteCommand] = Field(default_factory=list, description="이동경로 명령 목록")


class EventCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int = Field(description="이벤트 명령 코드")
    indent: int = Field(ge=0, description="이벤트 명령 들여쓰기 깊이")
    parameters: list[Any] = Field(default_factory=list, description="명령별 파라미터")

    @model_validator(mode="after")
    def validate_known_shapes(self):
        code = self.code
        p = self.parameters

        if code in {0, 351, 352, 353, 354} and p != []:
            raise ValueError(f"code={code}의 parameters는 빈 배열이어야 함")

        if code == 101 and len(p) != 4:
            raise ValueError("code=101은 parameters 길이가 4여야 함")

        if code == 401:
            if len(p) != 1 or not isinstance(p[0], str):
                raise ValueError("code=401은 [text] 형태여야 함")

        if code == 102 and len(p) < 5:
            raise ValueError("code=102는 parameters 길이가 최소 5여야 함")

        if code == 108:
            if len(p) != 1 or not isinstance(p[0], str):
                raise ValueError("code=108은 [comment] 형태여야 함")

        if code == 117 and len(p) != 1:
            raise ValueError("code=117은 [commonEventId] 형태여야 함")

        if code == 121 and len(p) != 3:
            raise ValueError("code=121은 [startId, endId, value] 형태여야 함")

        if code == 205:
            if len(p) != 2:
                raise ValueError("code=205는 [characterId, moveRoute] 형태여야 함")
            if not isinstance(p[1], dict | MoveRoute):
                raise ValueError("code=205의 두 번째 원소는 moveRoute 객체여야 함")

        if code == 230:
            if len(p) != 1:
                raise ValueError("code=230은 [duration] 형태여야 함")

        if code in {241, 245, 249, 250}:
            if len(p) != 1:
                raise ValueError(f"code={code}는 [audio] 형태여야 함")
            if not isinstance(p[0], dict | EventAudio):
                raise ValueError(f"code={code}의 첫 원소는 오디오 객체여야 함")

        if code == 320:
            if len(p) != 2:
                raise ValueError("code=320은 [actorId, nickname] 형태여야 함")

        if code in {355, 655}:
            if len(p) != 1 or not isinstance(p[0], str):
                raise ValueError(f"code={code}는 [scriptText] 형태여야 함")

        return self
