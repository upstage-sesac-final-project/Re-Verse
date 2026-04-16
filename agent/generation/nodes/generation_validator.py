"""I 노드 — generation_validator: RPG Maker MZ 프로젝트 검증.

검증 함수 구성:
  error(11): R_NULL, R1, array_lengths, R16, R17, R18, R19, R23, R26, R27, R28
  warning(4): balance, R20, R22, R24
  직접 호출(1): R25 (map reachability)
auto-repair 우선 적용 후 남은 오류만 retry 라우팅.
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.I
canonical: docs/The_world/risks_and_mitigations.md
canonical: docs/The_world/additional_risks.md
canonical: docs/The_world/game_ending_design.md §check_ending_reachable
"""

import logging
import os
import struct
from collections import deque

from agent.generation.balance import check_balance as simulate_check_balance
from agent.generation.models import GameSpec, MapConnectionInfo, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

MAX_RETRY = 2

# 이 오류들이 MAX_RETRY 도달 시에도 남아 있으면 게임 진행 불가 → 강제 실패
_CRITICAL_TAGS: frozenset[str] = frozenset({"R1", "R_NULL", "R16", "R18"})

# ── 전투 화면 크기 / 배틀러 스프라이트 높이 테이블 (R17 검증·교정 기준) ────
_BATTLE_W: int = 816  # 전투 배경 가로 (px)
_BATTLE_H: int = 624  # 전투 배경 세로 (px)
_DEFAULT_SPRITE_HALF_H: int = 96  # battlerName 미매핑 시 기본값 (보수적으로 큰 쪽)


def _build_battler_height_table() -> dict[str, int]:
    """base_game/img/enemies/*.png 헤더만 읽어 battlerName → 스프라이트 높이(px) 매핑 구축.

    PNG IHDR 청크는 파일 선두 24바이트에 위치하므로 I/O 비용이 극히 낮다.
    모듈 임포트 시 1회 실행 후 _BATTLER_HEIGHTS 상수에 캐싱된다.
    EC2 로컬 storage/games/base_game 경로 기준; 경로 없으면 빈 dict 반환.
    """
    table: dict[str, int] = {}
    base = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "storage",
            "games",
            "base_game",
            "img",
            "enemies",
        )
    )
    if not os.path.isdir(base):
        logger.debug("_build_battler_height_table: 경로 없음 → 기본값 사용 (%s)", base)
        return table
    for fname in os.listdir(base):
        if not fname.endswith(".png"):
            continue
        try:
            with open(os.path.join(base, fname), "rb") as f:
                if f.read(8) != b"\x89PNG\r\n\x1a\n":
                    continue
                f.read(8)  # IHDR length + type
                f.read(4)  # width
                h = struct.unpack(">I", f.read(4))[0]
            table[fname[:-4]] = h
        except OSError:
            pass
    logger.debug("_build_battler_height_table: %d개 배틀러 높이 로드 완료", len(table))
    return table


# 모듈 로드 시 1회 구축 (EC2 로컬 디스크 I/O, ~수 ms)
_BATTLER_HEIGHTS: dict[str, int] = _build_battler_height_table()

# ── Array 파일 목록 (R_NULL 검증 대상) ───────────────────────────────────────
_ARRAY_FILES = [
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


def _check_null_at_index_0(final_project: dict) -> list[str]:
    """모든 배열 파일의 index-0이 null인지 검증."""
    errors = []
    for fname in _ARRAY_FILES:
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


def _auto_repair_start_position(final_project: dict, map_tiles: dict[int, list[int]]) -> dict:
    """R16: startPos가 통행 불가 타일이면 BFS로 가장 가까운 walkable 좌표로 교정 (방어코드).

    tile_generator가 spawn_point를 이미 보정하므로 실제 발생 빈도는 낮다.
    tile_data가 없으면 교정 불가 → 스킵.
    """
    system = final_project.get("System.json")
    if not isinstance(system, dict):
        return final_project

    start_map_id = system.get("startMapId", 1)
    start_x = system.get("startX", 0)
    start_y = system.get("startY", 0)

    tile_data = map_tiles.get(start_map_id)
    if tile_data is None:
        return final_project

    map_file = final_project.get(f"Map{start_map_id:03d}.json", {})
    w = map_file.get("width", 30)
    h = map_file.get("height", 30)

    def _is_walkable(x: int, y: int) -> bool:
        if not (0 <= x < w and 0 <= y < h):
            return False
        idx = 5 * w * h + y * w + x
        return idx < len(tile_data) and tile_data[idx] == 0

    if _is_walkable(start_x, start_y):
        return final_project  # 이미 정상

    # BFS로 가장 가까운 walkable 좌표 탐색
    visited: set[tuple[int, int]] = {(start_x, start_y)}
    queue: deque[tuple[int, int]] = deque([(start_x, start_y)])
    found: tuple[int, int] | None = None
    while queue and found is None:
        cx, cy = queue.popleft()
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in visited:
                continue
            visited.add((nx, ny))
            if _is_walkable(nx, ny):
                found = (nx, ny)
                break
            queue.append((nx, ny))

    if found:
        logger.warning(
            "auto_repair R16: startPos (%d,%d) 통행 불가 → (%d,%d) 교정",
            start_x,
            start_y,
            found[0],
            found[1],
        )
        system["startX"] = found[0]
        system["startY"] = found[1]
    else:
        logger.error("auto_repair R16: Map%d walkable 좌표 없음 → 교정 불가", start_map_id)

    return final_project


def _get_battler_name(final_project: dict, enemy_id: int) -> str:
    """Enemies.json에서 enemyId에 해당하는 battlerName 반환."""
    for enemy in final_project.get("Enemies.json", []):
        if isinstance(enemy, dict) and enemy.get("id") == enemy_id:
            return enemy.get("battlerName", "")
    return ""


def _check_troop_positions(final_project: dict) -> list[str]:
    """Troops.json members 좌표가 전투 화면 범위 내인지, 스프라이트 실제 높이 기준 상단 잘림 없는지 검증 (R17).

    RPG Maker MZ 전투에서 적 스프라이트는 중심점이 (x, y)에 위치하므로
    y < sprite_height / 2 이면 상체가 화면 위로 잘린다.
    _BATTLER_HEIGHTS 테이블에 없는 경우 보수적 기본값(_DEFAULT_SPRITE_HALF_H)을 사용.
    """
    errors = []
    troops = final_project.get("Troops.json", [])
    for troop in troops:
        if troop is None:
            continue
        for member in troop.get("members", []):
            x, y = member.get("x", 0), member.get("y", 0)
            enemy_id = member.get("enemyId", 0)
            battler_name = _get_battler_name(final_project, enemy_id)
            sprite_h = _BATTLER_HEIGHTS.get(battler_name, _DEFAULT_SPRITE_HALF_H * 2)
            half_h = sprite_h // 2

            if not (0 <= x <= _BATTLE_W):
                errors.append(
                    f"[R17] Troops '{troop.get('name', '?')}' member x={x} 범위 초과 (0-{_BATTLE_W})"
                )
            if not (half_h <= y <= _BATTLE_H):
                errors.append(
                    f"[R17] Troops '{troop.get('name', '?')}' member y={y} "
                    f"범위 초과 ({half_h}-{_BATTLE_H}, 스프라이트 높이={sprite_h}px) — 상단 잘림 위험"
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


def _auto_repair_map_id_consistency(final_project: dict) -> dict:
    """R18: MapInfos.json ↔ Map*.json 불일치 → 고아 항목 제거/추가 (방어코드).

    MapInfos에만 있고 Map*.json 없는 항목 → MapInfos에서 제거.
    Map*.json만 있고 MapInfos 없는 항목 → 최소 항목 추가.
    integrator가 같은 map_specs에서 두 파일 모두 생성하므로 실제 발생 빈도는 낮다.
    """
    map_infos = final_project.get("MapInfos.json")
    if not isinstance(map_infos, list):
        return final_project

    map_file_ids: set[int] = {
        int(fname[3:6])
        for fname in final_project
        if fname.startswith("Map")
        and fname.endswith(".json")
        and fname != "MapInfos.json"
        and fname[3:6].isdigit()
    }
    if not map_file_ids:
        return final_project

    info_ids = {entry["id"] for entry in map_infos if isinstance(entry, dict) and "id" in entry}

    # MapInfos에만 있고 Map*.json 없는 항목 제거
    orphan_info = info_ids - map_file_ids
    if orphan_info:
        final_project["MapInfos.json"] = [
            entry
            for entry in map_infos
            if not (isinstance(entry, dict) and entry.get("id") in orphan_info)
        ]
        logger.warning("auto_repair R18: MapInfos 고아 항목 제거 %s", sorted(orphan_info))
        map_infos = final_project["MapInfos.json"]

    # Map*.json만 있고 MapInfos 없는 항목 → 최소 항목 추가
    orphan_files = map_file_ids - info_ids
    if orphan_files:
        for mid in sorted(orphan_files):
            map_json = final_project.get(f"Map{mid:03d}.json", {})
            entry = {
                "id": mid,
                "expanded": False,
                "name": map_json.get("displayName", f"Map{mid:03d}"),
                "order": mid,
                "parentId": 0,
                "scrollX": 0,
                "scrollY": 0,
            }
            map_infos.append(entry)
            logger.warning("auto_repair R18: Map%03d MapInfos 항목 추가", mid)
        final_project["MapInfos.json"] = map_infos

    return final_project


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
    """마지막 맵(보스 구역)에 도달 가능한 엔딩 이벤트(code 353/354) 존재 여부 검증 (R23).

    map_type은 town/dungeon만 사용하므로, map_id가 가장 큰 맵을 보스 구역으로 간주한다.
    """
    errors = []
    if not map_specs:
        errors.append("[R23] 맵이 없음 — 게임 엔딩 불가")
        return errors

    # map_id 최대값 = 마지막 맵 = 보스 구역
    boss_maps = [max(map_specs, key=lambda m: m.map_id)]

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


# ── Auto-Repair: retry 없이 인-플레이스 수정 ─────────────────────────────────


def _auto_repair_resource_filenames(final_project: dict) -> dict:
    """R19: characterName/faceName/battlerName의 공백을 언더스코어로 교정.

    RPG Maker MZ는 파일명 공백을 인식하지 못해 스프라이트 로딩에 실패한다.
    유효 파일명은 전부 언더스코어 형태(SF_Actor1 등)이므로 안전하게 치환 가능.
    """
    for actor in final_project.get("Actors.json", []):
        if actor is None:
            continue
        for field in ("characterName", "faceName", "battlerName"):
            val = actor.get(field, "")
            if val and " " in val:
                fixed = val.replace(" ", "_")
                logger.info("auto_repair R19: %s '%s' → '%s'", field, val, fixed)
                actor[field] = fixed
    return final_project


def _auto_repair_coordinate_conflicts(
    compiled_events: dict[int, list[dict]],
    final_project: dict,
    map_specs: list[MapSpec],
    map_tiles: dict[int, list[int]],
) -> dict[int, list[dict]]:
    """R22: 동일 좌표에 이벤트 중복 배치 → 이동 가능한 인접 빈 좌표로 재배치.

    event_compiler_node의 좌표 보정 이후에 auto_repair_isolated_maps(R25) 등이
    추가한 이벤트가 기존 이벤트와 충돌하는 케이스를 처리한다.
    tile_data가 없으면 단순 오프셋만 적용(이동 가능 여부 불보장).
    """
    # tilesets는 integrator 경유로 가져오기 어려우므로 파일에서 직접 로드
    try:
        from agent.generation.mapgen.tile_checker import get_reachable_coords
        from agent.generation.nodes.integrator import load_base_tilesets

        tilesets = load_base_tilesets()
    except Exception:
        tilesets = None

    spec_by_id: dict[int, MapSpec] = {s.map_id: s for s in map_specs}

    for map_id, events in compiled_events.items():
        seen: dict[tuple[int, int], int] = {}  # 좌표 → 먼저 배치된 이벤트 인덱스
        spec = spec_by_id.get(map_id)
        tile_data = map_tiles.get(map_id)

        # 이동 가능 좌표 집합 (tile_data·tilesets·spec 모두 있어야 계산 가능)
        reachable: set[tuple[int, int]] = set()
        if spec and tile_data and tilesets:
            try:
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
            except Exception:
                pass

        for i, ev in enumerate(events):
            if ev is None:
                continue
            pos: tuple[int, int] = (ev.get("x", 0), ev.get("y", 0))
            if pos not in seen:
                seen[pos] = i
                continue

            # 충돌 발생 — 나중에 추가된 이벤트(i)를 빈 reachable 좌표로 이동
            occupied = {(e.get("x", 0), e.get("y", 0)) for e in events if e}
            new_pos: tuple[int, int] | None = None

            if reachable:
                # reachable 집합에서 현재 위치와 가장 가까운 미사용 좌표 탐색
                candidates = sorted(
                    (c for c in reachable if c not in occupied),
                    key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]),
                )
                if candidates:
                    new_pos = candidates[0]
            else:
                # tile_data 없음 → 단순 오프셋 (x 방향으로 1씩 증가)
                nx, ny = pos[0] + 1, pos[1]
                if spec:
                    while (nx, ny) in occupied and nx < spec.width - 1:
                        nx += 1
                new_pos = (nx, ny) if (nx, ny) not in occupied else None

            if new_pos:
                logger.warning(
                    "auto_repair R22: Map%d 이벤트 '%s' (%d,%d) → (%d,%d) 재배치",
                    map_id,
                    ev.get("name", "?"),
                    pos[0],
                    pos[1],
                    new_pos[0],
                    new_pos[1],
                )
                ev["x"], ev["y"] = new_pos[0], new_pos[1]
                seen[new_pos] = i
                # Map*.json 동기화
                map_key = f"Map{map_id:03d}.json"
                map_json_events = final_project.get(map_key, {}).get("events", [])
                for je in map_json_events:
                    if je and je.get("id") == ev.get("id"):
                        je["x"], je["y"] = new_pos[0], new_pos[1]
                        break
            else:
                logger.warning(
                    "auto_repair R22: Map%d 이벤트 '%s' (%d,%d) 재배치 위치 없음 → 그대로 유지",
                    map_id,
                    ev.get("name", "?"),
                    pos[0],
                    pos[1],
                )

    return compiled_events


def _auto_repair_null_at_index_0(final_project: dict) -> dict:
    """R_NULL: 배열 파일 index-0을 null로 자동 교정.

    LLM 없이 순수 데이터 수정이므로 retry 불필요.
    """
    for fname in _ARRAY_FILES:
        data = final_project.get(fname)
        if not isinstance(data, list):
            continue
        if not data or data[0] is not None:
            if not data:
                final_project[fname] = [None]
            else:
                final_project[fname] = [None] + data
            logger.info("auto_repair R_NULL: %s index-0 → null 교정", fname)
    return final_project


async def _auto_repair_actor_class_ids(
    final_project: dict,
    game_spec: "GameSpec",
    id_table: IdTable,
) -> dict:
    """R1: 유효하지 않은 classId를 가진 Actor → actors만 LLM 재생성.

    전체 asset_generator 재실행 대신 Actors.json만 대상으로 LLM을 호출.
    Classes.json은 그대로 유지하여 다른 에셋에 영향 없음.
    """
    from agent.generation.nodes.asset_generator import generate_actors

    classes_json = final_project.get("Classes.json", [])
    logger.info("auto_repair R1: Actors.json classId 불일치 → actors만 재생성 (LLM)")
    try:
        new_actors = await generate_actors(game_spec, id_table, classes_json)
        final_project["Actors.json"] = new_actors
        logger.info("auto_repair R1: Actors.json 재생성 완료")
    except Exception as e:
        logger.error("auto_repair R1: actors 재생성 실패: %s", e)
    return final_project


def _auto_repair_ending_event(
    compiled_events: dict[int, list[dict]],
    final_project: dict,
    map_specs: list[MapSpec],
    switch_table: SwitchTable,
    id_table: IdTable,
) -> tuple[dict[int, list[dict]], dict]:
    """R23: 보스 맵에 엔딩 이벤트가 없으면 Auto-Run 엔딩 이벤트를 자동 삽입.

    boss_switch(_defeated)가 ON이 되면 자동 실행되는 최소 엔딩 이벤트를 삽입.
    위치는 보스 맵 스폰 근처(충돌 없는 오프셋) — Auto-Run은 위치 무관하게 동작함.
    """
    if not map_specs:
        return compiled_events, final_project

    boss_spec = max(map_specs, key=lambda m: m.map_id)
    boss_map_id = id_table.get_id("maps", boss_spec.name)
    if boss_map_id is None:
        logger.warning("auto_repair R23: 보스 맵 ID를 찾을 수 없음 → 스킵")
        return compiled_events, final_project

    # 보스 처치 스위치 ID 탐색 (_defeated 포함 스위치 중 보스 맵 관련 우선)
    boss_sw_id: int | None = None
    for sw_name, sw_id in switch_table.switches.items():
        if "_defeated" in sw_name:
            if boss_spec.name.lower().split()[0] in sw_name.lower():
                boss_sw_id = sw_id
                break
    if boss_sw_id is None:
        # 보스 맵 이름 매칭 실패 시 첫 번째 _defeated 스위치 사용
        for sw_name, sw_id in switch_table.switches.items():
            if "_defeated" in sw_name:
                boss_sw_id = sw_id
                break
    if boss_sw_id is None:
        logger.warning("auto_repair R23: _defeated 스위치 없음 → 스킵")
        return compiled_events, final_project

    # 이미 사용된 이벤트 좌표 수집
    existing_events = compiled_events.get(boss_map_id, [])
    used_positions = {(e.get("x", 0), e.get("y", 0)) for e in existing_events if e}

    # 스폰 근처에서 빈 위치 탐색 (Auto-Run이므로 위치는 게임 플레이에 영향 없음)
    sx, sy = boss_spec.spawn_point
    target_x, target_y = sx, sy
    for dx, dy in [(2, 0), (-2, 0), (0, 2), (0, -2), (3, 0), (-3, 0)]:
        cx, cy = sx + dx, sy + dy
        if (
            0 <= cx < boss_spec.width
            and 0 <= cy < boss_spec.height
            and (cx, cy) not in used_positions
        ):
            target_x, target_y = cx, cy
            break

    # 엔딩 이벤트 dict 직접 조립
    sw_condition = {
        "actorId": 1,
        "actorValid": False,
        "itemId": 1,
        "itemValid": False,
        "selfSwitchCh": "A",
        "selfSwitchValid": False,
        "switch1Id": boss_sw_id,
        "switch1Valid": True,
        "switch2Id": 1,
        "switch2Valid": False,
        "variableId": 1,
        "variableValid": False,
        "variableValue": 0,
    }
    empty_condition = {
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
    }

    def _make_ending_page(cmds: list[dict], conditions: dict, trigger: int) -> dict:
        return {
            "conditions": conditions,
            "directionFix": True,
            "image": {
                "characterIndex": 0,
                "characterName": "",
                "direction": 2,
                "pattern": 0,
                "tileId": 0,
            },
            "list": cmds,
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
            "through": True,
            "trigger": trigger,
            "walkAnime": True,
        }

    idle_page = _make_ending_page(
        [{"code": 0, "indent": 0, "parameters": []}], empty_condition, trigger=0
    )
    ending_cmds = [
        {"code": 230, "indent": 0, "parameters": [60]},  # Wait 1초
        {"code": 221, "indent": 0, "parameters": []},  # Fadeout
        {"code": 230, "indent": 0, "parameters": [60]},
        {"code": 354, "indent": 0, "parameters": []},  # Return to Title
        {"code": 0, "indent": 0, "parameters": []},
    ]
    ending_page = _make_ending_page(ending_cmds, sw_condition, trigger=3)  # Auto-Run

    new_event_id = max((e.get("id", 0) for e in existing_events if e), default=0) + 1
    ending_event = {
        "id": new_event_id,
        "name": "엔딩",
        "note": "",
        "pages": [idle_page, ending_page],
        "x": target_x,
        "y": target_y,
    }

    existing_events.append(ending_event)
    compiled_events[boss_map_id] = existing_events

    map_key = f"Map{boss_map_id:03d}.json"
    if map_key in final_project:
        final_project[map_key]["events"].append(ending_event)

    logger.info(
        "auto_repair R23: 보스 맵 '%s'(id=%d) 엔딩 이벤트 자동 삽입 (%d,%d) sw_id=%d",
        boss_spec.name,
        boss_map_id,
        target_x,
        target_y,
        boss_sw_id,
    )
    return compiled_events, final_project


def _auto_repair_troop_positions(final_project: dict) -> dict:
    """R17: Troops.json member 좌표를 스프라이트 실제 높이 기준 전투 화면 내로 클램핑.

    y < sprite_height / 2 이면 상체가 잘리므로 min_y = sprite_height // 2 로 보정.
    _BATTLER_HEIGHTS 테이블 미등록 시 _DEFAULT_SPRITE_HALF_H(96) 적용.
    """
    troops = final_project.get("Troops.json", [])
    for troop in troops:
        if troop is None:
            continue
        for member in troop.get("members", []):
            x, y = member.get("x", 0), member.get("y", 0)
            enemy_id = member.get("enemyId", 0)
            battler_name = _get_battler_name(final_project, enemy_id)
            sprite_h = _BATTLER_HEIGHTS.get(battler_name, _DEFAULT_SPRITE_HALF_H * 2)
            half_h = sprite_h // 2

            new_x = max(0, min(x, _BATTLE_W))
            new_y = max(half_h, min(y, _BATTLE_H))

            if new_x != x or new_y != y:
                logger.warning(
                    "auto_repair R17: Troops '%s' member (%d,%d) → (%d,%d) [%s, 스프라이트 높이=%dpx]",
                    troop.get("name", "?"),
                    x,
                    y,
                    new_x,
                    new_y,
                    battler_name or "?",
                    sprite_h,
                )
                member["x"] = new_x
                member["y"] = new_y
    return final_project


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


def _check_party_members(final_project: dict) -> list[str]:
    """System.json partyMembers 존재 여부 및 유효 Actor ID 참조 검증 (R28)."""
    errors = []
    system = final_project.get("System.json")
    if not isinstance(system, dict):
        return errors

    party = system.get("partyMembers")
    if party is None:
        errors.append("[R28] System.json partyMembers 누락")
        return errors
    if not isinstance(party, list) or len(party) == 0:
        errors.append("[R28] System.json partyMembers 비어있음")
        return errors

    actors = final_project.get("Actors.json", [])
    valid_actor_ids = {a["id"] for a in actors if isinstance(a, dict)}
    for aid in party:
        if aid not in valid_actor_ids:
            errors.append(f"[R28] System.json partyMembers: actor_id={aid} Actors.json에 없음")

    return errors


def _auto_repair_party_members(final_project: dict) -> dict:
    """R28: partyMembers에서 Actors.json에 없는 유효하지 않은 ID만 제거.

    임의 actor 삽입은 하지 않는다 — 중복 위험 및 의도 훼손 가능성.
    제거 후 비어있으면 교정 불가 경고만 남긴다.
    """
    system = final_project.get("System.json")
    if not isinstance(system, dict):
        return final_project

    party = system.get("partyMembers")
    if not isinstance(party, list):
        return final_project  # 누락 케이스는 수정 불가 (생성 단계 문제)

    actors = final_project.get("Actors.json", [])
    valid_set = {a["id"] for a in actors if isinstance(a, dict)}

    repaired = [aid for aid in party if aid in valid_set]
    if repaired == party:
        return final_project  # 변경 없음

    removed = set(party) - set(repaired)
    logger.warning("auto_repair R28: partyMembers 유효하지 않은 ID %s 제거 → %s", removed, repaired)
    system["partyMembers"] = repaired

    if not repaired:
        logger.error("auto_repair R28: partyMembers 제거 후 비어있음 — 게임 시작 불가 가능성")

    return final_project


def _check_event_dsl_empty(
    event_dsl: dict[int, list],
    map_specs: list[MapSpec],
) -> list[str]:
    """event_planner 결과 DSL이 맵별로 완전히 비어있는지 검증 (R26).

    event_dsl이 없으면 검증 스킵 (샘플맵 phase_limit="maps" 등 event_planner 미실행 케이스).
    """
    if not event_dsl or not map_specs:
        return []
    errors = []
    for spec in map_specs:
        dsl_list = event_dsl.get(spec.map_id)
        if dsl_list is not None and len(dsl_list) == 0:
            errors.append(
                f"[R26] Map{spec.map_id}('{spec.name}') event_dsl 비어있음 — 이벤트 미생성"
            )
    return errors


def _check_connection_info_completeness(
    connection_info: dict[int, MapConnectionInfo],
    map_specs: list[MapSpec],
) -> list[str]:
    """map_specs의 모든 맵이 connection_info에 있는지 검증 (R27).

    누락 시 _auto_repair_isolated_maps가 해당 맵을 스킵하여 고립 상태가 유지될 수 있음.
    샘플맵은 sample_map_selector가 빈 connection_info를 채우므로 통상 발생하지 않음.
    """
    if not map_specs or not connection_info:
        return []
    errors = []
    for spec in map_specs:
        if spec.map_id not in connection_info:
            errors.append(
                f"[R27] Map{spec.map_id}('{spec.name}') connection_info 누락 — "
                f"고립 맵 auto-repair 스킵 가능성"
            )
    return errors


def _run_error_checks(
    final_project: dict,
    id_table: IdTable,
    switch_table: SwitchTable,
    map_specs: list[MapSpec],
    map_tiles: dict[int, list[int]],
    compiled_events: dict[int, list[dict]],
    event_dsl: dict[int, list] | None = None,
    connection_info: dict[int, MapConnectionInfo] | None = None,
) -> list[str]:
    """모든 error 검증을 실행하고 오류 목록 반환."""
    errors: list[str] = []
    errors.extend(_check_null_at_index_0(final_project))
    errors.extend(_check_id_references(final_project, id_table))
    errors.extend(_check_array_lengths(final_project))
    errors.extend(_check_start_position(final_project, map_tiles))
    errors.extend(_check_troop_positions(final_project))
    errors.extend(_check_map_id_consistency(final_project))
    errors.extend(_check_resource_filenames(final_project))
    errors.extend(_check_party_members(final_project))
    if event_dsl is not None:
        errors.extend(_check_event_dsl_empty(event_dsl, map_specs))
    if connection_info is not None:
        errors.extend(_check_connection_info_completeness(connection_info, map_specs))
    if map_specs and compiled_events:
        errors.extend(_check_ending_reachable(map_specs, compiled_events, id_table, switch_table))
    return errors


async def generation_validator(state: GenerationState) -> dict:
    """I 노드: 생성된 프로젝트 파일 검증.

    검증 흐름:
      1. error 검증 실행
      2. auto-repair 적용 (R16 / R18 / R28 / R19 / R_NULL / R1 / R25 / R23 / R22)
      3. repair 후 재검증 → 남은 오류만 retry 라우팅
    """
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
    game_spec: GameSpec | None = state.get("game_spec")  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    map_tiles: dict[int, list[int]] = state.get("map_tiles") or {}
    compiled_events: dict[int, list[dict]] = state.get("compiled_events") or {}
    connection_info: dict[int, MapConnectionInfo] | None = state.get("connection_info") or None
    # event_dsl: event_planner가 실행된 경우에만 존재 (샘플맵 phase_limit="maps" 등은 None)
    event_dsl: dict[int, list] | None = state.get("event_dsl")
    retry_count: int = state.get("retry_count", 0)

    warnings: list[str] = []
    extra_state: dict = {}

    # ── 1단계: 초기 error 검증 ───────────────────────────────────────────────
    errors = _run_error_checks(
        final_project,
        id_table,
        switch_table,
        map_specs,
        map_tiles,
        compiled_events,
        event_dsl=event_dsl,
        connection_info=connection_info,
    )

    # ── 2단계: auto-repair (LLM retry 없이 인-플레이스 수정) ─────────────────
    tags = {err.split("]")[0].lstrip("[") for err in errors if "]" in err}
    repaired_tags: set[str] = set()

    # R16: 시작 위치 통행 불가 → BFS walkable 교정 (방어코드, LLM 없음)
    if "R16" in tags:
        final_project = _auto_repair_start_position(final_project, map_tiles)
        repaired_tags.add("R16")

    # R18: MapInfos ↔ Map*.json 불일치 → 고아 항목 제거/추가 (방어코드, LLM 없음)
    if "R18" in tags:
        final_project = _auto_repair_map_id_consistency(final_project)
        repaired_tags.add("R18")

    # R28: partyMembers 누락/비어있음 → 첫 번째 actor로 자동 채움 (LLM 없음)
    if "R28" in tags:
        final_project = _auto_repair_party_members(final_project)
        repaired_tags.add("R28")

    # R17: Troop member 좌표 전투 화면 밖 → 스프라이트 크기 기준 클램핑 (LLM 없음)
    if "R17" in tags:
        final_project = _auto_repair_troop_positions(final_project)
        repaired_tags.add("R17")

    # R19: characterName/faceName 공백 → 언더스코어 교정 (LLM 없음)
    if "R19" in tags:
        final_project = _auto_repair_resource_filenames(final_project)
        repaired_tags.add("R19")

    # R_NULL: index-0 null 교정 (LLM 없음)
    if "R_NULL" in tags:
        final_project = _auto_repair_null_at_index_0(final_project)
        repaired_tags.add("R_NULL")

    # R1: actors classId 불일치 → actors만 LLM 재생성
    if "R1" in tags and game_spec is not None:
        final_project = await _auto_repair_actor_class_ids(final_project, game_spec, id_table)
        repaired_tags.add("R1")

    # R25: 고립 맵 → 워프 이벤트 삽입
    _r25_repaired = False
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
                connection_info=connection_info or {},
                id_table=id_table,
            )
            for name in iso_names:
                warnings.append(f"[R25] 고립된 맵 '{name}' — 워프 이벤트 자동 삽입됨")
            _r25_repaired = True

    # R23: 엔딩 이벤트 없음 → 자동 삽입
    if "R23" in tags and map_specs and compiled_events:
        compiled_events, final_project = _auto_repair_ending_event(
            compiled_events, final_project, map_specs, switch_table, id_table
        )
        repaired_tags.add("R23")

    # R22: 좌표 중복 → reachable 좌표로 재배치 (retry 대신 인-플레이스 수정)
    # R22 check는 warning 경로에 있어 tags에 포함 안 됨 → 직접 재검증으로 트리거
    if compiled_events:
        _r22_conflicts = _check_event_coordinate_conflicts(compiled_events)
        if _r22_conflicts:
            compiled_events = _auto_repair_coordinate_conflicts(
                compiled_events, final_project, map_specs, map_tiles
            )
            repaired_tags.add("R22")

    # repair가 하나라도 있으면 state 업데이트
    if repaired_tags or _r25_repaired:
        extra_state["compiled_events"] = compiled_events
        extra_state["final_project"] = final_project

    # ── 3단계: repair 후 재검증 ──────────────────────────────────────────────
    # R25 단독 수정도 포함 — 삽입된 워프 이벤트가 R22를 유발할 수 있음
    if repaired_tags or _r25_repaired:
        errors = _run_error_checks(
            final_project,
            id_table,
            switch_table,
            map_specs,
            map_tiles,
            compiled_events,
            event_dsl=event_dsl,
            connection_info=connection_info,
        )
        logger.info(
            "generation_validator: auto-repair 적용 후 재검증 (repaired=%s, r25=%s, remaining=%d)",
            repaired_tags,
            _r25_repaired,
            len(errors),
        )

        # R25 재검증: 워프 삽입 후 고립 해소 여부 확인
        if _r25_repaired and map_specs and compiled_events:
            still_isolated = _check_map_reachability(compiled_events, map_specs, id_table)
            if still_isolated:
                iso_names = [
                    next(
                        (s.name for s in map_specs if id_table.get_id("maps", s.name) == mid),
                        f"Map{mid}",
                    )
                    for mid in still_isolated
                ]
                logger.warning(
                    "generation_validator: R25 재검증 — 워프 삽입 후에도 고립 맵 잔존: %s",
                    iso_names,
                )
                for name in iso_names:
                    warnings.append(f"[R25] 워프 삽입 후에도 고립 맵 잔존: '{name}'")

    # ── warning 검증 (통과, 메시지만) ────────────────────────────────────────
    warnings.extend(_check_balance(final_project))
    if compiled_events:
        warnings.extend(_check_event_coordinate_conflicts(compiled_events))
        warnings.extend(_check_event_character_names(compiled_events))
    if switch_table:
        warnings.extend(_check_switch_semantic_conflicts(switch_table))

    validation_passed = len(errors) == 0

    # MAX_RETRY 초과 후에도 크리티컬 오류 잔존 → 명시적 실패 로깅
    if not validation_passed and retry_count >= MAX_RETRY:
        final_err_tags = {err.split("]")[0].lstrip("[") for err in errors if "]" in err}
        critical_remaining = final_err_tags & _CRITICAL_TAGS
        if critical_remaining:
            logger.error(
                "generation_validator: MAX_RETRY(%d) 초과, 크리티컬 오류 %s 잔존 → 강제 실패",
                MAX_RETRY,
                critical_remaining,
            )

    if errors:
        logger.warning("generation_validator: %d 오류 발견 (retry=%d)", len(errors), retry_count)
        for err in errors:
            logger.warning("  %s", err)
    else:
        logger.info(
            "generation_validator: 검증 통과%s",
            f" (auto-repair: {repaired_tags})" if repaired_tags else "",
        )

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
    """validator 이후 라우팅 결정.

    auto-repair 대상(R16 / R17 / R18 / R19 / R_NULL / R1 / R22 / R23 / R25 / R28)은
    generation_validator 내에서 인-플레이스 수정 후 재검증을 거침.
    여기서는 repair 후에도 남은 오류만 retry 라우팅.
    """
    errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)

    if not errors:
        return "respond"

    tags = {err.split("]")[0].lstrip("[") for err in errors if "]" in err}

    if retry_count >= MAX_RETRY:
        critical_remaining = tags & _CRITICAL_TAGS
        if critical_remaining:
            logger.error(
                "route_after_validation: MAX_RETRY(%d) 초과, 크리티컬 오류 %s — 실패 응답",
                MAX_RETRY,
                critical_remaining,
            )
        return "respond"

    # R_NULL / R1 / R28: auto-repair 후에도 남으면 전체 asset 재시도
    # R28: partyMembers 제거 후 빈 배열 → actor 재생성 필요 (발생 빈도 낮음, 방어코드)
    if "R1" in tags or "R_NULL" in tags or "R28" in tags:
        return "retry_assets"

    # R23 / R26 / R27: 이벤트 재시도
    # R26: event_dsl 비어있음 → event_planner 재실행
    # R27: connection_info 누락 → event_planner 재실행 (event_planner는 empty connection으로 폴백)
    if "R23" in tags or "R26" in tags or "R27" in tags:
        return "retry_events"

    return "respond"
