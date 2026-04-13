from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.constants import ALLOWED_TRAIT_CODES


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
