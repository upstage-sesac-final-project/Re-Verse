from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .traits import Trait


class Learning(BaseModel):
    level: int = Field(description="?대떦 ?ㅽ궗??諛곗슦???덈꺼", ge=1, le=99)
    note: str = Field(description="硫붾え", default="")
    skillId: int = Field(description="?듬뱷 ?ㅽ궗 id", ge=1)


class Class(BaseModel):
    id: int = Field(description="직업 id, 분류용")
    note: str = Field(description="메모", default="")

    #--------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름")
    expParams: list[int] = Field(
        description="일반 설정 > EXP 곡선",
        default_factory=lambda: [30, 20, 20, 40],
        min_length=4,
        max_length=4,
    )

    #--------------- 능력치 곡선

    params: list[list[int]] = Field(
        description=" 능력치 곡선, 첫번째 리스트 길이는 8로 고정",
        default_factory=lambda: [[] for _ in range(8)],
        min_length=8,
        max_length=8,
    )

    #--------------- 습득할 스킬

    learnings: list[Learning] = Field(description="습득할 스킬", default_factory=list)

    #--------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


class ClassesFile(RootModel[Annotated[list[Class | None], Field(min_length=1)]]):


    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Classes.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Classes.json의 첫 원소는 반드시 null이어야 함")
        return self
