from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, model_validator

from .events import EventCommand


class TroopMember(BaseModel):
    enemyId: int = Field(description="적 그룹 멤버 > 적 ID", default=1, ge=0)
    hidden: bool = Field(
        description="적 그룹 멤버 > 출현 시 숨김 여부(투명화)",
        default=False,
    )
    x: int = Field(
        description="적 그룹 멤버 > X 좌표",
        default=0,
    )
    y: int = Field(
        description="적 그룹 멤버 > Y 좌표",
        default=0,
    )


class TroopPageCondition(BaseModel):
    turnEnding: bool = Field(
        description="페이지 조건 > 액터 HP 비율",
        default=False,
    )

    turnValid: bool = Field(
        description="페이지 조건 > 턴 조건 사용 여부",
        default=False,
    )
    turnA: int = Field(description="페이지 조건 > 턴 A", default=0, ge=0)
    turnB: int = Field(description="페이지 조건 > 턴 B", default=0, ge=0)

    enemyValid: bool = Field(
        description="페이지 조건 > 적 조건 사용 여부",
        default=False,
    )
    enemyIndex: int = Field(description="페이지 조건 > 적 인덱스", default=0, ge=0)
    enemyHp: int = Field(description="페이지 조건 > 적 HP 비율", default=50, ge=0, le=100)

    actorValid: bool = Field(
        description="페이지 조건 > 액터 조건 사용 여부",
        default=False,
    )
    actorId: int = Field(description="페이지 조건 > 액터 ID", default=1, ge=0)
    actorHp: int = Field(description="페이지 조건 > 액터 HP 비율", default=50, ge=0, le=100)

    switchValid: bool = Field(
        description="페이지 조건 > 스위치 조건 사용 여부",
        default=False,
    )
    switchId: int = Field(description="페이지 조건 > 스위치 ID", default=1, ge=0)


class TroopPage(BaseModel):
    conditions: TroopPageCondition = Field(description="전투 이벤트 > 발동 조건")
    list: list[EventCommand] = Field(
        description="전투 이벤트 > 이벤트 명령 목록", default_factory=list
    )
    span: int = Field(description="전투 이벤트 > 적용 범위", default=0, ge=0, le=2)


class Troop(BaseModel):
    id: int = Field(description="적 군단 id, 분류용")

    # --------------- 일반 설정

    name: str = Field(description="일반 설정 > 적 군단 이름", default="")
    members: list[TroopMember] = Field(
        description="일반 설정 > 적 군단 멤버 목록", default_factory=list
    )

    # --------------- 전투 이벤트

    pages: list[TroopPage] = Field(description="전투 이벤트", default_factory=list)


class TroopsFile(RootModel[Annotated[list[Troop | None], Field(min_length=1)]]):
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Troops.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Troops.json의 첫 원소는 반드시 null이어야 함")
        return self
