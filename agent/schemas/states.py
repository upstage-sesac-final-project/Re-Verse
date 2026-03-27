from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .traits import Trait


class State(BaseModel):
    id: int = Field(description="상태 id, 분류용")
    note: str = Field(description="메모", default="")

    #--------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름", default="")
    iconIndex: int = Field(description="일반 설정 > 아이콘", default=0)
    restriction: int = Field(description="일반 설정 > 행동 제한")
    priority: int = Field(description="일반 설정 > 우선권")
    motion: int = Field(description="일반 설정 > [SV] 모션")
    overlay: int = Field(description="일반 설정 > [SV] 오버레이")

    #--------------- 해제 조건

    removeAtBattleEnd: bool = Field(
        description="해제 조건 > 전투 종료 시에 해제", default=False
    )
    removeByRestriction: bool = Field(
        description="해제 조건 > 행동 제한에 따라 해제", default=False
    )
    autoRemovalTiming: int = Field(
        description="해제 조건 > 자동 해제의 타이밍", ge=0, le=2
    )
    minTurns: int = Field(
        description="해제 조건 > 지속 순번 횟수(최솟값)",
        ge=0,
        le=9999,
    )
    maxTurns: int = Field(
        description="해제 조건 > 지속 순번 횟수(최댓값)",
        ge=0,
        le=9999,
    )
    removeByDamage: bool = Field(
        description="해제 조건 > 피해로 인한 해제", default=False
    )
    chanceByDamage: int = Field(
        description="해제 조건 > 피해로 인한 해제(체크 시) > 해제 확률",
        ge=0,
        le=100,
    )
    removeByWalking: bool = Field(
        description="해제 조건 > 보행으로 해제", default=False
    )
    stepsToRemove: int = Field(
        description="해제 조건 > 보행으로 해제(체크 시) > 보행 횟수",
        ge=1,
        le=9999,
    )
    releaseByDamage: bool = Field(description="뭐임?!")

    #--------------- 메시지

    message1: str = Field(description="메시지 > 액터가 해당 상태가 됐을 때:", default="")
    message2: str = Field(description="메시지 > 적 캐릭터가 해당 상태가 됐을 때:", default="")
    message3: str = Field(description="메시지 > 해당 상태가 계속될 때:", default="")
    message4: str = Field(description="메시지 > 해당 상태가 해제될 때:", default="")
    messageType: int = Field(description="뭐임?!") # 0으로 바꾸고 테스트

    #--------------- 특성

    traits: list[Trait] = Field(description="특성 목록", default_factory=list)


class StatesFile(RootModel[Annotated[list[State | None], Field(min_length=1)]]):

    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("States.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("States.json의 첫 원소는 반드시 null이어야 함")
        return self
