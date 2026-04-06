"""B 노드 — asset_planner: GameSpec → IdTable + SwitchTable (LLM 없음).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.B
canonical: docs/The_world/switch_allocation.md
"""

import logging

from agent.generation.models import GameSpec
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_GENERATION_ORDER = [
    "classes",
    "actors",
    "skills",
    "items",
    "weapons",
    "armors",
    "enemies",
    "troops",
]


def asset_planner(state: GenerationState) -> dict:
    """B 노드: GameSpec → IdTable, SwitchTable, generation_order."""
    spec: GameSpec = state["game_spec"]  # type: ignore[assignment]

    id_table = _build_id_table(spec)
    switch_table = _build_switch_table(spec)

    logger.info(
        "asset_planner 완료: actors=%d enemies=%d maps=%d switches=%d",
        len(id_table.actors),
        len(id_table.enemies),
        len(id_table.maps),
        len(switch_table.switches),
    )

    completed = list(state.get("completed_phases", []))
    completed.append("planning")
    return {
        "id_table": id_table,
        "switch_table": switch_table,
        "generation_order": _GENERATION_ORDER,
        "completed_phases": completed,
    }


def _build_id_table(spec: GameSpec) -> IdTable:
    """GameSpec 모든 에셋에 1부터 순차 ID 할당."""
    actors = {c.name: i + 1 for i, c in enumerate(spec.characters)}
    unique_class_names = list(dict.fromkeys(c.class_name for c in spec.characters))
    classes = {name: i + 1 for i, name in enumerate(unique_class_names)}
    skills = {s: i + 1 for i, s in enumerate(spec.skills)}
    items = {k: i + 1 for i, k in enumerate(spec.key_items)}
    enemies = {e.name: i + 1 for i, e in enumerate(spec.enemies)}
    maps = {m.name: i + 1 for i, m in enumerate(spec.maps)}

    # weapons / armors: 기본 1개씩 (캐릭터당 starter 장비)
    weapons: dict[str, int] = {}
    armors: dict[str, int] = {}
    for i, char in enumerate(spec.characters):
        weapon_name = f"{char.name}의 무기"
        armor_name = f"{char.name}의 방어구"
        weapons[weapon_name] = i + 1
        armors[armor_name] = i + 1

    # troops: 적 그룹 (weak/normal/elite 3변형 + boss 단독)
    troops: dict[str, int] = {}
    tid = 1
    for enemy in spec.enemies:
        if enemy.tier == "boss":
            troops[f"{enemy.name}_단독"] = tid
            tid += 1
        elif enemy.tier == "elite":
            troops[f"{enemy.name}_단독"] = tid
            tid += 1
        else:
            for count in (1, 2, 3):
                troops[f"{enemy.name}×{count}"] = tid
                tid += 1

    return IdTable(
        actors=actors,
        classes=classes,
        skills=skills,
        items=items,
        weapons=weapons,
        armors=armors,
        enemies=enemies,
        troops=troops,
        maps=maps,
    )


def _build_switch_table(spec: GameSpec) -> SwitchTable:
    """GameSpec 구조에서 예측 가능한 스위치를 사전 할당."""
    table = SwitchTable()

    # 1. boss/elite 처치 스위치
    for enemy in spec.enemies:
        if enemy.tier in ("boss", "elite"):
            table, _ = table.allocate_switch(f"{enemy.name}_defeated")

    # 2. 스토리 막 진행 스위치
    acts = spec.story.get("acts", [])
    for i in range(len(acts)):
        table, _ = table.allocate_switch(f"act_{i + 1}_started")

    # 3. 던전 클리어 스위치
    for m in spec.maps:
        if m.type == "dungeon":
            table, _ = table.allocate_switch(f"{m.name}_cleared")

    # 4. 게임 클리어 스위치
    table, _ = table.allocate_switch("game_cleared")

    return table
