from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, RootModel, model_validator


class SE(BaseModel):
    name: str = Field(description="효과음 > 파일명", default="")
    pan: int = Field(description="효과음 > PAN", default=0, ge=-100, le=100)
    pitch: int = Field(description="효과음 > PITCH", default=100, ge=50, le=150)
    volume: int = Field(description="효과음 > VOLUME", default=90, ge=0, le=100)

class SoundTiming(BaseModel):
    frame: int = Field(description="효과음 > 프레임", default=0, ge=0)
    se: SE = Field(description="효과음 설정")

class FlashTiming(BaseModel):
    frame: int = Field(description="플래시 > 프레임", default=0, ge=0)
    duration: int = Field(description="플래시 > 지속 시간", default=0, ge=0)
    color: tuple[int, int, int, int] = Field(
        description="플래시 > RGBA 색상값",
        default=(255, 255, 255, 255),
    )

class Rotation(BaseModel):
    x: int = Field(description="파티클 효과 > 회전 > X", default=0)
    y: int = Field(description="파티클 효과 > 회전 > Y", default=0)
    z: int = Field(description="파티클 효과 > 회전 > Z", default=0)

class Animation(BaseModel):
    id: int = Field(description="애니메이션 id, 분류용")

    # --------------- 일반 설정

    name: str = Field(description="일반 설정 > 이름", default="")
    displayType: int = Field(description="일반 설정 > 디스플레이 유형", default=0, ge=0, le=2)
    alignBottom: bool | None = Field(description="일반 설정 > 아래로 정렬", default=None)

    # --------------- 파티클 효과

    effectName: str = Field(description="파티클 효과 > 파일명")
    scale: int = Field(description="파티클 효과 > 배율", ge=10, le=1000)
    speed: int = Field(description="파티클 효과 > 속도", ge=10, le=1000)
    rotation: Rotation = Field(description="파티클 효과 > 회전", default_factory=Rotation)
    offsetX: int = Field(description="파티클 효과 > 오프셋 X", default=0)
    offsetY: int = Field(description="파티클 효과 > 오프셋 Y", default=0)

    # --------------- 효과음

    soundTimings: list[SoundTiming] = Field(description="효과음 타이밍", default_factory=list)

    # --------------- 플래시

    flashTimings: list[FlashTiming] = Field(description="플래시 타이밍", default_factory=list)

    # --------------- timings
    timings: list = Field(description="MV 호환용 레거시 필드로 추정", default_factory=list)

class AnimationsFile(RootModel[Annotated[list[Animation | None], Field(min_length=1)]]):
    @model_validator(mode="after")
    def validate_leading_null(self):
        if not self.root:
            raise ValueError("Animations.json은 비어 있을 수 없음")
        if self.root[0] is not None:
            raise ValueError("Animations.json 첫 원소는 반드시 null이어야 함")

        for idx, animation in enumerate(self.root):
            if animation is None:
                continue

            if "timings" in animation.model_fields_set and idx != 1:
                raise ValueError(
                    f"Animations.json[{idx}].timings는 허용되지 않음. timings는 첫 번째 실제 애니메이션(인덱스 1)에서만 허용됨"
                )

        return self
