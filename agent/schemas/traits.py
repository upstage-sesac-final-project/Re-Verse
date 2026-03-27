from pydantic import BaseModel, ConfigDict, Field, model_validator

ALLOWED_TRAIT_CODES = {
    11,
    12, # 내성 > 약화 유효율
    13,
    14, # 내성 > 상태 무효화
    21,
    22,
    23, # 능력치 > 특수 능력치
    31,
    32,
    33,
    34,
    35, # 공격 스킬
    41,
    42,
    43,
    44,
    51,
    52,
    53,
    54,
    55,
    61,
    62,
    63,
    64,
}


class Trait(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int = Field(description="특성 코드")
    dataId: int = Field(ge=0, description="특성 대상 데이터 ID")
    value: int | float = Field(description="특성 값")

    @model_validator(mode="after")
    def validate_code(self):
        if self.code not in ALLOWED_TRAIT_CODES:
            raise ValueError(f"지원하지 않는 trait code: {self.code}")
        return self
