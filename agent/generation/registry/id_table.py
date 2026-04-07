"""IdTable — 모든 에셋의 이름→ID 매핑. LLM 호출 전에 확정된다."""

from pydantic import BaseModel, Field


class IdTable(BaseModel):
    """RPG Maker MZ는 인덱스 0이 null이므로 실제 ID는 1부터 시작."""

    actors: dict[str, int] = Field(default_factory=dict)
    classes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    items: dict[str, int] = Field(default_factory=dict)
    weapons: dict[str, int] = Field(default_factory=dict)
    armors: dict[str, int] = Field(default_factory=dict)
    enemies: dict[str, int] = Field(default_factory=dict)
    troops: dict[str, int] = Field(default_factory=dict)
    maps: dict[str, int] = Field(default_factory=dict)

    def get_id(self, category: str, name: str) -> int:
        """이름으로 ID 조회. KeyError면 즉시 예외."""
        return getattr(self, category)[name]
