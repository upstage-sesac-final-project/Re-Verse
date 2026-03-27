from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, model_validator

from .traits import Trait


class Weapons(BaseModel):
    id: int = Field(description="무기 id, 분류용")
    note: str = Field(description="메모", default="")
    etypeId: int = Field(description="장비 유형", ge=0, le=5)

    #--------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름")
    iconIndex: int = Field(description="일반 설정 > 아이콘", default=0)
    description: str = Field(description="일반 설정 > 설명", default="")
    wtypeId: int = Field(description="일반 설정 > 무기 유형", ge=0, le=12)
    price: int = Field(description="일반 설정 > 가격", default=100, ge=0, le=999999)
    animationId: int = Field(description="일반 설정 > 애니메이션", ge=-1, le=120)

    #--------------- 능력치 변화량

    params: list[int] = Field(description="능력치 변화량", default=[0, 0, 8, 0, 0, 0, 0, 0])

    #--------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


class WeaponsFile(RootModel[Annotated[list[Weapons | None], Field(min_length=1)]]):

    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Weapons.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Weapons.json의 첫 원소는 반드시 null이어야 함")
        return self
