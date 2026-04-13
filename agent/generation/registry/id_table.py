"""IdTable — 에셋 이름→ID 매핑 레지스트리.

B 노드(asset_planner)에서 사전 확정하여 모든 노드가 공유.
"""

from pydantic import BaseModel


class IdTable(BaseModel):
    actors: dict[str, int] = {}  # "해럴드" → 1
    classes: dict[str, int] = {}
    skills: dict[str, int] = {}
    items: dict[str, int] = {}
    weapons: dict[str, int] = {}
    armors: dict[str, int] = {}
    enemies: dict[str, int] = {}
    troops: dict[str, int] = {}
    maps: dict[str, int] = {}  # "출발 마을" → 1

    def get_id(self, category: str, name: str) -> int | None:
        """카테고리에서 이름으로 ID를 조회. 없으면 None."""
        return getattr(self, category, {}).get(name)
