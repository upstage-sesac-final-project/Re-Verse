"""D 노드 — map_designer: GameSpec → list[MapSpec] (LLM 1회).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.D
canonical: docs/The_world/map_generation.md §D
"""

import logging

from agent.generation.mapgen.sample_selector.filter import load_metadata
from agent.generation.mapgen.sample_selector.selector import select_maps
from agent.generation.models import ExitSpec, GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def map_designer(state: GenerationState) -> dict:
    """D 노드: GameSpec → 샘플 맵 기반 MapSpec 목록 선택."""
    gen_id = state["generation_id"]
    spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    user_input = state["user_input"]

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "map_design",
            "progress": 49,
            "message": "최적의 샘플 맵 검색 중...",
        },
    )

    # 1. 샘플 맵 선택 (사용자 입력 쿼리 활용)
    n_maps = len(spec.maps) if spec.maps else 3
    result = await select_maps(user_input, n_maps=n_maps)
    chosen_filenames = result["chosen"]
    ranked_candidates = result["candidates"]

    # 2. 선택된 맵의 메타데이터 로드
    all_metadata = load_metadata()
    metadata_map = {m["file_name"]: m for m in all_metadata}

    map_specs: list[MapSpec] = []
    for i, filename in enumerate(chosen_filenames, start=1):
        meta = metadata_map.get(filename)
        if not meta:
            continue

        # 3. MapSpec 객체로 변환
        # ID Table에 맵 이름 등록
        map_name = meta["display_name"]
        id_table.maps[map_name] = i

        # 출구 정보 변환
        exits = []
        for ex in meta.get("exits", []):
            exits.append(
                ExitSpec(
                    direction=ex["direction"],
                    to_map_id=ex["leads_to_id"],  # 원본 ID (integrator에서 번역됨)
                    label=ex["leads_to_name"],
                )
            )

        ms = MapSpec(
            map_id=i,
            name=map_name,
            map_type="town" if "마을" in meta["tags"] else "dungeon",  # 단순 분류
            width=meta["width"],
            height=meta["height"],
            tileset_id=meta["tileset_id"],
            bgm="Theme1",  # 기본값
            atmosphere=meta["description"],
            landmarks=[],  # 샘플 맵은 이미 지형에 랜드마크가 포함됨
            exits=exits,
            spawn_point=(meta["width"] // 2, meta["height"] // 2),
            original_file_name=filename,  # 이 필드가 중요!
        )
        map_specs.append(ms)

    logger.info("map_designer 완료: %d개 샘플 맵 선택됨", len(map_specs))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "map_design",
            "summary": f"{len(map_specs)}개 샘플 맵 선택 완료 ({', '.join(m.name for m in map_specs)})",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("map_design")
    return {
        "map_specs": map_specs,
        "ranked_map_candidates": ranked_candidates,
        "completed_phases": completed,
    }
