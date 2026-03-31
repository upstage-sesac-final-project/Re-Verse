from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

from .effects import Effect

import re

class Damage(BaseModel):
    type: int = Field(description="피해 > 유형", ge=0, le=6)
    elementId: int = Field(description="피해 > 속성", ge=-1)
    formula: str = Field(description="피해 > 계산식")
    critical: bool = Field(description="피해 > 치명타", default=True)
    variance: int = Field(description="피해 > 분산도", ge=0, le=100)

    @field_validator("formula")
    @classmethod
    def validate_formula(cls, v: str) -> str:
        if v == "0":
            return v

        token_pattern = r"(?:a|b)\.(?:atk|def|mhp|mat)|\d+(?:\.\d+)?|[+\-*/()]|\s+"
        consumed = "".join(
            m.group(0)
            for m in re.finditer(token_pattern, v)
        )

        if consumed != v:
            raise ValueError("허용되지 않은 damage formula 형식입니다.")

        return v


class Item(BaseModel):
    id: int = Field(description="아이템 id, 분류용")
    note: str = Field(description="메모", default="")

    # --------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름")
    iconIndex: int = Field(description="일반 설정 > 아이콘", default=0)
    description: str = Field(description="일반 설정 > 설명", default="")
    itypeId: int = Field(description="일반 설정 > 아이템 유형", default=1, ge=1, le=4)
    price: int = Field(description="일반 설정 > 가격", default=100, ge=0, le=999999)
    consumable: bool = Field(description="일반 설정 > 소모품", default=True)
    scope: int = Field(description="일반 설정 > 범위", ge=0, le=14)
    occasion: int = Field(description="일반 설정 > 사용 가능할 때", ge=0, le=3)

    # --------------- 발동

    speed: int = Field(description="발동 > 속도 보정", ge=0, le=2000)
    successRate: int = Field(description="발동 > 성공률", ge=1, le=100)
    repeats: int = Field(description="발동 > 연속 횟수", ge=1, le=9)
    tpGain: int = Field(description="발동 > TP 획득", ge=0, le=100)
    hitType: int = Field(description="발동 > 명중 유형", ge=0, le=2)
    animationId: int = Field(description="발동 > 애니메이션", ge=-1)

    # --------------- 피해

    damage: Damage = Field(description="피해 정의")

    # --------------- 사용 효과

    effects: list[Effect] = Field(description="사용 효과", default_factory=list)


class ItemsFile(RootModel[Annotated[list[Item | None], Field(min_length=1)]]):
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Items.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Items.json의 첫 원소는 반드시 null이어야 함")
        return self
