"""SwitchTable — 스위치/변수 이름→ID 레지스트리.

불변(immutable) 설계: allocate_switch()는 새 인스턴스를 반환.
LangGraph 체크포인트와의 호환성을 위해 직접 변경 금지.

canonical: docs/The_world/switch_allocation.md
"""

import re

from pydantic import BaseModel


def normalize_switch_name(name: str) -> str:
    """스위치 이름 정규화: 공백→밑줄, 연속 밑줄 제거, 양쪽 밑줄 제거.

    사전 할당 스위치(맵 이름에 공백 포함)와 LLM 출력(밑줄 사용)의
    불일치를 방지한다.
    예: "고대 유적_cleared" → "고대_유적_cleared"
    """
    normalized = name.replace(" ", "_")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


class SwitchTable(BaseModel):
    switches: dict[str, int] = {}  # "boss_defeated" → 1
    variables: dict[str, int] = {}
    next_switch_id: int = 1
    next_variable_id: int = 1

    def allocate_switch(self, name: str) -> tuple["SwitchTable", int]:
        """스위치 이름으로 ID 할당. 불변 — 새 인스턴스 + ID 반환.

        이름은 정규화 후 저장 (공백→밑줄). 이미 존재하면 기존 ID.
        """
        name = normalize_switch_name(name)
        if name in self.switches:
            return self, self.switches[name]
        new_id = self.next_switch_id
        new_table = self.model_copy(
            update={
                "switches": {**self.switches, name: new_id},
                "next_switch_id": new_id + 1,
            }
        )
        return new_table, new_id

    def allocate_variable(self, name: str) -> tuple["SwitchTable", int]:
        """변수 이름으로 ID 할당. 불변 — 새 인스턴스 + ID 반환."""
        if name in self.variables:
            return self, self.variables[name]
        new_id = self.next_variable_id
        new_table = self.model_copy(
            update={
                "variables": {**self.variables, name: new_id},
                "next_variable_id": new_id + 1,
            }
        )
        return new_table, new_id

    def to_rpgmaker_switches(self) -> list[str | None]:
        """System.json switches 배열 형식으로 변환.

        Returns:
            [null, "switch1_name", "switch2_name", ...] (index 0 = null)
        """
        if not self.switches:
            return [None]
        max_id = max(self.switches.values())
        result: list[str | None] = [None] * (max_id + 1)
        for name, sid in self.switches.items():
            result[sid] = name
        return result

    def to_rpgmaker_variables(self) -> list[str | None]:
        """System.json variables 배열 형식으로 변환."""
        if not self.variables:
            return [None]
        max_id = max(self.variables.values())
        result: list[str | None] = [None] * (max_id + 1)
        for name, vid in self.variables.items():
            result[vid] = name
        return result
