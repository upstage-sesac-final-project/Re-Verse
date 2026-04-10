"""I 노드 — generation_validator: RPG Maker MZ 프로젝트 검증.

11개 검증 함수 (error: 재시도 대상, warning: 통과 후 메시지 포함).
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.I
canonical: docs/The_world/risks_and_mitigations.md
canonical: docs/The_world/additional_risks.md
canonical: docs/The_world/game_ending_design.md §check_ending_reachable
"""

import logging
from collections import deque

from agent.generation.balance import check_balance as simulate_check_balance
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

MAX_RETRY = 2


def _check_null_at_index_0(final_project: dict) -> list[str]:
    """모든 배열 파일의 index-0이 null인지 검증."""
    errors = []
    array_files = [
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "Troops.json",
        "States.json",
        "Animations.json",
        "CommonEvents.json",
    ]
    for fname in array_files:
        data = final_project.get(fname)
        if data is None:
            continue
        if not isinstance(data, list):
            errors.append(f"[R_NULL] {fname}: 배열이 아님")
            continue
        if len(data) == 0 or data[0] is not None:
            errors.append(
                f"[R_NULL] {fname}: index-0이 null이 아님 (값={data[0] if data else 'empty'})"
            )
    return errors


def _check_id_references(final_project: dict, id_table: IdTable) -> list[str]:
    """Actors.json의 classId가 Classes.json에 존재하는지 검증 (R1)."""
    errors = []
    actors = final_project.get("Actors.json", [])
    classes = final_project.get("Classes.json", [])

    valid_class_ids = {c["id"] for c in classes if c is not None}

    for actor in actors:
        if actor is None:
            continue
        cid = actor.get("classId", 0)
        if cid not in valid_class_ids:
            errors.append(f"[R1] Actors.json: {actor.get('name', '?')} classId={cid} 미존재")

    return errors


def _check_array_lengths(final_project: dict) -> list[str]:
    """Classes.json params[i]가 99개인지 검증."""
    errors = []
    classes = final_project.get("Classes.json", [])
    for cls in classes:
        if cls is None:
            continue
        params = cls.get("params", [])
        if len(params) != 8:
            errors.append(
                f"Classes.json: {cls.get('name', '?')} params 행 수={len(params)} (기대:8)"
            )
            continue
        for i, row in enumerate(params):
            if len(row) != 99:
                errors.append(
                    f"Classes.json: {cls.get('name', '?')} params[{i}] 길이={len(row)} (기대:99)"
                )
    return errors


def _check_start_position(final_project: dict, map_tiles: dict[int, list[int]]) -> list[str]:
    """System.json startMapId/startX/Y가 walkable 위치인지 검증 (R16)."""
    errors = []
    system = final_project.get("System.json", {})
    start_map_id = system.get("startMapId", 1)
    start_x = system.get("startX", 0)
    start_y = system.get("startY", 0)

    tile_data = map_tiles.get(start_map_id)
    if tile_data is None:
        return errors  # 맵 타일 없으면 skip

    map_file = final_project.get(f"Map{start_map_id:03d}.json", {})
    w = map_file.get("width", 30)
    h = map_file.get("height", 30)

    if not (0 <= start_x < w and 0 <= start_y < h):
        errors.append(
            f"[R16] System.json startPos ({start_x},{start_y}) 맵 크기 초과 (width={w}, height={h})"
        )
        return errors

    # layer 5: 0=walkable, 1=impassable
    idx = 5 * w * h + start_y * w + start_x
    if idx < len(tile_data) and tile_data[idx] != 0:
        errors.append(f"[R16] System.json startPos ({start_x},{start_y})이 통행 불가 타일")
    return errors


def _check_troop_positions(final_project: dict) -> list[str]:
    """Troops.json members 좌표가 valid range 내인지 검증 (R17)."""
    errors = []
    troops = final_project.get("Troops.json", [])
    for troop in troops:
        if troop is None:
            continue
        for member in troop.get("members", []):
            x, y = member.get("x", 0), member.get("y", 0)
            if not (0 <= x <= 816 and 0 <= y <= 816):
                errors.append(
                    f"[R17] Troops '{troop.get('name', '?')}' member 좌표 ({x},{y}) 범위 초과"
                )
    return errors


def _check_map_id_consistency(final_project: dict) -> list[str]:
    """MapInfos.json 항목과 Map*.json 파일명 일치 여부 검증 (R18)."""
    errors = []
    map_infos = final_project.get("MapInfos.json")
    # 배열 형식: [null, {id:1,...}, ...]
    if not isinstance(map_infos, list):
        return errors

    map_file_ids = {
        int(fname[3:6])
        for fname in final_project
        if fname.startswith("Map")
        and fname.endswith(".json")
        and fname != "MapInfos.json"
        and fname[3:6].isdigit()
    }
    # Map*.json 파일이 하나도 없으면 assets-only 단계 → R18 검증 skip
    if not map_file_ids:
        return errors

    info_ids = {entry["id"] for entry in map_infos if isinstance(entry, dict) and "id" in entry}

    for mid in info_ids - map_file_ids:
        errors.append(f"[R18] MapInfos.json에 Map{mid:03d}.json 파일 없음")
    for mid in map_file_ids - info_ids:
        errors.append(f"[R18] Map{mid:03d}.json이 MapInfos.json에 없음")

    return errors


def _check_resource_filenames(final_project: dict) -> list[str]:
    """Actors.json/Enemies.json 리소스 파일명이 공백 없는지 검증 (R19)."""
    errors = []
    actors = final_project.get("Actors.json", [])
    for actor in actors:
        if actor is None:
            continue
        for field in ("characterName", "faceName", "battlerName"):
            val = actor.get(field, "")
            if val and (" " in val or "\t" in val):
                errors.append(f"[R19] Actors '{actor.get('name', '?')}' {field}='{val}' 공백 포함")
    return errors


_VALID_CHARACTER_NAMES: frozenset[str] = frozenset(
    {
        # 일반 캐릭터
        "Actor1",
        "Actor2",
        "Actor3",
        "People1",
        "People2",
        "People3",
        "People4",
        "Evil",
        "Monster",
        "Nature",
        "Vehicle",
        "Damage1",
        "Damage2",
        "Damage3",
        # SF 캐릭터
        "SF_Actor1",
        "SF_Actor2",
        "SF_Actor3",
        "SF_People1",
        "SF_People2",
        "SF_People3",
        "SF_Monster",
        "SF_Vehicle",
        "SF_Damage1",
        "SF_Damage2",
        # 오브젝트 (! 접두사)
        "!Chest",
        "!Crystal",
        "!Door1",
        "!Door2",
        "!Flame",
        "!Other1",
        "!Other2",
        "!Switch1",
        "!Switch2",
        "!Weapon",
        "!SF_Chest",
        "!SF_Door1",
        "!SF_Door2",
        "!SF_Switch1",
        # 빅 몬스터 ($ 접두사)
        "$BigMonster1",
        "$BigMonster2",
        # 게이트
        "!$Gate1",
        "!$Gate2",
        "!$SF_Gate1",
        "!$SF_Gate2",
        "!$SF_Gate3",
    }
)


def _check_event_character_names(compiled_events: dict[int, list[dict]]) -> list[str]:
    """이벤트 페이지의 characterName이 유효한 스프라이트 파일명인지 검증 (R24, 경고)."""
    warnings = []
    for map_id, events in compiled_events.items():
        for event in events:
            if event is None:
                continue
            for page in event.get("pages", []):
                name = page.get("image", {}).get("characterName", "")
                if name and name not in _VALID_CHARACTER_NAMES:
                    warnings.append(
                        f"[R24] Map{map_id} 이벤트 '{event.get('name', '?')}': "
                        f"characterName='{name}' 유효하지 않은 스프라이트"
                    )
    return warnings


def _check_ending_reachable(
    map_specs: list[MapSpec],
    compiled_events: dict[int, list[dict]],
    id_table: IdTable,
    switch_table: SwitchTable,
) -> list[str]:
    """보스 맵에 도달 가능한 엔딩 이벤트(code 353/354) 존재 여부 검증 (R23)."""
    errors = []
    boss_maps = [m for m in map_specs if m.map_type == "boss"]
    if not boss_maps:
        errors.append("[R23] 보스 맵 없음 — 게임 엔딩 불가")
        return errors

    for boss_map in boss_maps:
        mid = id_table.get_id("maps", boss_map.name)
        if mid is None:
            continue
        events = compiled_events.get(mid, [])
        has_ending = any(
            any(cmd.get("code") in (353, 354) for cmd in page.get("list", []))
            for event in events
            for page in event.get("pages", [])
        )
        if not has_ending:
            errors.append(f"[R23] 보스 맵 '{boss_map.name}'에 엔딩 이벤트(code 353/354) 없음")

    boss_switches = [n for n in switch_table.switches if "_defeated" in n]
    if not boss_switches:
        errors.append("[R23] 보스 처치 스위치(_defeated)가 SwitchTable에 없음")

    return errors


# ── 맵 도달 가능성 검증 + auto_repair ────────────────────────────────────────


def _extract_transfer_graph(
    compiled_events: dict[int, list[dict]],
) -> dict[int, set[int]]:
    """compiled_events에서 TransferEvent(code 201) 기반 이동 그래프 추출.

    Returns:
        {from_map_id: {to_map_id, ...}} 형태의 인접 리스트
    """
    graph: dict[int, set[int]] = {mid: set() for mid in compiled_events}
    for from_map_id, events in compiled_events.items():
        for event in events:
            if event is None:
                continue
            for page in event.get("pages", []):
                for cmd in page.get("list", []):
                    if cmd.get("code") == 201:
                        params = cmd.get("parameters", [])
                        # parameters: [0, to_map_id, to_x, to_y, direction, 0]
                        if len(params) >= 2 and isinstance(params[1], int) and params[1] > 0:
                            graph[from_map_id].add(params[1])
    return graph


def _check_map_reachability(
    compiled_events: dict[int, list[dict]],
    map_specs: list[MapSpec],
    id_table: IdTable,
) -> list[int]:
    """컴파일된 TransferEvent 기반 BFS로 고립된 맵 ID 목록 반환 (R25).

    시작점: town 맵 우선, 없으면 첫 번째 맵.
    """
    if not compiled_events or not map_specs:
        return []

    # 시작 맵 결정
    town_specs = [s for s in map_specs if s.map_type == "town"]
    start_spec = town_specs[0] if town_specs else map_specs[0]
    start_map_id = id_table.get_id("maps", start_spec.name)
    if start_map_id is None:
        return []

    graph = _extract_transfer_graph(compiled_events)
    all_map_ids = set(compiled_events.keys())

    visited: set[int] = {start_map_id}
    queue: deque[int] = deque([start_map_id])
    while queue:
        cur = queue.popleft()
        for nxt in graph.get(cur, set()):
            if nxt in all_map_ids and nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)

    isolated = sorted(all_map_ids - visited)
    if isolated:
        logger.warning("_check_map_reachability: 고립된 맵 ID %s", isolated)
    return isolated


def _make_warp_event(
    event_id: int,
    name: str,
    x: int,
    y: int,
    to_map_id: int,
    to_x: int,
    to_y: int,
) -> dict:
    """워프 전용 RPG Maker MZ 이벤트 dict 생성 (NPC/스토리 없음)."""
    return {
        "id": event_id,
        "name": name,
        "note": "",
        "pages": [
            {
                "conditions": {
                    "actorId": 1,
                    "actorValid": False,
                    "itemId": 1,
                    "itemValid": False,
                    "selfSwitchCh": "A",
                    "selfSwitchValid": False,
                    "switch1Id": 1,
                    "switch1Valid": False,
                    "switch2Id": 1,
                    "switch2Valid": False,
                    "variableId": 1,
                    "variableValid": False,
                    "variableValue": 0,
                },
                "directionFix": True,
                "image": {
                    "characterIndex": 0,
                    "characterName": "!Crystal",
                    "direction": 2,
                    "pattern": 0,
                    "tileId": 0,
                },
                "list": [
                    {"code": 201, "indent": 0, "parameters": [0, to_map_id, to_x, to_y, 0, 0]},
                    {"code": 0, "indent": 0, "parameters": []},
                ],
                "moveFrequency": 3,
                "moveRoute": {
                    "list": [{"code": 0, "parameters": []}],
                    "repeat": True,
                    "skippable": False,
                    "wait": False,
                },
                "moveSpeed": 3,
                "moveType": 0,
                "priorityType": 1,
                "stepAnime": False,
                "through": False,
                "trigger": 1,  # player_touch
                "walkAnime": True,
            }
        ],
        "x": x,
        "y": y,
    }


def _auto_repair_isolated_maps(
    isolated_map_ids: list[int],
    compiled_events: dict[int, list[dict]],
    final_project: dict,
    map_specs: list[MapSpec],
    connection_info: dict[int, MapConnectionInfo],
    id_table: IdTable,
) -> tuple[dict[int, list[dict]], dict]:
    """고립된 맵의 exit_tiles 기반으로 워프 이벤트만 양방향 삽입.

    Returns:
        수정된 (compiled_events, final_project) 튜플
    """
    # id → name 역매핑
    id_to_map_name: dict[int, str] = {v: k for k, v in id_table.maps.items()}
    # map_id → MapSpec
    spec_by_id: dict[int, MapSpec] = {s.map_id: s for s in map_specs}

    for iso_map_id in isolated_map_ids:
        iso_spec = spec_by_id.get(iso_map_id)
        if not iso_spec:
            continue

        ci = connection_info.get(iso_map_id)
        if not ci or not ci.exit_tiles:
            logger.warning("auto_repair: map_id=%d exit_tiles 없음 → 스킵", iso_map_id)
            continue

        for exit_tile in ci.exit_tiles:
            to_map_id: int = exit_tile.get("to_map_id", 0)
            ex: int = exit_tile.get("x", iso_spec.width // 2)
            ey: int = exit_tile.get("y", iso_spec.height // 2)
            to_map_name = id_to_map_name.get(to_map_id)
            if not to_map_name:
                continue

            to_spec = spec_by_id.get(to_map_id)
            to_x = to_spec.spawn_point[0] if to_spec else 1
            to_y = to_spec.spawn_point[1] if to_spec else 1

            # ── 고립 맵 → 목적지 워프 삽입 ───────────────────────────────
            iso_events = compiled_events.get(iso_map_id, [])
            new_id = max((e.get("id", 0) for e in iso_events), default=0) + 1
            warp = _make_warp_event(
                event_id=new_id,
                name=f"{to_map_name}_워프",
                x=ex,
                y=ey,
                to_map_id=to_map_id,
                to_x=to_x,
                to_y=to_y,
            )
            iso_events.append(warp)
            compiled_events[iso_map_id] = iso_events

            map_key = f"Map{iso_map_id:03d}.json"
            if map_key in final_project:
                final_project[map_key]["events"].append(warp)

            logger.info(
                "auto_repair: Map%d → '%s' 워프 이벤트 삽입 (%d,%d)",
                iso_map_id,
                to_map_name,
                ex,
                ey,
            )

            # ── 목적지 → 고립 맵 역방향 워프도 누락 시 삽입 ─────────────
            dest_events = compiled_events.get(to_map_id, [])
            has_return = any(
                any(
                    cmd.get("code") == 201 and cmd.get("parameters", [None, None])[1] == iso_map_id
                    for cmd in page.get("list", [])
                )
                for ev in dest_events
                for page in ev.get("pages", [])
            )
            if not has_return:
                dest_ci = connection_info.get(to_map_id)
                ret_tile = next(
                    (
                        t
                        for t in (dest_ci.exit_tiles if dest_ci else [])
                        if t.get("to_map_id") == iso_map_id
                    ),
                    None,
                )
                rx = ret_tile["x"] if ret_tile else (to_spec.width // 2 if to_spec else 1)
                ry = ret_tile["y"] if ret_tile else (to_spec.height // 2 if to_spec else 1)

                ret_id = max((e.get("id", 0) for e in dest_events), default=0) + 1
                iso_name = id_to_map_name.get(iso_map_id, f"Map{iso_map_id}")
                ret_warp = _make_warp_event(
                    event_id=ret_id,
                    name=f"{iso_name}_워프",
                    x=rx,
                    y=ry,
                    to_map_id=iso_map_id,
                    to_x=ex,
                    to_y=ey,
                )
                dest_events.append(ret_warp)
                compiled_events[to_map_id] = dest_events

                dest_key = f"Map{to_map_id:03d}.json"
                if dest_key in final_project:
                    final_project[dest_key]["events"].append(ret_warp)

                logger.info(
                    "auto_repair: Map%d ← '%s' 역방향 워프 이벤트 삽입 (%d,%d)",
                    iso_map_id,
                    to_map_name,
                    rx,
                    ry,
                )

    return compiled_events, final_project


# ── 경고 전용 검증 ────────────────────────────────────────────────────────────


def _check_balance(final_project: dict) -> list[str]:
    """전투 시뮬레이션 기반 밸런스 검증 (경고)."""
    return simulate_check_balance(final_project)


def _check_event_coordinate_conflicts(compiled_events: dict[int, list[dict]]) -> list[str]:
    """같은 맵에 동일 좌표에 이벤트 2개 이상 배치 여부 검증 (R22, 경고)."""
    warnings = []
    for map_id, events in compiled_events.items():
        seen: set[tuple[int, int]] = set()
        for event in events:
            if event is None:
                continue
            pos = (event.get("x", 0), event.get("y", 0))
            if pos in seen:
                warnings.append(f"[R22] Map{map_id}: 좌표 {pos}에 이벤트 중복 배치")
            seen.add(pos)
    return warnings


def _check_switch_semantic_conflicts(switch_table: SwitchTable) -> list[str]:
    """같은 의미인데 다른 이름으로 중복 스위치 등록 여부 검증 (R20, 경고)."""
    warnings = []
    switch_names = list(switch_table.switches.keys())
    # 이름이 거의 같은 스위치 탐지 (예: boss_defeated vs boss_defeat)
    for i, name_a in enumerate(switch_names):
        for name_b in switch_names[i + 1 :]:
            # 편집 거리 비슷 → 단순 prefix 체크
            if (
                name_a != name_b
                and len(name_a) > 3
                and len(name_b) > 3
                and (name_a.startswith(name_b[:5]) or name_b.startswith(name_a[:5]))
            ):
                warnings.append(f"[R20] 유사한 스위치 이름: '{name_a}' vs '{name_b}' — 중복 가능성")
    return warnings


async def generation_validator(state: GenerationState) -> dict:
    """I 노드: 생성된 프로젝트 파일 검증."""
    gen_id = state["generation_id"]
    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "validation",
            "progress": 94,
            "message": "검증 중...",
        },
    )

    final_project: dict = state.get("final_project", {})
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    map_tiles: dict[int, list[int]] = state.get("map_tiles") or {}
    compiled_events: dict[int, list[dict]] = state.get("compiled_events") or {}
    connection_info: dict[int, MapConnectionInfo] = state.get("connection_info") or {}
    retry_count: int = state.get("retry_count", 0)

    errors: list[str] = []
    warnings: list[str] = []

    # ── error 검증 (재시도 대상) ─────────────────────────────────────────────
    errors.extend(_check_null_at_index_0(final_project))
    errors.extend(_check_id_references(final_project, id_table))
    errors.extend(_check_array_lengths(final_project))
    errors.extend(_check_start_position(final_project, map_tiles))
    errors.extend(_check_troop_positions(final_project))
    errors.extend(_check_map_id_consistency(final_project))
    errors.extend(_check_resource_filenames(final_project))
    if map_specs and compiled_events:
        errors.extend(_check_ending_reachable(map_specs, compiled_events, id_table, switch_table))

    # ── 맵 도달 가능성 검증 (R25) ────────────────────────────────────────────
    # game_designer 단에서 이미 고립 맵이 발생한 경우 event_planner 재시도로 해결 불가
    # → 즉시 auto_repair로 워프 이벤트 삽입 (retry 루프 제거로 실행 시간 단축)
    extra_state: dict = {}
    if map_specs and compiled_events:
        isolated = _check_map_reachability(compiled_events, map_specs, id_table)
        if isolated:
            iso_names = [
                next(
                    (s.name for s in map_specs if id_table.get_id("maps", s.name) == mid),
                    f"Map{mid}",
                )
                for mid in isolated
            ]
            logger.warning(
                "generation_validator: 고립 맵 %s → auto_repair 실행 (retry=%d)",
                iso_names,
                retry_count,
            )
            compiled_events, final_project = _auto_repair_isolated_maps(
                isolated_map_ids=isolated,
                compiled_events=compiled_events,
                final_project=final_project,
                map_specs=map_specs,
                connection_info=connection_info,
                id_table=id_table,
            )
            for name in iso_names:
                warnings.append(f"[R25] 고립된 맵 '{name}' — 워프 이벤트 자동 삽입됨")
            extra_state["compiled_events"] = compiled_events
            extra_state["final_project"] = final_project

    # ── warning 검증 (통과, 메시지만) ────────────────────────────────────────
    warnings.extend(_check_balance(final_project))
    if compiled_events:
        warnings.extend(_check_event_coordinate_conflicts(compiled_events))
        warnings.extend(_check_event_character_names(compiled_events))
    if switch_table:
        warnings.extend(_check_switch_semantic_conflicts(switch_table))

    validation_passed = len(errors) == 0

    if errors:
        logger.warning("generation_validator: %d 오류 발견 (retry=%d)", len(errors), retry_count)
        for err in errors:
            logger.warning("  %s", err)
    else:
        logger.info("generation_validator: 검증 통과")

    if warnings:
        await publish_progress(
            gen_id,
            {
                "type": "warning",
                "category": "validation",
                "warnings": warnings,
            },
        )

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "validation",
            "summary": "검증 통과" if validation_passed else f"검증 완료 ({len(errors)}개 오류)",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("validation")
    return {
        "validation_passed": validation_passed,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "retry_count": retry_count + (0 if validation_passed else 1),
        "completed_phases": completed,
        **extra_state,
    }


def route_after_validation(state: GenerationState) -> str:
    """validator 이후 라우팅 결정."""
    errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)

    if not errors:
        return "respond"
    if retry_count >= MAX_RETRY:
        return "respond"

    # 오류 태그별 재시도 라우트
    tags = {err.split("]")[0].lstrip("[") for err in errors if "]" in err}
    if "R1" in tags or "R_NULL" in tags:
        return "retry_assets"
    if "R23" in tags or "R22" in tags:
        return "retry_events"

    return "respond"
