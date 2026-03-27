from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, model_validator

from .traits import Trait


class Actor(BaseModel):
    id: int = Field(description="액터 id, 분류용")
    note: str = Field(description="메모", default="")

    #--------------- 일반 설정

    name: str = Field(description="액터 이름")
    nickname: str = Field(description="액터 별명", default="")
    classId: int = Field(description="직업 id", ge=1)
    initialLevel: int = Field(description="초기 레벨", default=1, ge=1, le=99)
    maxLevel: int = Field(description="최대 레벨", default=99, ge=1, le=99)
    profile: str = Field(description="설명", default="")

    #--------------- 이미지

    faceName: str = Field(description="읽어올 페이스 파일명", pattern=r"^Actor\d+$")
    faceIndex: int = Field(
        description="인덱스 = 얼굴 이미지 결정, faceName보다 값 1 줄어야 함",
        ge=0,
        le=7,
    )
    characterName: str = Field(
        description="읽어올 보행 캐릭터 파일명", pattern=r"^Actor\d+$"
    )
    characterIndex: int = Field(
        description="인덱스 = 보행 캐릭터 결정, characterName보다 값 1 줄어야 함",
        ge=0,
        le=7,
    )
    battlerName: str = Field(description="전투 캐릭터 결정", pattern=r"^Actor\d+_\d+$")

    #--------------- 초기 장비

    equips: list[int] = Field(
        description="장비 id 리스트. 허용 길이는 해당 actor의 classId가 참조하는 설정을 따름",
        default_factory=list,
    )

    #--------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


# class ActorsFile(RootModel[Annotated[list[Actor | None], Field(min_length=1)]]):
#     model_config = ConfigDict(extra="forbid")

#     @model_validator(mode="after")
#     def validate_leading_null(self):
#         if not self.root:
#             raise ValueError("Actors.json은 비어 있을 수 없음")
#         if self.root[0] is not None:
#             raise ValueError("Actors.json 첫 원소는 반드시 null이어야 함")
#         return self
    
class ActorsFile(RootModel[Annotated[list[Actor | None], Field(min_length=1)]]):
    
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Actors.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Actors.json 첫 원소는 반드시 null이어야 함")
        return self
