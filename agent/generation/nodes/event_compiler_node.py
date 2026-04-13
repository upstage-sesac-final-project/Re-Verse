"""G 노드 — event_compiler_node: DSL → RPG Maker MZ 커맨드 (직렬).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.G
직렬 처리 이유: SwitchTable 불변 패턴 — 병렬화 시 스위치 ID 할당 경쟁 조건 발생.
"""

import logging

from agent.generation.compilers.dsl_models import DslEvent
from agent.generation.compilers.event_compiler import CompileError, EventCompiler
from agent.generation.models import MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def event_compiler_node(state: GenerationState) -> dict:
    """G 노드: 맵별 DSL → RPG Maker MZ 이벤트 JSON (직렬)."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    event_dsl: dict[int, list] = state.get("event_dsl") or {}
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]
    map_tiles: dict[int, list[int]] = state.get("map_tiles") or {}

    # 맵별 도달 가능 좌표 집합을 미리 구성 (중복 해결 시 안전한 위치 탐색에 사용)
    from agent.generation.mapgen.tile_checker import get_reachable_coords
    from agent.generation.nodes.integrator import load_base_tilesets

    tilesets = load_base_tilesets()
    reachable_by_map: dict[int, set[tuple[int, int]]] = {}
    for spec in map_specs:
        tile_data = map_tiles.get(spec.map_id)
        if tile_data and tilesets:
            reachable = get_reachable_coords(
                tile_data,
                spec.spawn_point[0],
                spec.spawn_point[1],
                spec.width,
                spec.height,
                spec.tileset_id,
                tilesets,
                avoid_damage=True,
            )
            reachable_by_map[spec.map_id] = set(reachable)

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "event_compile",
            "progress": 82,
            "message": "이벤트 컴파일 중...",
        },
    )

    compiler = EventCompiler(id_table=id_table, switch_table=switch_table)
    compiled_events: dict[int, list[dict]] = {}

    # 직렬 처리 — SwitchTable 불변 패턴 때문에 병렬 불가
    for spec in map_specs:
        map_id = spec.map_id
        dsl_list: list[DslEvent] = event_dsl.get(map_id, [])
        compiled: list[dict] = []
        event_index = 1  # index 0 = null (RPG Maker MZ 규칙)

        reachable_set = reachable_by_map.get(map_id, set())
        used_positions: set[tuple[int, int]] = set()
        for dsl_event in dsl_list:
            try:
                event_dict = compiler.compile(dsl_event)
                # 좌표 중복 방지: 같은 위치에 다른 이벤트가 있으면 도달 가능한 빈 좌표로 이동
                x, y = event_dict.get("x", 0), event_dict.get("y", 0)
                if (x, y) in used_positions:
                    orig_x, orig_y = x, y
                    # 도달 가능 집합에서 미사용 좌표 중 가장 가까운 것 선택
                    candidates = reachable_set - used_positions
                    if candidates:
                        x, y = min(
                            candidates, key=lambda c: abs(c[0] - orig_x) + abs(c[1] - orig_y)
                        )
                    else:
                        # 도달 가능 집합이 없으면 맵 범위 안에서만 x를 증가
                        while (x, y) in used_positions and x < spec.width - 1:
                            x += 1
                    logger.warning(
                        "Map%d 이벤트 '%s' 좌표 중복 (%d,%d) → (%d,%d)으로 이동",
                        map_id,
                        event_dict.get("name", "?"),
                        orig_x,
                        orig_y,
                        x,
                        y,
                    )
                    event_dict["x"] = x
                    event_dict["y"] = y
                used_positions.add((x, y))
                event_dict["id"] = event_index
                event_index += 1
                compiled.append(event_dict)
            except CompileError as e:
                logger.warning(
                    "Map%d 이벤트 '%s' 컴파일 실패: %s → 건너뜀",
                    map_id,
                    getattr(dsl_event, "name", "?"),
                    e,
                )

        compiled_events[map_id] = compiled
        logger.debug("Map%d: %d개 이벤트 컴파일 완료", map_id, len(compiled))

    # 컴파일러가 동적 할당한 스위치 포함된 최신 SwitchTable
    final_switch_table = compiler.final_switch_table
    logger.info(
        "event_compiler_node 완료: %d개 맵, 스위치 %d개",
        len(compiled_events),
        len(final_switch_table.switches),
    )

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "event_compile",
            "summary": f"{len(compiled_events)}개 맵 이벤트 컴파일 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("event_compile")
    return {
        "compiled_events": compiled_events,
        "switch_table": final_switch_table,
        "completed_phases": completed,
    }
