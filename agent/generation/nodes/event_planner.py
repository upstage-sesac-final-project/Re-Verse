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
    NpcEvent,
    TransferEvent,
)
from agent.generation.mapgen.tile_checker import find_nearest_safe_coord
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
    tilesets: list | None = generated_assets.get("Tilesets.json")

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
    """좌표가 맵 범위를 벗어난 이벤트 제거, 통행 불가 타일 보정 및 중복 배치 방지."""
    valid = []
    # 1. 이미 사용 중인 좌표 집합 (입구, 출구 좌표 포함)
    used_coords: set[tuple[int, int]] = set()

    if connection_info:
        for et in connection_info.entry_tiles:
            used_coords.add((et["x"], et["y"]))
        for xt in connection_info.exit_tiles:
            used_coords.add((xt["x"], xt["y"]))

    for e in events:
        # 1. 맵 범위 체크
        if not (0 <= e.x < spec.width and 0 <= e.y < spec.height):
            logger.warning(
                "Map%d 이벤트 '%s' 좌표 (%d, %d) 범위 초과 → 제거",
                spec.map_id,
                e.name,
                e.x,
                e.y,
            )
            continue

        # 2. 통행 가능 여부 및 중복 체크하여 보정
        if tile_data:
            nx, ny = find_nearest_safe_coord(
                tile_data,
                e.x,
                e.y,
                spec.width,
                spec.height,
                spec.tileset_id,
                tilesets,
                used_coords=used_coords,
            )

            if (nx, ny) != (e.x, e.y):
                logger.info(
                    "Map%d 이벤트 '%s' 좌표 보정: (%d, %d) -> (%d, %d)",
                    spec.map_id,
                    e.name,
                    e.x,
                    e.y,
                    nx,
                    ny,
                )
                e.x, e.y = nx, ny

            # 보정된 좌표가 여전히 차단되어 있거나 중복이면 제거 (최후의 수단)
            if (nx, ny) in used_coords:
                logger.warning("Map%d 이벤트 '%s': 빈 좌표를 찾지 못함 → 제거", spec.map_id, e.name)
                continue

            used_coords.add((e.x, e.y))

        valid.append(e)
    return valid


def _correct_troop_name(raw: str, all_troop_names: set[str]) -> str | None:
    """LLM이 suffix를 생략하거나 잘못 붙인 troop 이름을 자동 보정한다.

    보정 순서:
      1. × 앞 공백/언더스코어 제거 ("이름 ×2" → "이름×2")
      2. _단독 suffix 추가 ("이름" → "이름_단독")
      3. ×1 suffix 추가 ("이름" → "이름×1")
      4. 접두 부분 매칭 (all_troop_names 중 raw로 시작하는 첫 번째)
    """
    # 1. × 앞 공백/underscore 정규화
    normalized = re.sub(r"[\s_]+×", "×", raw)
    if normalized in all_troop_names:
        return normalized

    base = normalized  # 이후 suffix 시도는 정규화된 이름 기준

    # 2. _단독 suffix
    candidate = f"{base}_단독"
    if candidate in all_troop_names:
        return candidate

    # 3. ×1 suffix
    candidate = f"{base}×1"
    if candidate in all_troop_names:
        return candidate

    # 4. 접두 부분 매칭 (정렬해서 가장 짧은 것 우선)
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
    """id_table.troops의 모든 troop_name에 대해 (character_name, character_index)를 사전 결정.

    id_table.troops는 spec 기준 exact key이므로 런타임 문자열 파싱 없이 바로 사용 가능.
    우선순위:
      0순위: battlerName fallback 적 → Nature/1
      1순위: battlerName → _BATTLER_TO_MAP_SPRITE 직접 조회
      2순위: tier 기반 폴백
    """
    # Enemies.json에서 enemy_id → battlerName 구성
    enemies_json: list = generated_assets.get("Enemies.json") or []
    enemy_id_to_battler: dict[int, str] = {
        e["id"]: e["battlerName"]
        for e in enemies_json
        if e and isinstance(e, dict) and e.get("id") and e.get("battlerName")
    }
    # fallback 처리된 적 ID (note에 "(fallback)" 포함)
    fallback_enemy_ids: set[int] = {
        e["id"]
        for e in enemies_json
        if e and isinstance(e, dict) and e.get("id") and "(fallback)" in (e.get("note") or "")
    }

    # spec_enemy_name → battlerName / tier
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
        # troop_name에서 spec enemy name 추출 (id_table 기준이므로 항상 정확)
        if "×" in troop_name:
            spec_name = troop_name.rsplit("×", 1)[0]
        elif troop_name.endswith("_단독"):
            spec_name = troop_name[: -len("_단독")]
        else:
            spec_name = troop_name

        # 0순위: fallback → Nature/1
        if spec_name in fallback_enemy_names:
            result[troop_name] = ("Nature", 1)
            continue

        # 1순위: battlerName 테이블 조회
        battler_name = battler_map.get(spec_name)
        if battler_name and battler_name in _BATTLER_TO_MAP_SPRITE:
            result[troop_name] = _BATTLER_TO_MAP_SPRITE[battler_name]
            continue

        # 2순위: tier 기반 폴백
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


# battlerName → (character_name, character_index)
# 직접 이미지 확인 기반 시각적 매핑 테이블
# characters/Monster.png 레이아웃:  0=파란피부언데드여, 1=초록몬스터, 2=은회색늑대인간, 3=검은번개갑옷,
#                                   4=흰여우구미호, 5=검은뿔소악마, 6=금관좀비보스, 7=보라악마날개보스
# characters/Evil.png 레이아웃:     0=초록두건고글불량배, 1=갈색안경학자악당, 2=흰은발여성마법사,
#                                   3=황금가면마왕, 6=황금갑옷기사, 7=갈색로브흑막
# characters/$BigMonster1.png:      4캐릭터×3프레임, 3개씩 묶음
#   0~2=보라마왕마법사, 3~5=초록나무괴물, 6~8=보라곤충두족류(크라켄), 9~11=다머리초록용(히드라)
# characters/$BigMonster2.png:      4캐릭터×3프레임, 3개씩 묶음
#   0~2=붉은드래곤, 3~5=황금천마기사, 6~8=보라촉수여신(이블갓), 9~11=붉은변이악마
# characters/SF_Monster.png 레이아웃: 0=흰정장마피아, 1=검은군복요원, 2=검은그림자빨간눈,
#                                     3=빨간광대, 4=파란메카로봇, 5=검은육중전투로봇,
#                                     6=보라리치, 7=붉은도깨비장군
_BATTLER_TO_MAP_SPRITE: dict[str, tuple[str, int]] = {
    # ── 판타지: Monster 시트 ────────────────────────────────────────────
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
    # ── 판타지: Evil 시트 ───────────────────────────────────────────────
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
    # ── 판타지: $BigMonster1 (대형, 4캐릭터×3프레임 — 3개씩 묶음) ──────────
    # index 0~2:  보라 마왕형 마법사
    "Lich": ("$BigMonster1", 0),
    "Goddess_of_death": ("$BigMonster1", 0),
    # index 3~5:  초록 나무 괴물
    "Treant": ("$BigMonster1", 3),
    # index 6~8:  보라 곤충/두족류 (크라켄형)
    "Kraken": ("$BigMonster1", 6),
    "Ketos": ("$BigMonster1", 6),
    # index 9~11: 다머리 초록 용 (히드라형)
    "Hydra": ("$BigMonster1", 9),
    # ── 판타지: $BigMonster2 (대형, 4캐릭터×3프레임 — 3개씩 묶음) ──────────
    # index 0~2:  붉은 드래곤
    "Dragon": ("$BigMonster2", 0),
    "Demon": ("$BigMonster2", 0),
    # index 3~5:  황금+날개 천마 기사
    "God_of_light": ("$BigMonster2", 3),
    "Goddess": ("$BigMonster2", 3),
    # index 6~8:  보라+촉수 여신형
    "Evilgod": ("$BigMonster2", 6),
    # index 9~11: 붉은 변이 악마 (최종 보스)
    "Demon_metamorphosis": ("$BigMonster2", 9),
    # ── SF: SF_Monster 시트 ─────────────────────────────────────────────
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


def _fix_battle_sprites(
    events: list,
    troop_to_sprite: dict[str, tuple[str, int]],
) -> list:
    """BattleEvent의 map sprite를 사전 구성된 troop_to_sprite 테이블로 결정."""
    for event in events:
        if not isinstance(event, BattleEvent):
            continue
        sprite = troop_to_sprite.get(event.troop)
        if sprite:
            event.character_name, event.character_index = sprite
        else:
            logger.warning("troop '%s' sprite 매핑 없음 → 기본값 유지", event.troop)
    return events


def _fallback_events(spec: MapSpec, id_table: IdTable) -> list:
    """파싱/기획 완전 실패 시 최소 이벤트 목록 (전이만)."""
    events: list = []
    cx = spec.width // 2
    cy = spec.height // 2

    # 맵 연결 transfer 이벤트 (spec.exits 기반)
    for exit_spec in spec.exits:
        if exit_spec.to_map_id in {v for v in id_table.maps.values()}:
            to_name = next(
                (name for name, mid in id_table.maps.items() if mid == exit_spec.to_map_id),
                None,
            )
            if to_name:
                direction_coords = {
                    "north": (cx, 1),
                    "south": (cx, spec.height - 2),
                    "east": (spec.width - 2, cy),
                    "west": (1, cy),
                }
                ex, ey = direction_coords.get(exit_spec.direction, (cx, cy))
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

    # 마을이면 최소 NPC 1개 추가
    if spec.map_type == "town":
        events.append(
            NpcEvent(
                type="npc",
                name="마을주민",
                x=cx + 2,
                y=cy,
                dialogue=["..."],
            )
        )

    return events


def _empty_connection(map_id: int) -> MapConnectionInfo:
    return MapConnectionInfo(map_id=map_id, exit_tiles=[], entry_tiles=[])
