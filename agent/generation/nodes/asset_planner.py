"""B 노드 — asset_planner: GameSpec → IdTable + SwitchTable (LLM 없음).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.B
canonical: docs/The_world/switch_allocation.md
"""

import logging

from agent.generation.models import GameSpec
from agent.generation.progress import publish_progress
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


async def asset_planner(state: GenerationState) -> dict:
    """B 노드: GameSpec → IdTable, SwitchTable, generation_order."""
    gen_id = state["generation_id"]
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

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "planning",
            "summary": f"에셋 계획 완료: 액터 {len(id_table.actors)}명, 적 {len(id_table.enemies)}종, 맵 {len(id_table.maps)}개",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("planning")
    return {
        "id_table": id_table,
        "switch_table": switch_table,
        "generation_order": _GENERATION_ORDER,
        "completed_phases": completed,
    }


# ── 적 전용 스킬 템플릿 (알고리즘 생성) ──────────────────────────────────────

_ENEMY_SKILL_TEMPLATES: dict[str, list[str]] = {
    "weak": [],
    "normal": ["적_강타"],
    "elite": ["적_강타", "적_전체공격"],
    "boss": ["적_강타", "적_전체공격", "적_자가회복", "적_버프"],
}


def _build_id_table(spec: GameSpec) -> IdTable:
    """GameSpec 모든 에셋에 1부터 순차 ID 할당."""
    actors = {c.name: i + 1 for i, c in enumerate(spec.characters)}
    unique_class_names = list(dict.fromkeys(c.class_name for c in spec.characters))
    classes = {name: i + 1 for i, name in enumerate(unique_class_names)}

    # skills: id=1="공격", id=2="방어" 예약 → 플레이어 스킬 id=3~ → 적 스킬 그 뒤
    skills: dict[str, int] = {"공격": 1, "방어": 2}
    next_id = 3
    for s in spec.skills:
        if s.name not in skills:
            skills[s.name] = next_id
            next_id += 1

    # 적 전용 스킬 (tier별 템플릿, 중복 제거)
    enemy_skill_names: set[str] = set()
    for enemy in spec.enemies:
        for sname in _ENEMY_SKILL_TEMPLATES.get(enemy.tier, []):
            enemy_skill_names.add(sname)
    for sname in sorted(enemy_skill_names):
        if sname not in skills:
            skills[sname] = next_id
            next_id += 1
    items = {k: i + 1 for i, k in enumerate(spec.key_items)}
    enemies = {e.name: i + 1 for i, e in enumerate(spec.enemies)}
    maps = {m.name: i + 1 for i, m in enumerate(spec.maps)}

    # weapons / armors: GameSpec에서 가져오거나 fallback (하위 호환)
    if spec.weapons:
        weapons = {w: i + 1 for i, w in enumerate(spec.weapons)}
    else:
        weapons = {f"{char.name}의 무기": i + 1 for i, char in enumerate(spec.characters)}
    if spec.armors:
        armors = {a: i + 1 for i, a in enumerate(spec.armors)}
    else:
        armors = {f"{char.name}의 방어구": i + 1 for i, char in enumerate(spec.characters)}

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

    # 5. 아이템/무기/방어구 획득 체스트 스위치 (story_planner acquisitions chest_switch용)
    for item_name in spec.key_items:
        table, _ = table.allocate_switch(f"{item_name}_chest")
    for weapon_name in spec.weapons:
        table, _ = table.allocate_switch(f"{weapon_name}_chest")
    for armor_name in spec.armors:
        table, _ = table.allocate_switch(f"{armor_name}_chest")

    # 6. 맵별 NPC 퀘스트 스위치 (story_planner NPC set_switch용, 맵당 최대 3개)
    for m in spec.maps:
        for idx in range(1, 4):
            table, _ = table.allocate_switch(f"{m.name}_npc{idx}_talked")

    # 7. 배틀 quest_chest 전용 독립 스위치 (NPC talked 스위치와 충돌 방지)
    #    battle quest_chest.quest_switch는 반드시 이 스위치를 사용해야 함
    for item_name in spec.key_items:
        table, _ = table.allocate_switch(f"{item_name}_battle_won")
    for weapon_name in spec.weapons:
        table, _ = table.allocate_switch(f"{weapon_name}_battle_won")
    for armor_name in spec.armors:
        table, _ = table.allocate_switch(f"{armor_name}_battle_won")

    return table
