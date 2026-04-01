from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

from .traits import Trait


class DropItem(BaseModel):
    kind: int = Field(description="드롭 아이템 > 드롭 종류", default=0, ge=0, le=3)
    dataId: int = Field(description="드롭 아이템 > 아이템 인덱스", default=1)
    denominator: int = Field(description="드롭 아이템 > 출현율", default=1, ge=1, le=1000)


class Action(BaseModel):
    skillId: int = Field(description="행동 패턴 > 스킬 ID")
    rating: int = Field(description="행동 패턴 > 우선도", ge=1, le=9)
    conditionType: int = Field(description="행동 패턴 > 조건 유형", default=5, ge=0, le=6)
    conditionParam1: int = Field(description="행동 패턴 > 첫번째 조건 결정값", ge=0, le=100)
    conditionParam2: int = Field(description="행동 패턴 > 두번째 조건 결정값", ge=0, le=100)


class Enemy(BaseModel):
    id: int = Field(description="적 캐릭터 id, 분류용")
    note: str = Field(description="메모", default="")

    # --------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름", default="")
    battlerHue: int = Field(description="일반 설정 > 색조", default=0, ge=0, le=360)
    battlerName: str = Field(description="일반 설정 > 이미지")
    params: list[int] = Field(description="일반 설정 > 설정값", min_length=8, max_length=8)

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: list[int]) -> list[int]:
        rules = [
            (1, 999999),  # 최대 HP
            (0, 9999),  # 최대 MP
            (0, 999),  # 공격
            (0, 999),  # 방어
            (0, 999),  # 마법 공격력
            (0, 999),  # 마법 방어력
            (0, 999),  # 민첩성
            (0, 999),  # 운
        ]

        for i, (ge, le) in enumerate(rules):
            if not (ge <= v[i] <= le):
                raise ValueError(f"params[{i}] must be between {ge} and {le}, got {v[i]}")
        return v

    # --------------- 보상

    exp: int = Field(description="보상 > EXP", default=10, ge=0, le=9999999)
    gold: int = Field(description="보상 > 소지금액", default=5, ge=0, le=9999999)

    # --------------- 드롭 아이템

    dropItems: list[DropItem] = Field(description="드롭 아이템", min_length=3, max_length=3)

    # --------------- 행동 패턴

    actions: list[Action] = Field(description="행동 패턴", default_factory=list)

    # --------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


class EnemiesFile(RootModel[Annotated[list[Enemy | None], Field(min_length=1)]]):
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Enemies.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Enemies.json의 첫 원소는 반드시 null이어야 함")
        return self
