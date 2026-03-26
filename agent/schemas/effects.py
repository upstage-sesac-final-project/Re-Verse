from pydantic import BaseModel, ConfigDict, Field, model_validator

ALLOWED_EFFECT_CODES = {11, 12, 13, 21, 22, 31, 32, 33, 34, 41, 42, 43, 44}

class Effect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int = Field(description="효과 코드")
    dataId: int = Field(ge=0, description="효과 대상 데이터 ID")
    value1: float = Field(description="효과 값 1")
    value2: float = Field(description="효과 값 2")

    @model_validator(mode="after")
    def validate_code(self):
        if self.code not in ALLOWED_EFFECT_CODES:
            raise ValueError(f"지원하지 않는 effect code: {self.code}")
        return self