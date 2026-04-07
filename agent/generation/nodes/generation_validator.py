"""I 노드 — generation_validator: RPG Maker MZ 프로젝트 검증.

11개 검증 함수 (error: 재시도 대상, warning: 통과 후 메시지 포함).
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.I
canonical: docs/The_world/risks_and_mitigations.md
canonical: docs/The_world/additional_risks.md
canonical: docs/The_world/game_ending_design.md §check_ending_reachable
"""

import logging

from agent.generation.balance import check_balance as simulate_check_balance
from agent.generation.models import MapSpec
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
    """I 노드: 생성된 프로젝트 파일 검증 (11개 함수)."""
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
