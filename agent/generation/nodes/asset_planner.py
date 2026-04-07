"""AssetPlanner 노드 — ID 사전 확정 (LLM 없음)."""

import logging

from agent.generation.registry.id_table import IdTable
from agent.generation.schemas.world_spec import WorldSpec
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

# 직업 역할별 기본 스킬 개수
ROLE_SKILL_COUNT: dict[str, int] = {
    "warrior": 3,
    "mage": 4,
    "healer": 3,
    "thief": 3,
    "archer": 3,
    "default": 2,
}

BASE_ITEM_NAMES = ["HP포션(소)", "HP포션", "MP포션(소)", "MP포션"]


async def asset_planner(state: GenerationState) -> dict:
    """WorldSpec → IdTable. 모든 에셋 ID를 1부터 순차 확정."""
    spec = WorldSpec(**state["world_spec"])
    logger.info(
        "[AssetPlanner] 시작: party=%d명, enemies=%d마리", len(spec.party), len(spec.enemies)
    )

    id_table, asset_counts = _build_id_table(spec)

    logger.info(
        "[AssetPlanner] 완료: actors=%d, classes=%d, skills=%d, items=%d, weapons=%d, armors=%d, enemies=%d",
        len(id_table.actors),
        len(id_table.classes),
        len(id_table.skills),
        len(id_table.items),
        len(id_table.weapons),
        len(id_table.armors),
        len(id_table.enemies),
    )

    return {
        "id_table": id_table.model_dump(),
        "asset_counts": asset_counts,
    }


def _build_id_table(spec: WorldSpec) -> tuple[IdTable, dict]:
    table = IdTable()
    counts: dict = {}

    # ── actors ──
    for i, member in enumerate(spec.party, start=1):
        table.actors[member.name] = i

    # ── classes (중복 제거, 순서 유지) ──
    seen_classes = list(dict.fromkeys(m.class_name for m in spec.party))
    for i, cls in enumerate(seen_classes, start=1):
        table.classes[cls] = i

    # ── skills (개수 기반 ID 사전 부여) ──
    table.skills["공격"] = 1
    table.skills["방어"] = 2
    skill_id = 3
    role_to_class: dict[str, str] = {m.class_name: m.role for m in spec.party}
    for cls_name in seen_classes:
        role = role_to_class.get(cls_name, "default")
        n_skills = ROLE_SKILL_COUNT.get(role, ROLE_SKILL_COUNT["default"])
        for j in range(n_skills):
            table.skills[f"{cls_name}_skill_{j + 1}"] = skill_id
            skill_id += 1

    counts["skills_per_class"] = {
        cls: ROLE_SKILL_COUNT.get(role_to_class.get(cls, "default"), 2) for cls in seen_classes
    }

    # ── items ──
    for i, name in enumerate(BASE_ITEM_NAMES, start=1):
        table.items[name] = i
    counts["item_count"] = len(BASE_ITEM_NAMES)

    # ── weapons (직업당 1개) ──
    for i, cls_name in enumerate(seen_classes, start=1):
        table.weapons[f"{cls_name}_무기"] = i
    counts["weapon_count"] = len(seen_classes)

    # ── armors (공통 방어구 세트) ──
    armor_slots = ["방패", "갑옷", "장신구"]
    for i, slot in enumerate(armor_slots, start=1):
        table.armors[slot] = i
    counts["armor_count"] = len(armor_slots)

    # ── enemies ──
    for i, enemy in enumerate(spec.enemies, start=1):
        table.enemies[enemy.name] = i

    # ── troops: 적 1종당 1그룹 ──
    for i, enemy in enumerate(spec.enemies, start=1):
        table.troops[f"{enemy.name}_group"] = i

    # ── maps ──
    for i, m in enumerate(spec.maps, start=1):
        table.maps[m.name] = i

    return table, counts
