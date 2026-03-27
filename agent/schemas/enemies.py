from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from .traits import Trait


class DropItem(BaseModel):
    kind: int = Field(description="아이템 드롭 > 드롭 종류", default=0, ge=0, le=3)
    dataId: int = Field(description="아이템 드롭 > 아이템 인덱스", default=1)
    denominator: int = Field(description="아이템 드롭 > 출현율", default=1, ge=1, le=999)


class Action(BaseModel):
    skillId: int = Field(description="행동 패턴 > 스킬 ID", default=1)
    rating: int = Field(description="행동 패턴 > 우선도", ge=1, le=9)
    conditionType: int = Field(description="행동 패턴 > 조건 유형", ge=0, le=6)
    conditionParam1: int = Field(description="행동 패턴 > 첫번째 condition 결정값")
    conditionParam2: int = Field(description="행동 패턴 > 두번째 condition 결정값")


class Enemy(BaseModel):
    id: int = Field(description="적 캐릭터 id, 분류용")
    note: str = Field(description="메모", default="")

    #--------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름", default="")

    #--------------- 보상

    exp: int = Field(description="보상 > EXP", ge=0, default=0)
    gold: int = Field(description="보상 > 소지금액", ge=0, default=0)

    #--------------- 드롭 아이템

    dropItems: list[DropItem] = Field(description="드롭 아이템", default_factory=list)

    #--------------- 행동 패턴

    actions: list[Action] = Field(description="행동 패턴", default_factory=list)

    #--------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


class EnemiesFile(RootModel[Annotated[list[Enemy | None], Field(min_length=1)]]):

    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Enemies.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Enemies.json의 첫 원소는 반드시 null이어야 함")
        return self
