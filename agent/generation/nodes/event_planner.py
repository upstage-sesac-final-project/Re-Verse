"""F 노드 — event_planner: 맵별 YAML DSL 생성 (LLM 맵당 1회, 병렬).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.F
canonical: docs/The_world/prompt_engineering.md §F. 이벤트 기획자
"""

import asyncio
import logging
import re
from typing import cast

import yaml
from pydantic import TypeAdapter, ValidationError

from agent.core.llm_client import invoke_llm
from agent.generation.compilers.dsl_models import (
    BattleEvent,
    DslEvent,
    GateEvent,
    NpcEvent,
    QuestChestEvent,
    TransferEvent,
)
from agent.generation.mapgen.tile_checker import (
    get_all_safe_coords,
    get_reachable_coords,
)
from agent.generation.models import GameSpec, MapConnectionInfo, MapScreenplay, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.prompts.event_planner_prompt import build_event_planner_prompt
from agent.generation.rag_context import get_event_planner_context
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7  # 이벤트 대화/시나리오 — 창의적 텍스트 생성

_dsl_event_adapter: TypeAdapter = TypeAdapter(DslEvent)


async def event_planner(state: GenerationState) -> dict:
    """F 노드: 맵별 YAML DSL 생성 (asyncio.gather 병렬)."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]
    connection_info: dict[int, MapConnectionInfo] = state.get("connection_info") or {}
    map_tiles: dict[int, list[int]] = state.get("map_tiles") or {}
    generated_assets: dict = state.get("generated_assets") or {}
    # Tilesets.json: generated_assets에는 이 시점에 없으므로 base_game에서 직접 로드
    from agent.generation.nodes.integrator import load_base_tilesets

    tilesets: list | None = load_base_tilesets()

    # troop_name → (character_name, character_index) 매핑 테이블 사전 구성
    # id_table.troops의 exact key를 사용하므로 런타임 문자열 파싱 불필요
    troop_to_sprite = _build_troop_sprite_map(game_spec, id_table, generated_assets)

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "event_plan",
            "progress": 65,
            "message": "이벤트 기획 중...",
        },
    )

    story_script: dict[int, MapScreenplay] = state.get("story_script") or {}

    tasks = [
        _plan_single_map(
            map_spec=spec,
            game_spec=game_spec,
            id_table=id_table,
            switch_table=switch_table,
            connection_info=connection_info.get(spec.map_id, _empty_connection(spec.map_id)),
            troop_to_sprite=troop_to_sprite,
            map_story=story_script.get(spec.map_id),
            tile_data=map_tiles.get(spec.map_id),
            tilesets=tilesets,
        )
        for spec in map_specs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    event_dsl: dict[int, list] = {}
    for spec, result in zip(map_specs, results):
        if isinstance(result, Exception):
            logger.error("Map%d 이벤트 기획 실패: %s", spec.map_id, result)
            result = _fallback_events(spec, id_table)

        screenplay = story_script.get(spec.map_id)
        conn = connection_info.get(spec.map_id, _empty_connection(spec.map_id))
        # LLM 생성 이동 이벤트 제거 → 코드로 재생성
        result = _strip_llm_move_events(result, spec.map_id)
        # 이 맵 screenplay에 없는 quest_chest 제거 (LLM이 다른 맵 아이템 생성하는 것 방지)
        result = _filter_extra_quest_chests(result, screenplay, spec.map_id)
        # acquisition 누락 보완 (quest_chest 미생성 시 자동 삽입)
        tile_data = map_tiles.get(spec.map_id)
        result = _ensure_acquisition_events(
            result, screenplay, spec, switch_table, tile_data=tile_data, tilesets=tilesets
        )
        # battle quest_chest quest_switch ↔ NPC set_switch 충돌 수정 (NPC 대화로 배틀 우회 방지)
        result = _fix_battle_quest_switch_collision(result, spec.map_id, switch_table)
        # NpcEvent condition_switch 검증: 존재하지 않는 _defeated 스위치 자동 교체
        result = _fix_npc_defeated_conditions(result, switch_table, spec.map_id)
        # 이동 이벤트 코드 생성 (condition = acquisitions.chest_switch)
        new_moves = _build_move_events(screenplay, conn, id_table, spec, map_specs)
        # 이동 이벤트 좌표도 통행 가능 여부 검증 (exit_tile이 벽/물 위인 경우 보정)
        if new_moves and tile_data and tilesets:
            new_moves = _validate_move_event_coords(new_moves, spec, tile_data, tilesets)
        result = result + new_moves

        # ── 최종 고립 제거 패스 ──────────────────────────────────────────────
        # _ensure_acquisition_events / _build_move_events 등 _validate_coords를
        # 우회하여 추가된 이벤트가 통행 가능하지만 스폰에서 도달 불가한 고립 타일에
        # 배치되는 경우를 여기서 일괄 제거·재배치한다.
        if tile_data and tilesets:
            result = _remove_isolated_events(result, spec, tile_data, tilesets)

        event_dsl[spec.map_id] = result

    logger.info("event_planner 완료: %d개 맵", len(event_dsl))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "event_plan",
            "summary": f"{len(event_dsl)}개 맵 이벤트 기획 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("event_plan")
    return {"event_dsl": event_dsl, "completed_phases": completed}


async def _plan_single_map(
    map_spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
    troop_to_sprite: dict[str, tuple[str, int]],
    map_story: MapScreenplay | None = None,
    tile_data: list[int] | None = None,
    tilesets: list | None = None,
) -> list:
    rag_context = get_event_planner_context(map_spec.map_type)
    for attempt in range(3):
        try:
            prompt = build_event_planner_prompt(
                map_spec,
                game_spec,
                id_table,
                switch_table,
                connection_info,
                rag_context,
                map_story=map_story,
            )
            raw = cast(str, await invoke_llm(prompt, temperature=_TEMPERATURE))
            events = _parse_dsl_safe(raw, map_spec.map_id)
            if events is None:
                logger.warning("Map%d DSL 파싱 실패 (시도 %d)", map_spec.map_id, attempt + 1)
                continue

            # 좌표 보정 전 tilesets 상태 로그 추가
            ts_status = f"로드됨 ({len(tilesets)}개)" if tilesets else "None (누락)"
            logger.info(
                "Map%d 좌표 검증 시작: tilesets=%s, tile_data=%s",
                map_spec.map_id,
                ts_status,
                "존재함" if tile_data else "None",
            )

            # 좌표 보정 (범위 초과 제거 + 통행 불가 타일 보정 + 중복 방지)
            valid = _validate_coords(events, map_spec, tile_data, tilesets, connection_info)
            valid = _validate_duplicate_names(valid, map_spec.map_id)

            valid = _validate_name_refs(valid, id_table, switch_table)
            valid = _validate_event_types(valid, map_spec)
            valid = _validate_npc_names(valid, id_table, map_story=map_story)
            if valid is not None:
                return _fix_battle_sprites(valid, troop_to_sprite)
        except Exception as e:
            logger.warning("Map%d 이벤트 기획 시도 %d 실패: %s", map_spec.map_id, attempt + 1, e)

    logger.error("Map%d 이벤트 기획 3회 실패 → 폴백 사용", map_spec.map_id)
    return _fallback_events(map_spec, id_table)


_YAML_BANG_RE = re.compile(r"(:\s+)(![^\s\n\"']+)")


def _parse_dsl_safe(raw_yaml: str, map_id: int) -> list | None:
    # ... (생략 없이 유지)
    try:
        # YAML 코드블록 제거
        text = raw_yaml.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        # !로 시작하는 unquoted 값은 YAML 타입 태그로 해석 → 따옴표로 감싸기
        # e.g., "character_name: !Crystal" → "character_name: \"!Crystal\""
        text = _YAML_BANG_RE.sub(r'\1"\2"', text)

        data = yaml.safe_load(text)
        if not isinstance(data, dict) or "events" not in data:
            logger.warning("Map%d: YAML에 'events' 키 없음", map_id)
            return None

        events = data["events"] or []
        return [_dsl_event_adapter.validate_python(e) for e in events]
    except (yaml.YAMLError, ValidationError, Exception) as e:
        logger.warning("Map%d DSL 파싱 실패: %s", map_id, e)
        return None


def _validate_coords(
    events: list,
    spec: MapSpec,
    tile_data: list[int] | None = None,
    tilesets: list | None = None,
    connection_info: MapConnectionInfo | None = None,
) -> list:
    """좌표가 맵 범위를 벗어나거나 통행 불가/도달 불가인 경우 보정."""
    valid = []
    # 1. 이미 사용 중인 좌표 집합 (입구, 출구 좌표 포함)
    used_coords: set[tuple[int, int]] = set()

    if connection_info:
        for et in connection_info.entry_tiles:
            used_coords.add((et["x"], et["y"]))
        for xt in connection_info.exit_tiles:
            used_coords.add((xt["x"], xt["y"]))

    # 2. 맵의 도달 가능한(Reachability) 안전한 좌표 미리 추출
    all_safe_coords = []
    if tile_data:
        # 플레이어 시작 지점에서 도달 가능한 타일만 추출 (고립 지역 및 빈 타일 지역 방지)
        all_safe_coords = get_reachable_coords(
            tile_data,
            spec.spawn_point[0],
            spec.spawn_point[1],
            spec.width,
            spec.height,
            spec.tileset_id,
            tilesets,
            avoid_damage=True,
            used_coords=used_coords,
        )

        # 만약 도달 가능 좌표가 너무 적다면 (탐색 실패 등), 전체 안전 좌표로 폴백
        if len(all_safe_coords) < 5:
            logger.warning(
                "Map%d: 도달 가능 좌표 부족 (%d개) -> 전체 안전 좌표 사용",
                spec.map_id,
                len(all_safe_coords),
            )
            all_safe_coords = get_all_safe_coords(
                tile_data,
                spec.width,
                spec.height,
                spec.tileset_id,
                tilesets,
                avoid_damage=True,
                used_coords=used_coords,
            )

        # 3. 좁은 통로(corridor) 타일을 제외한 선호 좌표 목록 미리 계산
        if tile_data and tilesets:
            from agent.generation.mapgen.tile_checker import filter_non_corridor_coords

            preferred_coords = filter_non_corridor_coords(
                all_safe_coords, tile_data, spec.width, spec.height, spec.tileset_id, tilesets
            )
        else:
            preferred_coords = list(all_safe_coords)
    else:
        preferred_coords = []

    # 연결성 체크에 필요한 출구 좌표 (gate/transfer 이벤트가 여기에 배치됨)
    exit_coords: set[tuple[int, int]] = set()
    if connection_info and tile_data and tilesets:
        for xt in connection_info.exit_tiles:
            exit_coords.add((xt["x"], xt["y"]))

    # 이미 배치된 이벤트 좌표 집합 (연결성·인접 체크용)
    placed_event_positions: set[tuple[int, int]] = set()

    for e in events:
        # 1. 맵 범위 체크 및 통행 가능 여부 체크
        is_in_bounds = 0 <= e.x < spec.width and 0 <= e.y < spec.height
        is_safe = False
        if is_in_bounds and tile_data:
            from agent.generation.mapgen.tile_checker import is_walkable

            is_safe = (
                is_walkable(
                    tile_data,
                    e.x,
                    e.y,
                    spec.width,
                    spec.height,
                    spec.tileset_id,
                    tilesets,
                    avoid_damage=True,
                )
                and (e.x, e.y) not in used_coords
            )

            # 추가: 원래 좌표가 '도달 가능' 리스트에 없는 고립 지역이라면 안전하지 않은 것으로 간주
            if is_safe and all_safe_coords and (e.x, e.y) not in all_safe_coords:
                logger.info(
                    "Map%d 이벤트 '%s': 고립된 지역(%d, %d) 감지 -> 보정 대상",
                    spec.map_id,
                    e.name,
                    e.x,
                    e.y,
                )
                is_safe = False

        # 2. 위치 결정: 안전하지 않으면 보정, 안전하면 원래 좌표 사용
        def _pick_best_coord(ox: int, oy: int, candidate_list: list) -> tuple[int, int] | None:
            """candidate_list에서 배치 우선순위에 따라 최적 좌표를 선택한다.

            우선순위 (tier):
              0 = 비-통로 + 기배치 이벤트 비-인접 (이상적)
              1 = 비-통로
              2 = 전체 후보 (폴백)

            각 tier 내에서 맨해튼 거리 오름차순으로 정렬.
            상위 MAX_CHECK개 후보에 대해 연결성 체크를 수행하고,
            스폰 → 출구 도달 가능성을 유지하는 첫 번째 좌표를 반환한다.
            모든 후보가 실패하면 연결성 무시하고 tier/거리 최우선 좌표를 반환한다.
            """
            if not candidate_list:
                return None

            MAX_CHECK = 30  # 성능 상한: 최대 30개 후보까지만 연결성 체크

            adj_nbrs = {
                (px + dx, py + dy)
                for px, py in placed_event_positions
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            }
            preferred_set = set(preferred_coords)

            def _tier(c: tuple[int, int]) -> int:
                in_pref = c in preferred_set
                not_adj = c not in adj_nbrs
                if in_pref and not_adj:
                    return 0
                if in_pref:
                    return 1
                return 2

            sorted_candidates = sorted(
                candidate_list,
                key=lambda c: (_tier(c), abs(c[0] - ox) + abs(c[1] - oy)),
            )

            fallback = sorted_candidates[0]  # 연결성 체크 실패 시 사용

            if not (tile_data and tilesets and exit_coords):
                # 연결성 체크 정보 없음 → tier/거리 기준만 사용
                return fallback

            from agent.generation.mapgen.tile_checker import are_exits_reachable

            spawn = (spec.spawn_point[0], spec.spawn_point[1])
            for candidate in sorted_candidates[:MAX_CHECK]:
                test_blocked = placed_event_positions | {candidate}
                if are_exits_reachable(
                    tile_data,
                    spawn[0],
                    spawn[1],
                    spec.width,
                    spec.height,
                    spec.tileset_id,
                    tilesets,
                    exit_coords,
                    test_blocked,
                ):
                    return candidate

            # 모든 후보가 연결성 체크 실패 → tier/거리 최우선 좌표로 폴백
            logger.warning(
                "Map%d 이벤트 '%s': 연결성 유지 후보 없음 → 거리 기준 폴백 (%d,%d)",
                spec.map_id,
                e.name,
                fallback[0],
                fallback[1],
            )
            return fallback

        if not is_in_bounds or not is_safe:
            if all_safe_coords:
                ox = e.x if is_in_bounds else spec.width // 2
                oy = e.y if is_in_bounds else spec.height // 2
                chosen = _pick_best_coord(ox, oy, all_safe_coords)
                if chosen is None:
                    logger.warning(
                        "Map%d 이벤트 '%s': 도달 가능한 안전 좌표가 없음 → 제거",
                        spec.map_id,
                        e.name,
                    )
                    continue
                nx, ny = chosen
                logger.info(
                    "Map%d 이벤트 '%s' 좌표 보정 (도달 가능 최근접): (%d, %d) -> (%d, %d)",
                    spec.map_id,
                    e.name,
                    e.x,
                    e.y,
                    nx,
                    ny,
                )
                e.x, e.y = nx, ny
                used_coords.add((nx, ny))
                all_safe_coords.remove((nx, ny))
                try:
                    preferred_coords.remove((nx, ny))
                except ValueError:
                    pass
                placed_event_positions.add((nx, ny))
                valid.append(e)
            else:
                logger.warning(
                    "Map%d 이벤트 '%s': 도달 가능한 안전 좌표가 없음 → 제거", spec.map_id, e.name
                )
        else:
            # 원래 좌표가 안전. 단, 통로 타일이거나 다른 이벤트에 인접하면 더 나은 위치로 이동
            preferred_set = set(preferred_coords)
            adj_nbrs = {
                (px + dx, py + dy)
                for px, py in placed_event_positions
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            }
            needs_relocation = (e.x, e.y) not in preferred_set or (e.x, e.y) in adj_nbrs
            if needs_relocation and all_safe_coords:
                chosen = _pick_best_coord(e.x, e.y, all_safe_coords)
                if chosen and chosen != (e.x, e.y):
                    nx, ny = chosen
                    logger.info(
                        "Map%d 이벤트 '%s' 통로/인접 회피 재배치: (%d, %d) -> (%d, %d)",
                        spec.map_id,
                        e.name,
                        e.x,
                        e.y,
                        nx,
                        ny,
                    )
                    e.x, e.y = nx, ny
                    used_coords.add((nx, ny))
                    all_safe_coords.remove((nx, ny))
                    try:
                        preferred_coords.remove((nx, ny))
                    except ValueError:
                        pass
                    placed_event_positions.add((nx, ny))
                    valid.append(e)
                    continue
            # 재배치 불필요하거나 더 나은 위치가 없음 → 원래 좌표 그대로 사용
            used_coords.add((e.x, e.y))
            if (e.x, e.y) in all_safe_coords:
                all_safe_coords.remove((e.x, e.y))
            try:
                preferred_coords.remove((e.x, e.y))
            except ValueError:
                pass
            placed_event_positions.add((e.x, e.y))
            valid.append(e)

    return valid


def _validate_move_event_coords(
    move_events: list,
    spec: "MapSpec",
    tile_data: list[int],
    tilesets: list,
) -> list:
    """_build_move_events가 반환한 게이트/귀환/워프 이벤트의 좌표를 검증한다.

    exit_tile 좌표가 벽이나 물 위인 경우 근처 통행 가능 타일로 보정한다.
    이 이벤트들은 _validate_coords를 거치지 않아 별도 검증이 필요하다.
    """
    from agent.generation.mapgen.tile_checker import find_nearest_safe_coord, is_walkable

    corrected = []
    used: set[tuple[int, int]] = set()
    for ev in move_events:
        x, y = ev.x, ev.y
        if not is_walkable(tile_data, x, y, spec.width, spec.height, spec.tileset_id, tilesets):
            nx, ny = find_nearest_safe_coord(
                tile_data,
                x,
                y,
                spec.width,
                spec.height,
                spec.tileset_id,
                tilesets,
                max_radius=8,
                used_coords=used,
            )
            if is_walkable(
                tile_data, nx, ny, spec.width, spec.height, spec.tileset_id, tilesets
            ) and (nx, ny) != (x, y):
                logger.info(
                    "Map%d 이동이벤트 '%s' 좌표 보정 (통행 불가): (%d, %d) -> (%d, %d)",
                    spec.map_id,
                    ev.name,
                    x,
                    y,
                    nx,
                    ny,
                )
                ev.x, ev.y = nx, ny
            else:
                logger.warning(
                    "Map%d 이동이벤트 '%s': 근처 통행 가능 좌표 없음, 원래 위치 유지 (%d, %d)",
                    spec.map_id,
                    ev.name,
                    x,
                    y,
                )
        used.add((ev.x, ev.y))
        corrected.append(ev)
    return corrected


def _validate_duplicate_names(events: list, map_id: int) -> list:
    """이벤트 이름 중복 제거 (첫 번째만 유지)."""
    seen: set[str] = set()
    valid = []
    for e in events:
        if e.name in seen:
            logger.warning(
                "Map%d 이벤트 '%s' 이름 중복 → 제거 (첫 번째만 유지)",
                map_id,
                e.name,
            )
        else:
            seen.add(e.name)
            valid.append(e)
    return valid


def _correct_troop_name(raw: str, all_troop_names: set[str]) -> str | None:
    """LLM이 suffix를 생략하거나 잘못 붙인 troop 이름을 자동 보정한다.

    보정 순서:
      1. × 주변 공백 제거 ("이름 × 2" → "이름×2")
      2. 적 이름 내 언더스코어→공백 변환 ("이름_보스_단독" → "이름 보스_단독")
      3. _단독 suffix 추가 ("이름" → "이름_단독")
      4. ×1 suffix 추가 ("이름" → "이름×1")
      5. 접두 부분 매칭 (all_troop_names 중 raw로 시작하는 첫 번째)
    """
    # 1. × 앞뒤 공백/underscore 정규화: "이름 × 2" → "이름×2"
    normalized = re.sub(r"\s*×\s*", "×", raw)
    if normalized in all_troop_names:
        return normalized

    # 2. 적 이름 부분의 언더스코어를 공백으로 변환
    #    "알고리즘_관리자_단독" → base="알고리즘_관리자" → "알고리즘 관리자_단독"
    #    "에러_고블린×2"        → base="에러_고블린"     → "에러 고블린×2"
    if "×" in normalized:
        base_part, count_part = normalized.rsplit("×", 1)
        spaced = f"{base_part.replace('_', ' ')}×{count_part}"
        if spaced in all_troop_names:
            return spaced
    elif normalized.endswith("_단독"):
        base_part = normalized[: -len("_단독")]
        spaced = f"{base_part.replace('_', ' ')}_단독"
        if spaced in all_troop_names:
            return spaced

    base = normalized  # 이후 suffix 시도는 정규화된 이름 기준

    # 3. _단독 suffix
    candidate = f"{base}_단독"
    if candidate in all_troop_names:
        return candidate

    # 4. ×1 suffix
    candidate = f"{base}×1"
    if candidate in all_troop_names:
        return candidate

    # 5. 접두 부분 매칭 (정렬해서 가장 짧은 것 우선)
    matches = sorted(t for t in all_troop_names if t.startswith(base))
    return matches[0] if matches else None


def _validate_name_refs(events: list, id_table: IdTable, switch_table: SwitchTable) -> list:
    """id_table에 없는 이름을 참조하는 이벤트 필터링."""
    valid = []
    all_item_names = set(id_table.items) | set(id_table.weapons) | set(id_table.armors)
    all_map_names = set(id_table.maps)
    all_troop_names = set(id_table.troops)

    for e in events:
        try:
            if isinstance(e, TransferEvent) and e.to_map not in all_map_names:
                logger.warning(
                    "transfer 이벤트 '%s': to_map '%s' 존재하지 않음 → 제거", e.name, e.to_map
                )
                continue
            if hasattr(e, "troop") and e.troop is not None and e.troop not in all_troop_names:
                corrected = _correct_troop_name(e.troop, all_troop_names)
                if corrected:
                    logger.info(
                        "battle 이벤트 '%s': troop '%s' → '%s' 자동 보정",
                        e.name,
                        e.troop,
                        corrected,
                    )
                    e.troop = corrected
                else:
                    logger.warning(
                        "battle 이벤트 '%s': troop '%s' 존재하지 않음 → 제거", e.name, e.troop
                    )
                    continue
            if hasattr(e, "item") and e.item not in all_item_names:
                logger.warning("chest 이벤트 '%s': item '%s' 존재하지 않음 → 제거", e.name, e.item)
                continue
            valid.append(e)
        except Exception as exc:
            logger.warning("이벤트 '%s' 검증 오류: %s → 제거", getattr(e, "name", "?"), exc)

    return valid


# 맵 타입별 생성 금지 이벤트 타입
_FORBIDDEN_EVENT_TYPES: dict[str, set[str]] = {
    "town": {"battle", "ending", "transfer"},  # 마을 — 전투·엔딩·transfer 금지, 출구는 gate 전용
    "boss": {"gate", "transfer"},  # 보스맵 — gate/transfer 금지, 엔딩으로만 종료
    "dungeon": {"ending"},  # 던전 — 엔딩 금지
    "field": {"ending"},  # 필드 — 엔딩 금지
}


def _validate_npc_names(
    events: list,
    id_table: IdTable,
    map_story: MapScreenplay | None = None,
) -> list:
    """NPC 이름이 액터(주인공 파티) 이름과 겹치면 role 기반으로 자동 수정.

    수정 우선순위:
      1. map_story.npcs에서 동일 이름 NPC의 role 사용
      2. role 없으면 map_story.npcs의 role 중 첫 번째 미사용 role
      3. 그래도 없으면 "안내인" (강제 접두사 금지)
    """
    actor_names: set[str] = set(id_table.actors.keys())
    if not actor_names:
        return events

    # story_script의 NPC name → role 역매핑
    story_name_to_role: dict[str, str] = {}
    if map_story:
        for npc in map_story.npcs:
            story_name_to_role[npc.name] = npc.role

    for e in events:
        if e.type not in ("npc", "shop"):
            continue
        if e.name not in actor_names:
            continue

        # role 결정: story_script 매칭 → 첫 번째 story NPC role → 기본값
        role = story_name_to_role.get(e.name)
        if not role and map_story and map_story.npcs:
            role = map_story.npcs[0].role
        if not role or role in actor_names:
            role = "안내인"

        logger.warning(
            "NPC 이름 '%s'이 액터 이름과 충돌 → '%s'(role)로 자동 수정",
            e.name,
            role,
        )
        e.name = role

    return events


def _validate_event_types(events: list, spec: MapSpec) -> list:
    """맵 타입에 허용되지 않는 이벤트 타입 제거."""
    forbidden = _FORBIDDEN_EVENT_TYPES.get(spec.map_type, set())
    if not forbidden:
        return events
    valid = []
    for e in events:
        if e.type in forbidden:
            logger.warning(
                "Map%d('%s') 이벤트 '%s' (type=%s) — %s 맵에서 금지된 타입 → 제거",
                spec.map_id,
                spec.name,
                e.name,
                e.type,
                spec.map_type,
            )
        else:
            valid.append(e)
    return valid


_SF_KEYWORDS = ("sf", "sci-fi", "science", "사이버", "로봇", "우주", "미래")


def _build_troop_sprite_map(
    game_spec: GameSpec,
    id_table: IdTable,
    generated_assets: dict,
) -> dict[str, tuple[str, int]]:
    """id_table.troops의 모든 troop_name에 대해 (character_name, character_index)를 사전 결정."""
    enemies_json: list = generated_assets.get("Enemies.json") or []
    enemy_id_to_battler: dict[int, str] = {
        e["id"]: e["battlerName"]
        for e in enemies_json
        if e and isinstance(e, dict) and e.get("id") and e.get("battlerName")
    }
    fallback_enemy_ids: set[int] = {
        e["id"]
        for e in enemies_json
        if e and isinstance(e, dict) and e.get("id") and "(fallback)" in (e.get("note") or "")
    }

    enemy_tier: dict[str, str] = {e.name: e.tier for e in game_spec.enemies}
    battler_map: dict[str, str] = {
        name: enemy_id_to_battler[eid]
        for name, eid in id_table.enemies.items()
        if eid in enemy_id_to_battler
    }
    fallback_enemy_names: set[str] = {
        name for name, eid in id_table.enemies.items() if eid in fallback_enemy_ids
    }
    is_sf = any(k in game_spec.theme.lower() for k in _SF_KEYWORDS)

    result: dict[str, tuple[str, int]] = {}
    for troop_name, troop_id in id_table.troops.items():
        if "×" in troop_name:
            spec_name = troop_name.rsplit("×", 1)[0]
        elif troop_name.endswith("_단독"):
            spec_name = troop_name[: -len("_단독")]
        else:
            spec_name = troop_name

        if spec_name in fallback_enemy_names:
            result[troop_name] = ("Nature", 1)
            continue

        battler_name = battler_map.get(spec_name)
        if battler_name and battler_name in _BATTLER_TO_MAP_SPRITE:
            result[troop_name] = _BATTLER_TO_MAP_SPRITE[battler_name]
            continue

        tier = enemy_tier.get(spec_name, "normal")
        if is_sf:
            char_name = "SF_Monster"
            char_idx = (6 + troop_id % 2) if tier in ("boss", "elite") else troop_id % 6
        elif tier == "boss":
            char_name = f"$BigMonster{1 + troop_id % 2}"
            char_idx = 0
        else:
            char_name = "Evil"
            char_idx = 7
        result[troop_name] = (char_name, char_idx)

    return result


_BATTLER_TO_MAP_SPRITE: dict[str, tuple[str, int]] = {
    "Zombie": ("Monster", 1),
    "Caitsith": ("Monster", 0),
    "Undine": ("Monster", 0),
    "Goblin": ("Monster", 1),
    "Matango": ("Monster", 1),
    "Gnome": ("Monster", 1),
    "Oddegg": ("Monster", 1),
    "Frilledlizard": ("Monster", 1),
    "Wolfman": ("Monster", 2),
    "Tigerbunny": ("Monster", 2),
    "Birdman": ("Monster", 2),
    "Hakutaku": ("Monster", 2),
    "Plasma": ("Monster", 3),
    "Sandworm": ("Monster", 3),
    "Mechascorpion": ("Monster", 3),
    "Machinerybee": ("Monster", 3),
    "Salamander": ("Monster", 3),
    "Foxman": ("Monster", 4),
    "Sylph": ("Monster", 4),
    "Harpy": ("Monster", 4),
    "Unicorn": ("Monster", 4),
    "Petitdevil": ("Monster", 5),
    "Crow": ("Monster", 5),
    "Crab": ("Monster", 5),
    "Demonpot": ("Monster", 5),
    "Evilbook": ("Monster", 5),
    "Mimic": ("Monster", 5),
    "Wraith": ("Monster", 6),
    "Gatekeeper": ("Monster", 6),
    "Hi_monster": ("Monster", 6),
    "Demoncount": ("Monster", 7),
    "Mercenary": ("Evil", 0),
    "Sailor": ("Evil", 0),
    "Witch": ("Evil", 2),
    "Medusa": ("Evil", 2),
    "Siren": ("Evil", 2),
    "Sorcerer": ("Evil", 3),
    "Berserker": ("Evil", 4),
    "Darkelf": ("Evil", 5),
    "Highking": ("Evil", 6),
    "Captain": ("Evil", 6),
    "Blackknight": ("Evil", 6),
    "Stoneknight": ("Evil", 6),
    "Lich": ("$BigMonster1", 0),
    "Goddess_of_death": ("$BigMonster1", 0),
    "Treant": ("$BigMonster1", 3),
    "Kraken": ("$BigMonster1", 6),
    "Ketos": ("$BigMonster1", 6),
    "Hydra": ("$BigMonster1", 9),
    "Dragon": ("$BigMonster2", 0),
    "Demon": ("$BigMonster2", 0),
    "God_of_light": ("$BigMonster2", 3),
    "Goddess": ("$BigMonster2", 3),
    "Evilgod": ("$BigMonster2", 6),
    "Demon_metamorphosis": ("$BigMonster2", 9),
    "SF_Boss": ("SF_Monster", 0),
    "SF_Madscientist": ("SF_Monster", 0),
    "SF_Agent": ("SF_Monster", 1),
    "SF_Mafia": ("SF_Monster", 1),
    "SF_Specialforces": ("SF_Monster", 1),
    "SF_Armygorilla": ("SF_Monster", 1),
    "SF_Armymonkey": ("SF_Monster", 1),
    "SF_Brownbear": ("SF_Monster", 1),
    "SF_Shadow": ("SF_Monster", 2),
    "SF_Zombiedog": ("SF_Monster", 2),
    "SF_Wolf": ("SF_Monster", 2),
    "SF_Whitewolf": ("SF_Monster", 2),
    "SF_Anaconda": ("SF_Monster", 2),
    "SF_Kamaitachi": ("SF_Monster", 2),
    "SF_Will_o_the_wisp": ("SF_Monster", 2),
    "SF_Jiangshi": ("SF_Monster", 2),
    "SF_Madclown": ("SF_Monster", 3),
    "SF_Hannyamask": ("SF_Monster", 3),
    "SF_Talkingmuppet": ("SF_Monster", 3),
    "SF_Evilteddybear": ("SF_Monster", 3),
    "SF_Kappa": ("SF_Monster", 3),
    "SF_Workrobot": ("SF_Monster", 4),
    "SF_Drone": ("SF_Monster", 4),
    "SF_Timebomb": ("SF_Monster", 4),
    "SF_Mechasphere": ("SF_Monster", 4),
    "SF_Slaughterrobot": ("SF_Monster", 5),
    "SF_Securityrobot": ("SF_Monster", 5),
    "SF_Cyborg": ("SF_Monster", 5),
    "SF_Enmadaio": ("SF_Monster", 6),
    "SF_Hermit": ("SF_Monster", 6),
    "SF_Demon_of_universe": ("SF_Monster", 6),
    "SF_Skullmask": ("SF_Monster", 6),
    "SF_Phoenix": ("SF_Monster", 6),
    "SF_Redogre": ("SF_Monster", 7),
    "SF_Blueogre": ("SF_Monster", 7),
}


def _fix_battle_sprites(events: list, troop_to_sprite: dict[str, tuple[str, int]]) -> list:
    for event in events:
        if not isinstance(event, BattleEvent):
            continue
        sprite = troop_to_sprite.get(event.troop)
        if sprite:
            event.character_name, event.character_index = sprite
    return events


def _fallback_events(spec: MapSpec, id_table: IdTable) -> list:
    events: list = []
    cx, cy = spec.width // 2, spec.height // 2
    for exit_spec in spec.exits:
        if exit_spec.to_map_id in {v for v in id_table.maps.values()}:
            to_name = next(
                (name for name, mid in id_table.maps.items() if mid == exit_spec.to_map_id), None
            )
            if to_name:
                ex, ey = {
                    "north": (cx, 1),
                    "south": (cx, spec.height - 2),
                    "east": (spec.width - 2, cy),
                    "west": (1, cy),
                }.get(exit_spec.direction, (cx, cy))
                events.append(
                    TransferEvent(
                        type="transfer",
                        name=f"{to_name}_이동",
                        x=ex,
                        y=ey,
                        to_map=to_name,
                        to_x=cx,
                        to_y=cy,
                    )
                )
    if spec.map_type == "town":
        events.append(NpcEvent(type="npc", name="마을주민", x=cx + 2, y=cy, dialogue=["..."]))
    return events


def _remove_isolated_events(
    events: list,
    spec: "MapSpec",
    tile_data: list[int],
    tilesets: list,
) -> list:
    """스폰에서 도달 불가한 고립 타일에 배치된 이벤트를 재배치하거나 제거한다.

    _validate_coords 이후에 추가된 이벤트(게이트, quest_chest 등)가
    통행 가능하지만 고립된 타일에 배치되는 경우를 최종 패스에서 잡아낸다.

    처리 순서:
      1. 스폰 기준 flood-fill로 도달 가능 집합 계산
      2. 이미 배치된 이벤트 좌표는 장애물로 간주하지 않음 (정적 고립만 처리)
      3. 고립된 이벤트 → 도달 가능 집합에서 가장 가까운 미사용 좌표로 재배치
      4. 도달 가능 집합이 비어 있으면 아무것도 하지 않음 (폴백)
    """
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
    if not reachable:
        return events  # 도달 가능 좌표 계산 실패 → 건드리지 않음

    reachable_set = set(reachable)
    used: set[tuple[int, int]] = {(e.x, e.y) for e in events if (e.x, e.y) in reachable_set}
    result = []

    for e in events:
        if (e.x, e.y) in reachable_set:
            result.append(e)
            continue

        # 이벤트가 고립 지역에 있음 → 가장 가까운 도달 가능·미사용 좌표로 이동
        candidates = reachable_set - used
        if candidates:
            nx, ny = min(candidates, key=lambda c: abs(c[0] - e.x) + abs(c[1] - e.y))
            logger.warning(
                "Map%d 이벤트 '%s' 고립 지역 (%d,%d) → 도달 가능 좌표 (%d,%d) 재배치",
                spec.map_id,
                e.name,
                e.x,
                e.y,
                nx,
                ny,
            )
            e.x, e.y = nx, ny
            used.add((nx, ny))
            result.append(e)
        else:
            logger.warning(
                "Map%d 이벤트 '%s' 고립 지역 (%d,%d) → 도달 가능 좌표 없음, 제거",
                spec.map_id,
                e.name,
                e.x,
                e.y,
            )

    return result


def _empty_connection(map_id: int) -> MapConnectionInfo:
    return MapConnectionInfo(map_id=map_id, exit_tiles=[], entry_tiles=[])


# ── 구조 이벤트 코드 직접 조립 ───────────────────────────────────────────────
#
# 역할 분리:
#   _strip_llm_move_events      LLM 생성 gate/transfer 제거
#   _ensure_acquisition_events  quest_chest 누락 보완 (아이템 획득 이벤트)
#   _build_move_events          gate/transfer 코드 생성 (condition = chest_switches)


def _strip_llm_move_events(events: list, map_id: int) -> list:
    """LLM이 생성한 gate/transfer 이벤트를 모두 제거한다.

    이동 이벤트는 _build_move_events가 코드로 직접 생성하므로 LLM 생성본은 사용하지 않는다.
    """
    _MOVE_TYPES = {"gate", "transfer"}
    stripped = [e for e in events if e.type not in _MOVE_TYPES]
    removed = len(events) - len(stripped)
    if removed:
        logger.info("Map%d LLM 이동 이벤트 %d개 제거 (코드 대체)", map_id, removed)
    return stripped


def _filter_extra_quest_chests(
    events: list,
    screenplay: MapScreenplay | None,
    map_id: int,
) -> list:
    """이 맵의 screenplay.acquisitions에 없는 quest_chest 이벤트를 제거한다.

    LLM이 체크리스트를 무시하고 다른 맵 아이템의 quest_chest를 생성하는 것을 방지한다.
    screenplay가 없으면 전체 통과 (폴백 맵은 그대로 유지).
    """
    if not screenplay:
        return events

    valid_chest_switches = {acq.chest_switch for acq in screenplay.acquisitions}

    filtered = []
    for e in events:
        if e.type == "quest_chest":
            chest_sw = getattr(e, "chest_switch", None)
            if chest_sw not in valid_chest_switches:
                logger.warning(
                    "Map%d quest_chest '%s' (chest_switch=%s) — 이 맵 acquisitions에 없음 → 제거",
                    map_id,
                    e.name,
                    chest_sw,
                )
                continue
        filtered.append(e)
    return filtered


def _ensure_acquisition_events(
    events: list,
    screenplay: MapScreenplay | None,
    spec: MapSpec,
    switch_table: SwitchTable | None = None,
    tile_data: list[int] | None = None,
    tilesets: list | None = None,
) -> list:
    """screenplay.acquisitions 중 quest_chest가 누락된 항목을 자동으로 보완한다.

    게이트 조건이 chest_switch 기반이므로, quest_chest가 없으면 게이트가 영원히 잠긴다.
    LLM이 정상 생성했으면 이 함수는 아무것도 추가하지 않는다.

    quest_type 결정 규칙:
    - boss맵: npc (boss_defeated_switch 사용)
    - town맵: npc (npc_set_switch 사용)
    - dungeon/field맵: battle ({item}_battle_won 스위치 사용, switch_table에 있으면)
    """
    if not screenplay or not screenplay.acquisitions:
        return events

    # 이미 생성된 quest_chest / chest 이벤트의 chest_switch 수집
    # quest_type=battle이면서 troop 없는 것은 컴파일 실패 예정 → 미존재로 처리
    existing_chest_switches: set[str] = set()
    for e in events:
        if e.type == "chest" and getattr(e, "chest_switch", None):
            # 일반 chest도 같은 chest_switch를 사용하면 중복 삽입 방지
            existing_chest_switches.add(e.chest_switch)
        elif e.type == "quest_chest" and getattr(e, "chest_switch", None):
            if getattr(e, "quest_type", "npc") == "battle" and not getattr(e, "troop", None):
                continue  # troop 없는 battle quest_chest는 재삽입 대상
            existing_chest_switches.add(e.chest_switch)

    # NPC set_switch 목록
    npc_set_switches = [npc.set_switch for npc in screenplay.npcs if npc.set_switch]

    # 보스맵: 아이템은 보스 격파 후 획득 → boss_defeated를 quest_switch로 사용
    boss_defeated_switch: str | None = None
    if screenplay.has_boss and screenplay.boss_name:
        boss_defeated_switch = f"{screenplay.boss_name}_defeated"

    # 맵 타입별 기본 quest_type
    is_battle_map = spec.map_type in ("dungeon", "field") and not boss_defeated_switch
    valid_switches = set(switch_table.switches.keys()) if switch_table else set()

    # 이 맵의 전투 이벤트에서 사용 가능한 troop 목록 수집 (battle quest_chest 자동 삽입 시 재사용)
    available_troops: list[str] = [
        e.troop for e in events if e.type == "battle" and getattr(e, "troop", None)
    ]

    cx, cy = spec.spawn_point

    # tile_data가 있으면 도달 가능 좌표 풀을 미리 구성 (통행 불가 타일 배치 방지)
    _reachable_pool: list[tuple[int, int]] | None = None
    if tile_data and tilesets:
        from agent.generation.mapgen.tile_checker import get_all_safe_coords, get_reachable_coords

        _reachable_pool = get_reachable_coords(
            tile_data,
            cx,
            cy,
            spec.width,
            spec.height,
            spec.tileset_id,
            tilesets,
            avoid_damage=True,
        )
        # spawn_point가 고립된 소영역에 있으면 맵 중심에서 재탐색 후 폴백
        if len(_reachable_pool) < 5:
            center_x, center_y = spec.width // 2, spec.height // 2
            center_pool = get_reachable_coords(
                tile_data, center_x, center_y, spec.width, spec.height, spec.tileset_id, tilesets
            )
            if len(center_pool) > len(_reachable_pool):
                _reachable_pool = center_pool
                cx, cy = center_x, center_y  # 선택 기준도 중심으로 변경
        if len(_reachable_pool) < 5:
            logger.warning(
                "Map%d _ensure_acquisition: spawn 도달 가능 좌표 부족(%d) → 전체 walkable 사용",
                spec.map_id,
                len(_reachable_pool),
            )
            _reachable_pool = get_all_safe_coords(
                tile_data, spec.width, spec.height, spec.tileset_id, tilesets, avoid_damage=True
            )
            cx, cy = spec.width // 2, spec.height // 2  # 선택 기준도 맵 중심으로

    added: list = []
    offset = 2

    for acq in screenplay.acquisitions:
        if acq.chest_switch in existing_chest_switches:
            continue  # 이미 생성됨

        # quest_switch + quest_type + troop 결정
        troop_for_battle: str | None = None
        if boss_defeated_switch:
            # 보스맵: boss 처치 후 npc 타입 상자
            quest_switch = boss_defeated_switch
            quest_type = "npc"
            q_dialogue = ["보스를 물리쳤군요!", "이 보물을 가져가세요."]
        elif is_battle_map:
            # 던전/필드: {item}_battle_won 독립 스위치 사용
            battle_won_sw = f"{acq.item_name}_battle_won"
            if battle_won_sw in valid_switches and available_troops:
                # 맵에 전투 이벤트가 있으면 → battle 타입 + troop 임베드
                troop_for_battle = available_troops[len(added) % len(available_troops)]
                quest_switch = battle_won_sw
                quest_type = "battle"
                q_dialogue = ["적을 물리쳐야만 이 보물이 열린다."]
            else:
                # troop이 없거나 battle_won 스위치 미할당 → npc 타입 폴백
                quest_switch = (
                    npc_set_switches[len(added)]
                    if len(added) < len(npc_set_switches)
                    else (npc_set_switches[0] if npc_set_switches else None)
                )
                quest_type = "npc"
                q_dialogue = ["이 보물은 내가 지키고 있어.", "도움을 주면 열어줄게."]
                logger.warning(
                    "Map%d('%s') acquisition '%s': battle_won 스위치 미할당 또는 troop 없음 → npc 타입으로 폴백",
                    spec.map_id,
                    spec.name,
                    acq.item_name,
                )
        else:
            # town맵: NPC 대화 후 npc 타입 상자
            quest_switch = (
                npc_set_switches[len(added)]
                if len(added) < len(npc_set_switches)
                else (npc_set_switches[0] if npc_set_switches else None)
            )
            quest_type = "npc"
            q_dialogue = ["이 보물은 내가 지키고 있어.", "도움을 주면 열어줄게."]

        # 좌표 결정: tile_data가 있으면 도달 가능 풀에서 선택, 없으면 spawn 기반 offset
        used_coords = {(getattr(e, "x", -1), getattr(e, "y", -1)) for e in events + added}
        if _reachable_pool:
            # 도달 가능하고 미사용인 좌표 중 spawn에서 가장 가까운 것 선택
            candidates = [c for c in _reachable_pool if c not in used_coords]
            if candidates:
                px, py = min(candidates, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))
                # 다음 번 호출 시 중복 방지를 위해 사용한 좌표 제거
                _reachable_pool = [c for c in _reachable_pool if c != (px, py)]
            else:
                # 도달 가능 풀 소진 → spawn offset 폴백
                px, py = cx + offset, cy
                while (px, py) in used_coords:
                    offset += 1
                    px = cx + offset
        else:
            # tile_data 없음 → 기존 방식
            px, py = cx + offset, cy
            while (px, py) in used_coords:
                offset += 1
                px = cx + offset

        added.append(
            QuestChestEvent(
                type="quest_chest",
                name=f"{acq.item_name}_퀘스트상자",
                x=px,
                y=py,
                quest_type=quest_type,
                quest_switch=quest_switch or f"{acq.item_name}_quest",
                quest_dialogue=q_dialogue,
                troop=troop_for_battle,  # battle 타입: 기존 전투 이벤트 troop 재사용
                item=acq.item_name,
                item_type=acq.item_type,
                chest_switch=acq.chest_switch,
                dialogue_before="빛나는 상자가 나타났다!",
                dialogue_after=f"{acq.item_name}을 손에 넣었다!",
            )
        )
        offset += 2
        logger.warning(
            "Map%d('%s') acquisition '%s' quest_chest 누락 → 자동 삽입 (quest_type=%s, troop=%s, chest_switch=%s)",
            spec.map_id,
            spec.name,
            acq.item_name,
            quest_type,
            troop_for_battle,
            acq.chest_switch,
        )

    return events + added


def _fix_battle_quest_switch_collision(
    events: list,
    map_id: int,
    switch_table: SwitchTable | None = None,
) -> list:
    """battle quest_chest의 quest_switch를 NpcEvent가 ON시키는 충돌을 방지.

    배틀 없이 NPC 대화만으로 quest_switch가 ON되면 battle quest_chest가 활성화되어
    전투 없이 아이템 획득이 가능해지는 버그를 수정한다.

    1차 수정: battle quest_chest.quest_switch가 NPC set_switch와 같으면,
              quest_switch를 {item}_battle_won으로 교체 (switch_table에 존재하는 경우).
    2차 수정: NPC set_switch가 battle quest_switch와 충돌하면 NPC set_switch 제거.
    """
    # battle quest_chest의 quest_switch 목록 수집 (item_name → quest_switch 매핑)
    battle_quest_map: dict[str, str] = {}  # item_name → quest_switch
    for e in events:
        if (
            e.type == "quest_chest"
            and getattr(e, "quest_type", "npc") == "battle"
            and getattr(e, "quest_switch", None)
        ):
            item_name = getattr(e, "item", None) or e.name
            battle_quest_map[item_name] = e.quest_switch

    if not battle_quest_map:
        return events

    # NPC set_switch 집합 수집
    npc_set_switches: set[str] = {
        e.set_switch for e in events if e.type == "npc" and getattr(e, "set_switch", None)
    }

    # 1차: battle quest_chest.quest_switch가 NPC set_switch와 충돌하면 _battle_won으로 교체
    valid_switches = set(switch_table.switches.keys()) if switch_table else set()
    fixed_events = []
    for e in events:
        if (
            e.type == "quest_chest"
            and getattr(e, "quest_type", "npc") == "battle"
            and getattr(e, "quest_switch", None) in npc_set_switches
        ):
            item_name = getattr(e, "item", None) or e.name
            battle_won_sw = f"{item_name}_battle_won"
            if battle_won_sw in valid_switches:
                logger.warning(
                    "Map%d QuestChest '%s': quest_switch '%s'가 NPC set_switch와 충돌 "
                    "→ '%s'로 교체 (독립 배틀 스위치 사용)",
                    map_id,
                    e.name,
                    e.quest_switch,
                    battle_won_sw,
                )
                e = e.model_copy(update={"quest_switch": battle_won_sw})
                battle_quest_map[item_name] = battle_won_sw
            else:
                logger.warning(
                    "Map%d QuestChest '%s': quest_switch '%s' 충돌, '%s' 미할당 → NPC set_switch 제거로 대응",
                    map_id,
                    e.name,
                    e.quest_switch,
                    battle_won_sw,
                )
        fixed_events.append(e)

    # 2차: NPC set_switch가 (업데이트된) battle quest_switch와 여전히 충돌하면 제거
    all_battle_switches = {
        getattr(e, "quest_switch", None)
        for e in fixed_events
        if e.type == "quest_chest" and getattr(e, "quest_type", "npc") == "battle"
    } - {None}

    result = []
    for e in fixed_events:
        if e.type == "npc" and getattr(e, "set_switch", None) in all_battle_switches:
            logger.warning(
                "Map%d NpcEvent '%s': set_switch '%s'가 battle quest_chest의 quest_switch와 충돌 "
                "→ NPC set_switch 제거 (배틀 없이 아이템 획득 방지)",
                map_id,
                e.name,
                e.set_switch,
            )
            e = e.model_copy(update={"set_switch": None})
        result.append(e)
    return result


def _fix_npc_defeated_conditions(
    events: list,
    switch_table: SwitchTable,
    map_id: int,
) -> list:
    """NpcEvent의 condition_switch가 존재하지 않는 _defeated 스위치를 참조할 때 수정.

    LLM이 잘못된 보스 이름의 _defeated 스위치를 condition_switch로 지정하는 경우를 처리.
    - switch_table에 있는 _defeated 스위치 목록에서 가장 적합한 것으로 교체
    - _defeated 스위치가 전혀 없으면 condition_switch/alt_dialogue를 None으로 제거
    """
    valid_switches = switch_table.switches
    # switch_table에 실제 존재하는 _defeated 스위치 목록
    valid_defeated = [sw for sw in valid_switches if sw.endswith("_defeated")]

    fixed = []
    for e in events:
        if (
            e.type == "npc"
            and getattr(e, "condition_switch", None)
            and e.condition_switch.endswith("_defeated")
            and e.condition_switch not in valid_switches
        ):
            if valid_defeated:
                # 존재하지 않는 defeated 스위치 → 실제 존재하는 것으로 교체
                correct = valid_defeated[0]
                logger.warning(
                    "Map%d NpcEvent '%s': condition_switch '%s' 미존재 → '%s'로 교체",
                    map_id,
                    e.name,
                    e.condition_switch,
                    correct,
                )
                e = e.model_copy(update={"condition_switch": correct})
            else:
                # defeated 스위치 자체가 없음 → condition_switch/alt_dialogue 제거
                logger.warning(
                    "Map%d NpcEvent '%s': condition_switch '%s' 미존재, defeated 스위치 없음 → 제거",
                    map_id,
                    e.name,
                    e.condition_switch,
                )
                e = e.model_copy(update={"condition_switch": None, "alt_dialogue": None})
        fixed.append(e)
    return fixed


def _build_move_events(
    screenplay: MapScreenplay | None,
    conn: MapConnectionInfo,
    id_table: IdTable,
    spec: "MapSpec | None" = None,
    map_specs: "list | None" = None,
) -> list:
    """screenplay.moves를 읽어 gate/transfer 이벤트를 코드로 직접 생성한다.

    gate의 condition_switches: LLM 지정값을 사용하지 않고
    이 맵의 acquisitions[].chest_switch 목록으로 코드가 강제 구성한다.
    acquisitions가 없으면 NPC talked_switches를 gate 조건으로 대체 사용.
    (town 맵이거나 조건이 전혀 없으면 조건 없는 transfer로 폴백)
    """
    if not screenplay or not screenplay.moves:
        return []

    # 게이트 조건 = 이 맵 모든 acquisitions의 chest_switch
    chest_switches = [acq.chest_switch for acq in screenplay.acquisitions]
    map_type = spec.map_type if spec else "dungeon"

    # map_name → map_id 역매핑
    name_to_id: dict[str, int] = {name: mid for name, mid in id_table.maps.items()}

    # exit_tiles를 to_map_id → (x, y) 로 인덱싱
    tile_by_dest: dict[int, tuple[int, int]] = {}
    for tile in conn.exit_tiles:
        dest_id = tile.get("to_map_id")
        if dest_id is not None:
            tile_by_dest[dest_id] = (tile.get("x", 1), tile.get("y", 1))

    _fallback_hint = "아직 조건이 충족되지 않았습니다."
    events: list = []

    for move in screenplay.moves:
        dest_id = name_to_id.get(move.to_map_name)
        if dest_id is None:
            logger.warning(
                "_build_move_events: 맵 이름 '%s' id_table에 없음 → 스킵", move.to_map_name
            )
            continue

        tile_xy = tile_by_dest.get(dest_id)
        if tile_xy is None:
            # exit_tile 없음 → 맵 경계 좌표로 폴백 (샘플 맵은 exits=[] 가능)
            if spec:
                fallback_x = spec.width // 2
                fallback_y = spec.height - 2 if move.direction == "forward" else 1
                tile_xy = (fallback_x, fallback_y)
                logger.warning(
                    "_build_move_events: '%s'(id=%d) exit_tile 없음 → 폴백 좌표 (%d, %d) 사용",
                    move.to_map_name,
                    dest_id,
                    fallback_x,
                    fallback_y,
                )
            else:
                logger.warning(
                    "_build_move_events: '%s'(id=%d) exit_tile 없음, spec 없음 → 스킵",
                    move.to_map_name,
                    dest_id,
                )
                continue

        ex, ey = tile_xy

        if move.direction == "forward":
            if not chest_switches:
                # acquisitions가 없을 때: NPC talked_switches를 게이트 조건으로 대체
                npc_talked_switches = (
                    [npc.set_switch for npc in screenplay.npcs if npc.set_switch]
                    if screenplay
                    else []
                )

                if npc_talked_switches and map_type not in {"town"}:
                    # 비 town 맵: NPC 대화 완료를 gate 조건으로 사용
                    gate_switches = npc_talked_switches[:2]  # 최대 2개
                    gate_dialogues = [
                        (
                            move.stage_dialogues[i]
                            if i < len(move.stage_dialogues)
                            else _fallback_hint
                        )
                        for i in range(len(gate_switches))
                    ]
                    logger.info(
                        "_build_move_events: '%s' acquisitions 없음 → NPC talked_switches로 gate 생성 (%s)",
                        move.to_map_name,
                        gate_switches,
                    )
                    events.append(
                        GateEvent(
                            type="gate",
                            name=f"{move.to_map_name}_게이트",
                            x=ex,
                            y=ey,
                            to_map=move.to_map_name,
                            to_x=ex,
                            to_y=1,
                            direction="retain",
                            keeper_character_name="People1",
                            keeper_character_index=6,
                            condition_switches=gate_switches,
                            stage_dialogues=gate_dialogues,
                            gate_character_name="!Crystal",
                            gate_character_index=2,
                        )
                    )
                else:
                    # town 맵이거나 NPC도 없으면 조건 없는 transfer
                    logger.info(
                        "_build_move_events: '%s' acquisitions/NPC 없음 → 조건 없는 transfer 생성",
                        move.to_map_name,
                    )
                    events.append(
                        TransferEvent(
                            type="transfer",
                            name=f"{move.to_map_name}_이동",
                            x=ex,
                            y=ey,
                            to_map=move.to_map_name,
                            to_x=ex,
                            to_y=1,
                            character_name="!Crystal",
                            character_index=2,
                        )
                    )
                continue

            # stage_dialogues 수를 chest_switches 수에 맞게 보정
            n = len(chest_switches)
            dialogues = [
                (move.stage_dialogues[i] if i < len(move.stage_dialogues) else _fallback_hint)
                for i in range(n)
            ]

            events.append(
                GateEvent(
                    type="gate",
                    name=f"{move.to_map_name}_게이트",
                    x=ex,
                    y=ey,
                    to_map=move.to_map_name,
                    to_x=ex,
                    to_y=1,
                    direction="retain",
                    keeper_character_name="People1",
                    keeper_character_index=6,
                    condition_switches=chest_switches,
                    stage_dialogues=dialogues,
                    gate_character_name="!Crystal",
                    gate_character_index=2,
                )
            )

        elif move.direction == "backward":
            # backward 목적지: 이전 맵의 하단(플레이어가 forward로 나간 위치 근처)
            target_spec = None
            if map_specs:
                target_spec = next((s for s in map_specs if s.map_id == dest_id), None)
            to_y_back = (target_spec.height - 2) if target_spec else max(ey, 2)
            to_x_back = (target_spec.width // 2) if target_spec else ex
            events.append(
                TransferEvent(
                    type="transfer",
                    name=f"{move.to_map_name}_귀환",
                    x=ex,
                    y=ey,
                    to_map=move.to_map_name,
                    to_x=to_x_back,
                    to_y=to_y_back,
                    character_name="!Crystal",
                    character_index=4,
                )
            )

    return events
