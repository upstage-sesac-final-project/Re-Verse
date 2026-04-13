from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.constants import ALLOWED_EFFECT_CODES, EFFECT_RULES


class Effect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int = Field(description="효과 코드")
    dataId: int = Field(default=0, description="효과 대상 데이터 ID")
    value1: int | float = Field(default=0, description="효과 값 1")
    value2: int | float = Field(default=0, description="효과 값 2")

    @model_validator(mode="after")
    def validate_effect(self):
        validate_effect_by_rule(self)
        return self


# EFFECT_RULES 는 agent.constants 에서 import


def validate_effect_by_rule(effect: Effect) -> None:
    if effect.code not in ALLOWED_EFFECT_CODES:
        raise ValueError(f"지원하지 않는 effect code: {effect.code}")

    rule = EFFECT_RULES.get(effect.code)
    if rule is None:
        # 허용된 코드지만 아직 상세 규칙 미정인 경우
        return

    _validate_field("dataId", effect.dataId, rule.get("dataId"), effect.code)
    _validate_field("value1", effect.value1, rule.get("value1"), effect.code)
    _validate_field("value2", effect.value2, rule.get("value2"), effect.code)


def _validate_field(
    field_name: str,
    value: int | float,
    field_rule: dict | None,
    code: int,
) -> None:
    if field_rule is None:
        return

    rule_type = field_rule.get("type")

    if rule_type == "exact":
        expected = field_rule["value"]
        if value != expected:
            raise ValueError(f"code {code}: {field_name} must be exactly {expected}, got {value}")

    elif rule_type == "range":
        min_value = field_rule.get("min")
        max_value = field_rule.get("max")

        if min_value is not None and value < min_value:
            raise ValueError(f"code {code}: {field_name} must be >= {min_value}, got {value}")

        if max_value is not None and value > max_value:
            raise ValueError(f"code {code}: {field_name} must be <= {max_value}, got {value}")

    elif rule_type == "one_of":
        allowed_values = field_rule["values"]
        if value not in allowed_values:
            raise ValueError(
                f"code {code}: {field_name} must be one of {allowed_values}, got {value}"
            )

    else:
        raise ValueError(f"code {code}: unknown validation rule type for {field_name}: {rule_type}")
