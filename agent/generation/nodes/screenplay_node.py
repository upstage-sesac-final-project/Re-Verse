"""각본(screenplay) 노드 — story_planner + event_planner를 대체.

LLM 1회 호출로 전체 게임 각본을 생성하고,
파서가 DSL 이벤트로 변환한다.
"""

import logging
from typing import cast

from agent.core.llm_client import invoke_llm
from agent.generation.models import GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.prompts.screenplay_prompt import build_screenplay_prompt
from agent.generation.registry.id_table import IdTable
from agent.generation.screenplay_parser import parse_screenplay, scenes_to_dsl
from agent.generation.sprite_mapping import _build_troop_sprite_map, _fix_battle_sprites
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7


async def screenplay_node(state: GenerationState) -> dict:
    """각본 노드: LLM 각본 생성 → 파싱 → DSL 이벤트."""
    gen_id = state["generation_id"]
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    generated_assets: dict = state.get("generated_assets") or {}

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "screenplay",
            "progress": 65,
            "message": "게임 각본 작성 중...",
        },
    )

    event_dsl: dict[int, list] = {}
    screenplay_text = ""

    for attempt in range(3):
        try:
            prompt = build_screenplay_prompt(game_spec, map_specs, id_table)
            screenplay_text = cast(str, await invoke_llm(prompt, temperature=_TEMPERATURE))
            scenes = parse_screenplay(screenplay_text)

            if len(scenes) < len(map_specs) // 2:
                logger.warning(
                    "각본 Scene %d개 (맵 %d개 중), 재시도 %d",
                    len(scenes),
                    len(map_specs),
                    attempt + 1,
                )
                continue

            event_dsl = scenes_to_dsl(scenes, map_specs, id_table)

            # 스프라이트 매핑 적용
            if game_spec:
                troop_to_sprite = _build_troop_sprite_map(game_spec, id_table, generated_assets)
                for map_id, events in event_dsl.items():
                    event_dsl[map_id] = _fix_battle_sprites(events, troop_to_sprite)

            logger.info(
                "각본 생성 완료: %d개 Scene, %d개 맵 이벤트",
                len(scenes),
                sum(len(v) for v in event_dsl.values()),
            )
            break

        except Exception as e:
            logger.warning("각본 생성 시도 %d 실패: %s", attempt + 1, e)

    if not event_dsl:
        logger.error("각본 생성 3회 실패 → 폴백 사용")
        from agent.generation.nodes.event_scaffolder import (
            _fallback_quest_plan,
            scaffold_map_events,
        )

        quest_plan = _fallback_quest_plan(map_specs, id_table)
        for spec in map_specs:
            event_dsl[spec.map_id] = scaffold_map_events(spec, quest_plan, id_table)

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "screenplay",
            "summary": f"{len(event_dsl)}개 맵 각본 변환 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("screenplay")
    return {"event_dsl": event_dsl, "completed_phases": completed}
