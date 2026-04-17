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


def _is_blocking_page(event_dict: dict) -> bool:
    """이벤트가 통로를 차단하는 페이지를 포함하는지 확인.

    code 201(워프) 또는 through=False+priorityType=1(물리적 차단) 페이지가 있으면 True.
    """
    for page in event_dict.get("pages", []):
        if any(cmd.get("code") == 201 for cmd in page.get("list", [])):
            return True
        if not page.get("through", False) and page.get("priorityType", 1) == 1:
            return True
    return False


async def event_compiler_node(state: GenerationState) -> dict:
    """G 노드: 맵별 DSL → RPG Maker MZ 이벤트 JSON (직렬)."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    event_dsl: dict[int, list] = state.get("event_dsl") or {}
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]
    map_tiles: dict[int, list[int]] = state.get("map_tiles") or {}
    connection_info = state.get("connection_info") or {}

    # 맵별 도달 가능 좌표 집합을 미리 구성 (중복 해결 시 안전한 위치 탐색에 사용)
    from agent.generation.mapgen.tile_checker import get_bottleneck_coords, get_reachable_coords
    from agent.generation.nodes.integrator import load_base_tilesets

    tilesets = load_base_tilesets()
    if not tilesets:
        logger.warning("event_compiler_node: tilesets 로드 실패 — 병목 체크 비활성화")

    reachable_by_map: dict[int, set[tuple[int, int]]] = {}
    bottlenecks_by_map: dict[int, set[tuple[int, int]]] = {}
    non_bottleneck_by_map: dict[int, set[tuple[int, int]]] = {}

    for spec in map_specs:
        tile_data = map_tiles.get(spec.map_id)
        if not tile_data:
            logger.warning("Map%d: tile_data 없음 — 병목 체크 비활성화", spec.map_id)
            continue
        if not tilesets:
            continue

        # 1. 안전하게 도달 가능한(is_walkable) 좌표들 (이벤트 배치 가능 구역)
        reachable = set(
            get_reachable_coords(
                tile_data,
                spec.spawn_point[0],
                spec.spawn_point[1],
                spec.width,
                spec.height,
                spec.tileset_id,
                tilesets,
                avoid_damage=True,
            )
        )
        reachable_by_map[spec.map_id] = reachable

        # 2. 완화된 기준(is_potential_path)을 사용한 병목 지점 탐지
        bottlenecks = get_bottleneck_coords(
            tile_data,
            spec.width,
            spec.height,
            spec.tileset_id,
            tilesets,
            spec.spawn_point[0],
            spec.spawn_point[1],
        )
        bottlenecks_by_map[spec.map_id] = bottlenecks
        non_bottleneck_by_map[spec.map_id] = reachable - bottlenecks

        logger.debug(
            "Map%d: reachable=%d, bottlenecks=%d, non_bottleneck=%d",
            spec.map_id,
            len(reachable),
            len(bottlenecks),
            len(reachable - bottlenecks),
        )

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
        bottleneck_set = bottlenecks_by_map.get(map_id, set())
        non_bottleneck_set = non_bottleneck_by_map.get(map_id, set())
        used_positions: set[tuple[int, int]] = set()

        # 출구 좌표 수집 (실시간 경로 차단 검증용)
        exit_coords: set[tuple[int, int]] = set()
        conn = connection_info.get(map_id)
        if conn and conn.exit_tiles:
            for et in conn.exit_tiles:
                exit_coords.add((et["x"], et["y"]))

        if not reachable_set:
            logger.warning("Map%d: reachable_set 비어있음 — 병목 체크 비활성화", map_id)

        # 플레이어 시작 지점 및 주변 8칸 예약 (끼임 및 즉시 트리거 방지)
        if conn and conn.entry_tiles:
            for entry in conn.entry_tiles:
                ex, ey = entry["x"], entry["y"]
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        rx, ry = ex + dx, ey + dy
                        if 0 <= rx < spec.width and 0 <= ry < spec.height:
                            used_positions.add((rx, ry))
        else:
            sx, sy = spec.spawn_point
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    rx, ry = sx + dx, sy + dy
                    if 0 <= rx < spec.width and 0 <= ry < spec.height:
                        used_positions.add((rx, ry))

        for dsl_event in dsl_list:
            try:
                event_dict = compiler.compile(dsl_event)
                x, y = event_dict.get("x", 0), event_dict.get("y", 0)
                orig_x, orig_y = x, y
                reason: str | None = None

                # ① 좌표 중복
                if (x, y) in used_positions:
                    reason = "좌표 중복"
                # ② 경로 차단 검증 (실시간)
                elif _is_blocking_page(event_dict):
                    from agent.generation.mapgen.tile_checker import are_exits_reachable

                    # 현재 위치가 병목 지점이거나, 배치 시 출구가 막히는 경우 재배치
                    if (x, y) in bottleneck_set or not are_exits_reachable(
                        map_tiles.get(map_id, []),
                        spec.spawn_point[0],
                        spec.spawn_point[1],
                        spec.width,
                        spec.height,
                        spec.tileset_id,
                        tilesets,
                        exit_coords,
                        used_positions | {(x, y)},
                    ):
                        reason = "경로 차단(병목 지점 또는 출구 봉쇄)"

                if reason:
                    # 비-병목 walkable 미사용 좌표 우선
                    preferred = (non_bottleneck_set) - used_positions
                    fallback = reachable_set - used_positions
                    candidates = preferred or fallback
                    if candidates:
                        from agent.generation.mapgen.tile_checker import are_exits_reachable

                        sorted_candidates = sorted(
                            candidates, key=lambda c: abs(c[0] - orig_x) + abs(c[1] - orig_y)
                        )

                        found_alt = False
                        is_blocking = _is_blocking_page(event_dict)
                        # 차단성 이벤트인 경우 출구가 막히지 않는지 재검증하며 이동
                        if is_blocking:
                            for cx, cy in sorted_candidates[:20]:
                                if cx in bottleneck_set:
                                    continue
                                if are_exits_reachable(
                                    map_tiles.get(map_id, []),
                                    spec.spawn_point[0],
                                    spec.spawn_point[1],
                                    spec.width,
                                    spec.height,
                                    spec.tileset_id,
                                    tilesets,
                                    exit_coords,
                                    used_positions | {(cx, cy)},
                                ):
                                    x, y = cx, cy
                                    found_alt = True
                                    break

                        if not found_alt:
                            x, y = sorted_candidates[0]
                    else:
                        while (x, y) in used_positions and x < spec.width - 1:
                            x += 1
                    logger.warning(
                        "Map%d 이벤트 '%s' %s (%d,%d) → (%d,%d)으로 이동",
                        map_id,
                        event_dict.get("name", "?"),
                        reason,
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
