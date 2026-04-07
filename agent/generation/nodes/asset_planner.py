import logging

from agent.generation.registry.id_table import IdTable, SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def asset_planner_node(state: GenerationState) -> GenerationState:
    """B. 설계사 노드: GameSpec을 바탕으로 모든 요소의 ID를 사전 확정."""
    logger.info("--- NODE: asset_planner ---")
    game_spec = state.get("game_spec")
    if not game_spec:
        raise ValueError("game_spec이 상태에 존재하지 않습니다.")

    id_table = IdTable()

    # 1. 액터(Characters) 및 직업(Classes) ID 할당
    # System.json partyMembers[0] = 1 고정이므로 주인공 Actor가 반드시 ID 1을 받아야 함
    chars = game_spec["characters"]
    chars_sorted = sorted(chars, key=lambda c: 0 if c.get("role") == "주인공" else 1)

    for i, char in enumerate(chars_sorted, start=1):
        id_table.actors[char["name"]] = i
        if char["class_name"] not in id_table.classes:
            id_table.classes[char["class_name"]] = len(id_table.classes) + 1

    # 2. 맵(Maps) ID 할당
    for i, g_map in enumerate(game_spec["maps"], start=1):
        id_table.maps[g_map["name"]] = i

    # 3. 적(Enemies) 및 부대(Troops) ID 할당
    for i, enemy in enumerate(game_spec["enemies"], start=1):
        id_table.enemies[enemy["name"]] = i
        # 단순화를 위해 적 1종당 1개의 부대 생성
        id_table.troops[enemy["name"]] = i

    # 4. 아이템(Key Items) ID 할당
    for i, item_name in enumerate(game_spec["key_items"], start=1):
        id_table.items[item_name] = i

    # 5. 스킬(Skills) ID 할당
    # TODO: GameSpec에 skills 리스트가 명시적으로 추가되어야 함 (game_designer_prompt 참고)
    skills = game_spec.get("skills", ["공격", "방어", "회복"])
    for i, skill_name in enumerate(skills, start=1):
        id_table.skills[skill_name] = i

    # 스위치 테이블 초기화
    switch_table = SwitchTable()
    # 기본 시스템 스위치 (예: 보스 처치 여부)
    switch_table, _ = switch_table.allocate_switch("boss_defeated")

    logger.info(
        "ID 할당 완료: Actors %d, Maps %d, Enemies %d",
        len(id_table.actors),
        len(id_table.maps),
        len(id_table.enemies),
    )

    return {
        **state,
        "id_table": id_table.model_dump(),
        "switch_table": switch_table.model_dump(),
        "completed_phases": ["planner"],
        "current_phase": "planner",
    }
