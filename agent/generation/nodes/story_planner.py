"""F 노드 — story_planner: GameSpec + MapSpec → GameQuestPlan 생성.

canonical: docs/The World/event/story_driven_event_plan.md §5
"""

import logging
from typing import cast

from agent.core.llm_client import invoke_llm
from agent.generation.models import (
    GameQuestPlan,
    GameSpec,
    MapSpec,
)
from agent.generation.nodes.event_scaffolder import _fallback_quest_plan
from agent.generation.progress import publish_progress
from agent.generation.prompts.story_planner_prompt import build_story_planner_prompt
from agent.generation.registry.id_table import IdTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7  # 창의적 스토리 기획


async def story_planner(state: GenerationState) -> dict:
    """F 노드: GameSpec + MapSpec → GameQuestPlan."""
    gen_id = state["generation_id"]
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "story_plan",
            "progress": 62,
            "message": "퀘스트 계획 작성 중...",
        },
    )

    quest_plan: GameQuestPlan | None = None
    try:
        messages = build_story_planner_prompt(game_spec, map_specs)
        result = cast(
            GameQuestPlan,
            await invoke_llm(messages, structured_output=GameQuestPlan, temperature=_TEMPERATURE),
        )
        quest_plan = _validate_quest_plan(result, game_spec, map_specs, id_table)
    except Exception as e:
        logger.error("story_planner LLM 실패, 폴백 사용: %s", e)

    if quest_plan is None:
        quest_plan = _fallback_quest_plan(map_specs, id_table)

    logger.info(
        "story_planner 완료: %d개 퀘스트, %d개 맵 스크립트",
        len(quest_plan.quests),
        len(quest_plan.maps),
    )

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "story_plan",
            "summary": f"퀘스트 계획 완성 (퀘스트 {len(quest_plan.quests)}개, 맵 {len(quest_plan.maps)}개)",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("story_plan")
    return {
        "quest_plan": quest_plan,
        "story_script": None,
        "completed_phases": completed,
    }


def _validate_quest_plan(
    result: GameQuestPlan,
    game_spec: GameSpec,
    map_specs: list[MapSpec],
    id_table: IdTable,
) -> GameQuestPlan | None:
    """LLM 출력 검증. 치명적 문제가 있으면 None을 반환하여 폴백으로 넘긴다."""
    actor_names = set(id_table.actors.keys())
    map_id_set = {s.map_id for s in map_specs}
    boss_names = {e.name for e in game_spec.enemies if e.tier == "boss"}

    # ── boss_name 검증 ──────────────────────────────────────────────
    if result.boss_name not in boss_names:
        if boss_names:
            corrected = next(iter(boss_names))
            logger.warning(
                "story_planner: boss_name '%s' 미등록 → '%s'로 보정",
                result.boss_name,
                corrected,
            )
            result = result.model_copy(update={"boss_name": corrected})
        else:
            logger.warning("story_planner: boss 적이 없음 — boss_name 그대로 유지")

    # ── maps 검증: map_id 유효성 + NPC 이름 충돌 ──────────────────
    valid_maps = []
    for ms in result.maps:
        if ms.map_id not in map_id_set:
            logger.warning("story_planner: 알 수 없는 map_id=%d → 스킵", ms.map_id)
            continue

        fixed_npcs = []
        for npc in ms.npcs:
            if npc.name in actor_names:
                fallback_name = npc.role.strip() if npc.role.strip() else "안내인"
                if fallback_name in actor_names:
                    fallback_name = f"{fallback_name}_{npc.name[0]}"
                logger.warning(
                    "story_planner: NPC '%s'이 액터 이름과 충돌 → '%s'로 변경",
                    npc.name,
                    fallback_name,
                )
                npc = npc.model_copy(update={"name": fallback_name})
            fixed_npcs.append(npc)

        valid_maps.append(ms.model_copy(update={"npcs": fixed_npcs}))

    if not valid_maps:
        logger.error("story_planner: 유효한 맵 스크립트가 없음 → 폴백")
        return None

    result = result.model_copy(update={"maps": valid_maps})
    return result
