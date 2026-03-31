from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

from .traits import Trait


class Armor(BaseModel):
    id: int = Field(description="방어구 id, 분류용")
    note: str = Field(description="메모", default="")

    # --------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름")
    iconIndex: int = Field(description="일반 설정 > 아이콘", default=0)
    description: str = Field(description="일반 설정 > 설명", default="")
    atypeId: int = Field(description="일반 설정 > 방어구 유형", ge=0, le=6)
    price: int = Field(description="일반 설정 > 가격", default=100, ge=0, le=999999)
    etypeId: int = Field(description="장비 유형", ge=2, le=5)

    # --------------- 능력치 변화량

    params: list[int] = Field(description="능력치 변화량", min_length=8, max_length=8)

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: list[int]) -> list[int]:
        rules = [
            (0, 9999),  # 최대 HP
            (0, 9999),  # 최대 MP
            (0, 999),   # 공격
            (0, 999),   # 방어
            (0, 999),   # 마법 공격력
            (0, 999),   # 마법 방어력
            (0, 999),   # 민첩성
            (0, 999),   # 운
        ]

        for i, (ge, le) in enumerate(rules):
            if not (ge <= v[i] <= le):
                raise ValueError(f"params[{i}] must be between {ge} and {le}, got {v[i]}")
        return v

    # --------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


class ArmorsFile(RootModel[Annotated[list[Armor | None], Field(min_length=1)]]):
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Armors.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Armors.json의 첫 원소는 반드시 null이어야 함")
        return self
