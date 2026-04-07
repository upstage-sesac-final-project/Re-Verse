from pydantic import BaseModel, Field


class IdTable(BaseModel):
    """모든 게임 요소의 ID를 중앙 관리하는 테이블."""

    actors: dict[str, int] = Field(default_factory=dict)
    classes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    items: dict[str, int] = Field(default_factory=dict)
    weapons: dict[str, int] = Field(default_factory=dict)
    armors: dict[str, int] = Field(default_factory=dict)
    enemies: dict[str, int] = Field(default_factory=dict)
    troops: dict[str, int] = Field(default_factory=dict)
    maps: dict[str, int] = Field(default_factory=dict)

    def get_id(self, category: str, name: str) -> int | None:
        return getattr(self, category, {}).get(name)


class SwitchTable(BaseModel):
    """스위치 및 변수 ID를 관리하는 테이블 (Immutable 패턴 지향)."""

    switches: dict[str, int] = Field(default_factory=dict)
    variables: dict[str, int] = Field(default_factory=dict)
    next_switch_id: int = 1
    next_variable_id: int = 1

    def allocate_switch(self, name: str) -> tuple["SwitchTable", int]:
        """새 스위치를 할당하고 업데이트된 테이블과 ID 반환."""
        if name in self.switches:
            return self, self.switches[name]

        new_switches = self.switches.copy()
        new_id = self.next_switch_id
        new_switches[name] = new_id

        new_table = self.model_copy(update={"switches": new_switches, "next_switch_id": new_id + 1})
        return new_table, new_id
