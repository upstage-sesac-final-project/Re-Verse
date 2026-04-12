"""F 노드 — event_planner: 맵별 YAML DSL 생성 (LLM 맵당 1회, 병렬).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.F
canonical: docs/The_world/prompt_engineering.md §F. 이벤트 기획자
"""

import asyncio
import logging
import random
import re
from typing import cast

import yaml
from pydantic import TypeAdapter, ValidationError

from agent.core.llm_client import invoke_llm
from agent.generation.compilers.dsl_models import (
    BattleEvent,
    DslEvent,
    NpcEvent,
    TransferEvent,
)
from agent.generation.mapgen.tile_checker import (
    get_all_safe_coords,
    get_reachable_coords,
)
from agent.generation.models import GameSpec, MapConnectionInfo, MapSpec
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

    tasks = [
        _plan_single_map(
            map_spec=spec,
            game_spec=game_spec,
            id_table=id_table,
            switch_table=switch_table,
            connection_info=connection_info.get(spec.map_id, _empty_connection(spec.map_id)),
            troop_to_sprite=troop_to_sprite,
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
    tile_data: list[int] | None = None,
    tilesets: list | None = None,
) -> list:
    rag_context = get_event_planner_context(map_spec.map_type)
    for attempt in range(3):
        try:
            prompt = build_event_planner_prompt(
                map_spec, game_spec, id_table, switch_table, connection_info, rag_context
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

            valid = _validate_name_refs(valid, id_table, switch_table)
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

        # 2. 안전하지 않다면 보정 시도
        if not is_in_bounds or not is_safe:
            from agent.generation.mapgen.tile_checker import find_nearest_safe_coord

            # 1순위: 원래 좌표 근처에서 가장 가까운 안전한 좌표 찾기 (BFS)
            nx, ny = find_nearest_safe_coord(
                tile_data,
                e.x if is_in_bounds else spec.width // 2,
                e.y if is_in_bounds else spec.height // 2,
                spec.width,
                spec.height,
                spec.tileset_id,
                tilesets,
                max_radius=15,
                used_coords=used_coords,
            )

            # BFS로 찾은 좌표가 안전하고 '도달 가능'한지 최종 확인
            is_valid_new = is_walkable(
                tile_data, nx, ny, spec.width, spec.height, spec.tileset_id, tilesets
            )
            if is_valid_new and all_safe_coords and (nx, ny) not in all_safe_coords:
                # BFS로 찾은 곳조차 도달 불가능하다면, 도달 가능 리스트에서 랜덤하게 하나 뽑기
                if all_safe_coords:
                    nx, ny = random.choice(all_safe_coords)
                else:
                    is_valid_new = False

            if is_valid_new and (nx, ny) != (e.x, e.y):
                logger.info(
                    "Map%d 이벤트 '%s' 좌표 근처/도달 보정: (%d, %d) -> (%d, %d)",
                    spec.map_id,
                    e.name,
                    e.x,
                    e.y,
                    nx,
                    ny,
                )
                e.x, e.y = nx, ny
                used_coords.add((nx, ny))
                valid.append(e)
                if (nx, ny) in all_safe_coords:
                    all_safe_coords.remove((nx, ny))
                continue

            # 2순위: 근처에도 없다면 랜덤 배정
            if all_safe_coords:
                nx, ny = random.choice(all_safe_coords)
                all_safe_coords.remove((nx, ny))
                logger.info(
                    "Map%d 이벤트 '%s' 좌표 랜덤 재배정 (도달 가능 지역): (%d, %d) -> (%d, %d)",
                    spec.map_id,
                    e.name,
                    e.x,
                    e.y,
                    nx,
                    ny,
                )
                e.x, e.y = nx, ny
                used_coords.add((nx, ny))
                valid.append(e)
            else:
                logger.warning(
                    "Map%d 이벤트 '%s': 도달 가능한 안전 좌표가 없음 → 제거", spec.map_id, e.name
                )
        else:
            # 원래 좌표가 안전하면 그대로 사용
            used_coords.add((e.x, e.y))
            if (e.x, e.y) in all_safe_coords:
                all_safe_coords.remove((e.x, e.y))
            valid.append(e)

    return valid


def _correct_troop_name(raw: str, all_troop_names: set[str]) -> str | None:
    # ... (생략 없이 유지)
    normalized = re.sub(r"[\s_]+×", "×", raw)
    if normalized in all_troop_names:
        return normalized
    base = normalized
    candidate = f"{base}_단독"
    if candidate in all_troop_names:
        return candidate
    candidate = f"{base}×1"
    if candidate in all_troop_names:
        return candidate
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
            if hasattr(e, "troop") and e.troop not in all_troop_names:
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


def _empty_connection(map_id: int) -> MapConnectionInfo:
    return MapConnectionInfo(map_id=map_id, exit_tiles=[], entry_tiles=[])
