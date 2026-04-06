"""D 노드 — map_designer: GameSpec → list[MapSpec] (LLM 1회).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.D
canonical: docs/The_world/map_generation.md §D
"""

import logging
from typing import cast

from agent.core.llm_client import invoke_llm
from agent.generation.mapgen import MAP_SIZE_BY_TYPE
from agent.generation.models import GameSpec, MapSpec, MapSpecListOutput
from agent.generation.progress import publish_progress
from agent.generation.prompts.map_designer_prompt import build_map_designer_prompt
from agent.generation.registry.id_table import IdTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def map_designer(state: GenerationState) -> dict:
    """D 노드: GameSpec → 상세 MapSpec 목록."""
    gen_id = state["generation_id"]
    spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "map_design",
            "progress": 49,
            "message": "맵 설계 중...",
        },
    )

    messages = build_map_designer_prompt(spec, id_table)
    result = cast(
        MapSpecListOutput, await invoke_llm(messages, structured_output=MapSpecListOutput)
    )

    # 맵 크기 강제 (LLM 출력 덮어쓰기)
    map_specs: list[MapSpec] = []
    for ms in result.items:
        w, h, tileset = MAP_SIZE_BY_TYPE.get(ms.map_type, (30, 30, 1))
        fixed = ms.model_copy(update={"width": w, "height": h, "tileset_id": tileset})
        map_specs.append(fixed)

    logger.info("map_designer 완료: %d개 맵", len(map_specs))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "map_design",
            "summary": f"{len(map_specs)}개 맵 설계 완료 ({', '.join(m.name for m in map_specs)})",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("map_design")
    return {"map_specs": map_specs, "completed_phases": completed}
