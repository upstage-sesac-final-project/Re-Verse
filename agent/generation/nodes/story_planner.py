"""F 노드 — story_planner: 전체 스토리를 맵별로 배분하여 MapStoryScript 생성.

canonical: docs/The World/event/story_driven_event_plan.md §5
"""

import logging
from typing import cast

from agent.core.llm_client import invoke_llm
from agent.generation.models import (
    GameSpec,
    MapSpec,
    MapStoryScript,
    StoryScriptOutput,
)
from agent.generation.progress import publish_progress
from agent.generation.prompts.story_planner_prompt import build_story_planner_prompt
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7  # 창의적 스토리 기획

_TYPE_TO_ACT: dict[str, int] = {"town": 0, "field": 1, "dungeon": 1, "boss": 2}


async def story_planner(state: GenerationState) -> dict:
    """F 노드: GameSpec + MapSpec → 맵별 MapStoryScript."""
    gen_id = state["generation_id"]
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "story_plan",
            "progress": 62,
            "message": "스토리 스크립트 작성 중...",
        },
    )

    story_script: dict[int, MapStoryScript] = {}
    try:
        messages = build_story_planner_prompt(game_spec, map_specs, id_table, switch_table)
        result = cast(
            StoryScriptOutput,
            await invoke_llm(
                messages, structured_output=StoryScriptOutput, temperature=_TEMPERATURE
            ),
        )
        story_script = _validate_story_script(result, id_table, map_specs)
    except Exception as e:
        logger.error("story_planner LLM 실패, 폴백 사용: %s", e)
        story_script = _fallback_story_script(map_specs)

    # LLM이 일부 맵 스크립트를 누락한 경우 폴백으로 보완
    for spec in map_specs:
        if spec.map_id not in story_script:
            logger.warning("story_planner: map_id=%d 스크립트 누락 → 폴백", spec.map_id)
            story_script[spec.map_id] = _fallback_single_map(spec)

    logger.info("story_planner 완료: %d개 맵 스크립트", len(story_script))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "story_plan",
            "summary": f"{len(story_script)}개 맵 스토리 스크립트 완성",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("story_plan")
    return {"story_script": story_script, "completed_phases": completed}


def _validate_story_script(
    result: StoryScriptOutput,
    id_table: IdTable,
    map_specs: list[MapSpec],
) -> dict[int, MapStoryScript]:
    """LLM 출력 검증: map_id 유효성 + NPC 이름 충돌 방지."""
    actor_names = set(id_table.actors.keys())
    map_id_set = {s.map_id for s in map_specs}
    out: dict[int, MapStoryScript] = {}

    for ms in result.maps:
        if ms.map_id not in map_id_set:
            logger.warning("story_planner: 알 수 없는 map_id=%d → 스킵", ms.map_id)
            continue

        # NPC 이름이 주인공과 충돌 → role을 표시 이름으로 사용 (자연스러운 대안)
        fixed_npcs = []
        for npc in ms.npcs:
            if npc.name in actor_names:
                # role이 유효하고 actor 이름과 겹치지 않으면 role을 이름으로 사용
                role_clean = npc.role.strip()
                if role_clean and role_clean not in actor_names:
                    fallback = role_clean
                else:
                    # role도 겹치면 role + 첫 글자 조합
                    fallback = f"{role_clean or '여행자'}{npc.name[0]}"
                logger.warning(
                    "story_planner: NPC '%s'이 액터 이름과 충돌 → '%s'로 변경 (role 사용)",
                    npc.name,
                    fallback,
                )
                npc = npc.model_copy(update={"name": fallback})
            fixed_npcs.append(npc)

        out[ms.map_id] = ms.model_copy(update={"npcs": fixed_npcs})
    return out


def _fallback_story_script(map_specs: list[MapSpec]) -> dict[int, MapStoryScript]:
    """LLM 완전 실패 시 맵 타입 기반 최소 스크립트."""
    return {spec.map_id: _fallback_single_map(spec) for spec in map_specs}


def _fallback_single_map(spec: MapSpec) -> MapStoryScript:
    return MapStoryScript(
        map_id=spec.map_id,
        act_index=_TYPE_TO_ACT.get(spec.map_type, 1),
        story_role=f"{spec.name} — {spec.map_type} 구역",
        npcs=[],
        required_events=[f"{spec.map_type} 맵 기본 이벤트 구성"],
        story_flags=[],
    )
