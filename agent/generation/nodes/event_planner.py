"""F 노드 — event_planner: 맵별 YAML DSL 생성 (LLM 맵당 1회, 병렬).

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.F
canonical: docs/The_world/prompt_engineering.md §F. 이벤트 기획자
"""

import asyncio
import logging
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
            valid = _validate_coords(events, map_spec)
            valid = _validate_name_refs(valid, id_table, switch_table)
            if valid is not None:
                return _fix_battle_sprites(valid, game_spec, id_table)
        except Exception as e:
            logger.warning("Map%d 이벤트 기획 시도 %d 실패: %s", map_spec.map_id, attempt + 1, e)

    logger.error("Map%d 이벤트 기획 3회 실패 → 폴백 사용", map_spec.map_id)
    return _fallback_events(map_spec, id_table)


def _parse_dsl_safe(raw_yaml: str, map_id: int) -> list | None:
    """YAML 파싱 실패 시 None 반환."""
    try:
        # YAML 코드블록 제거
        text = raw_yaml.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = yaml.safe_load(text)
        if not isinstance(data, dict) or "events" not in data:
            logger.warning("Map%d: YAML에 'events' 키 없음", map_id)
            return None

        events = data["events"] or []
        return [_dsl_event_adapter.validate_python(e) for e in events]
    except (yaml.YAMLError, ValidationError, Exception) as e:
        logger.warning("Map%d DSL 파싱 실패: %s", map_id, e)
        return None


def _validate_coords(events: list, spec: MapSpec) -> list:
    """좌표가 맵 범위를 벗어난 이벤트 제거."""
    valid = []
    for e in events:
        if 0 <= e.x < spec.width and 0 <= e.y < spec.height:
            valid.append(e)
        else:
            logger.warning(
                "Map%d 이벤트 '%s' 좌표 (%d, %d) 범위 초과 → 제거",
                spec.map_id,
                e.name,
                e.x,
                e.y,
            )
    return valid


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


def _fix_battle_sprites(
    events: list,
    game_spec: GameSpec,
    id_table: IdTable,
) -> list:
    """BattleEvent의 map sprite를 enemy tier 기반으로 알고리즘 결정.

    LLM이 임의로 고르는 character_name/character_index 대신
    troop → 적 이름 → tier → 적절한 스프라이트 시트를 코드로 고정한다.

    스프라이트 규칙:
      $ 접두사 파일 (예: $BigMonster1) → 단일 캐릭터, index 항상 0
      일반 파일 (Monster, SF_Monster) → 4×2 그리드, index 0~7
    """
    enemy_tier_map: dict[str, str] = {e.name: e.tier for e in game_spec.enemies}
    theme_lower = game_spec.theme.lower()
    is_sf = any(k in theme_lower for k in _SF_KEYWORDS)

    for event in events:
        if not isinstance(event, BattleEvent):
            continue

        troop_name = event.troop
        if "×" in troop_name:
            enemy_name = troop_name.rsplit("×", 1)[0]
        elif troop_name.endswith("_단독"):
            enemy_name = troop_name[: -len("_단독")]
        else:
            enemy_name = troop_name

        tier = enemy_tier_map.get(enemy_name, "normal")
        troop_id = id_table.troops.get(troop_name, 1)

        if is_sf:
            if tier in ("boss", "elite"):
                event.character_name = "SF_Monster"
                event.character_index = 6 + (troop_id % 2)  # 6 or 7
            else:
                event.character_name = "SF_Monster"
                event.character_index = troop_id % 6  # 0~5
        else:
            if tier == "boss":
                # $BigMonster1 / $BigMonster2 — 단일 캐릭터, index=0 고정
                big_num = 1 + (troop_id % 2)  # 1 or 2
                event.character_name = f"$BigMonster{big_num}"
                event.character_index = 0
            elif tier == "elite":
                event.character_name = "Monster"
                event.character_index = 6 + (troop_id % 2)  # 6 or 7
            else:
                event.character_name = "Monster"
                event.character_index = troop_id % 6  # 0~5

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
