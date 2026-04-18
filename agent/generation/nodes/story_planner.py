"""F 노드 — story_planner: 맵별 대본 + 이벤트 체크리스트 생성 (B 방식).

각 맵에 대해 자연어 대본과 이벤트 체크리스트(MapScreenplay)를 생성한다.
event_planner는 체크리스트를 1:1로 이벤트로 구현한다.
"""

import logging
from typing import cast

from agent.core.llm_client import invoke_llm
from agent.generation.models import (
    GameSpec,
    MapScreenplay,
    MapSpec,
    MoveScript,
    ScreenplayOutput,
)
from agent.generation.progress import publish_progress
from agent.generation.prompts.story_planner_prompt import build_story_planner_prompt
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7

_TYPE_TO_ACT: dict[str, int] = {"town": 0, "field": 1, "dungeon": 1, "boss": 2}

# game_cleared 등 게임 종료 스위치는 NPC set_switch로 사용 금지
_FORBIDDEN_SET_SWITCHES = {"game_cleared", "game_over", "ending_triggered"}


def _is_forbidden_set_switch(sw: str) -> bool:
    """NPC set_switch로 사용 금지된 스위치 판별."""
    if sw in _FORBIDDEN_SET_SWITCHES:
        return True
    # 보스 처치 스위치 (_defeated suffix)는 NPC 대화로 켜면 안 됨
    if sw.endswith("_defeated"):
        return True
    return False


def _align_map_types_with_game_spec(map_specs: list[MapSpec], game_spec: GameSpec) -> list[MapSpec]:
    """game_spec.maps 순서에 맞춰 map_type을 town/dungeon으로 보정한다.

    - game_spec의 type이 town/dungeon 외의 값(boss, field 등 레거시)이면 dungeon으로 정규화
    - 첫 번째 맵(map_id 최솟값)은 반드시 town
    - 나머지는 dungeon (마지막 맵이 보스 구역이 됨)
    """
    sorted_specs = sorted(map_specs, key=lambda s: s.map_id)
    corrected: list[MapSpec] = []
    for i, ms in enumerate(sorted_specs):
        if i < len(game_spec.maps):
            raw_type = game_spec.maps[i].type
            # town/dungeon 외는 dungeon으로 정규화
            game_type = raw_type if raw_type in {"town", "dungeon"} else "dungeon"
        else:
            game_type = "dungeon"
        # 첫 번째 맵은 항상 town, 마지막 맵은 항상 boss
        if i == 0:
            game_type = "town"
        elif i == len(sorted_specs) - 1:
            game_type = "boss"
        if ms.map_type != game_type:
            logger.info(
                "_align_map_types: map_id=%d '%s' 타입 보정 %s → %s",
                ms.map_id,
                ms.name,
                ms.map_type,
                game_type,
            )
            ms = ms.model_copy(update={"map_type": game_type})
        corrected.append(ms)
    return corrected


async def story_planner(state: GenerationState) -> dict:
    """F 노드: GameSpec + MapSpec → 맵별 MapScreenplay."""
    gen_id = state["generation_id"]
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]

    # game_spec.maps 순서에 맞춰 map_type 보정 (샘플 맵 선택기는 boss/field 구분 못함)
    map_specs = _align_map_types_with_game_spec(map_specs, game_spec)

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "story_plan",
            "progress": 62,
            "message": "스토리 대본 작성 중...",
        },
    )

    story_script: dict[int, MapScreenplay] = {}
    try:
        messages = build_story_planner_prompt(game_spec, map_specs, id_table, switch_table)
        result = cast(
            ScreenplayOutput,
            await invoke_llm(
                messages, structured_output=ScreenplayOutput, temperature=_TEMPERATURE
            ),
        )
        story_script = _validate_screenplay(result, id_table, switch_table, map_specs)
    except Exception as e:
        logger.error("story_planner LLM 실패, 폴백 사용: %s", e)
        story_script = _fallback_screenplay(map_specs)

    # LLM이 일부 맵을 누락한 경우 폴백으로 보완
    last_map_id = max((s.map_id for s in map_specs), default=-1)
    for spec in map_specs:
        if spec.map_id not in story_script:
            logger.warning("story_planner: map_id=%d 누락 → 폴백", spec.map_id)
            story_script[spec.map_id] = _fallback_single_map(
                spec, is_last=(spec.map_id == last_map_id)
            )

    logger.info("story_planner 완료: %d개 맵 대본", len(story_script))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "story_plan",
            "summary": f"{len(story_script)}개 맵 대본 완성",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("story_plan")
    return {"story_script": story_script, "map_specs": map_specs, "completed_phases": completed}


def _validate_screenplay(
    result: ScreenplayOutput,
    id_table: IdTable,
    switch_table: SwitchTable,
    map_specs: list[MapSpec],
) -> dict[int, MapScreenplay]:
    """LLM 출력 검증."""
    actor_names = set(id_table.actors.keys())
    valid_switches = set(switch_table.switches.keys())
    map_id_set = {s.map_id for s in map_specs}
    map_id_to_type = {s.map_id: s.map_type for s in map_specs}
    map_id_to_name = {s.map_id: s.name for s in map_specs}
    out: dict[int, MapScreenplay] = {}

    for ms in result.maps:
        if ms.map_id not in map_id_set:
            logger.warning("story_planner: 알 수 없는 map_id=%d → 스킵", ms.map_id)
            continue

        map_type = map_id_to_type.get(ms.map_id, "dungeon")  # noqa : F841

        # ── NPC 검증 ──────────────────────────────────────────────────────────
        fixed_npcs = []
        for npc in ms.npcs:
            # 이름이 주인공과 충돌
            if npc.name in actor_names:
                fallback = npc.role.strip() or "안내인"
                if fallback in actor_names:
                    fallback = f"{fallback}NPC"
                logger.warning(
                    "story_planner: NPC '%s' 주인공 이름 충돌 → '%s'로 변경",
                    npc.name,
                    fallback,
                )
                npc = npc.model_copy(update={"name": fallback})

            # set_switch 검증: 금지된 스위치이거나 스위치 목록에 없으면 None으로 초기화
            if npc.set_switch:
                sw = npc.set_switch
                from agent.generation.registry.switch_table import normalize_switch_name

                norm_sw = normalize_switch_name(sw)
                if _is_forbidden_set_switch(norm_sw):
                    logger.warning(
                        "story_planner: NPC '%s' set_switch '%s' 금지 스위치 → None으로 초기화",
                        npc.name,
                        sw,
                    )
                    npc = npc.model_copy(update={"set_switch": None})
                elif norm_sw not in valid_switches:
                    logger.warning(
                        "story_planner: NPC '%s' set_switch '%s' 스위치 목록 없음 → None",
                        npc.name,
                        sw,
                    )
                    npc = npc.model_copy(update={"set_switch": None})
                else:
                    npc = npc.model_copy(update={"set_switch": norm_sw})

            fixed_npcs.append(npc)

        # ── 아이템 획득 검증 ──────────────────────────────────────────────────
        all_items = (
            set(id_table.items.keys()) | set(id_table.weapons.keys()) | set(id_table.armors.keys())
        )
        fixed_acq = []
        for acq in ms.acquisitions:
            if acq.item_name not in all_items:
                logger.warning(
                    "story_planner: map_id=%d 아이템 '%s' 목록에 없음 → 스킵",
                    ms.map_id,
                    acq.item_name,
                )
                continue

            from agent.generation.registry.switch_table import normalize_switch_name

            norm_chest_sw = normalize_switch_name(acq.chest_switch)
            if norm_chest_sw not in valid_switches:
                logger.warning(
                    "story_planner: map_id=%d chest_switch '%s' 스위치 목록 없음 → 스킵",
                    ms.map_id,
                    acq.chest_switch,
                )
                continue

            acq = acq.model_copy(update={"chest_switch": norm_chest_sw})

            # item_type 자동 보정: LLM이 잘못된 카테고리를 지정하는 경우 수정
            correct_type = (
                "item"
                if acq.item_name in id_table.items
                else "weapon"
                if acq.item_name in id_table.weapons
                else "armor"
            )
            if acq.item_type != correct_type:
                logger.warning(
                    "story_planner: map_id=%d acquisition '%s' item_type '%s'→'%s' 자동 보정",
                    ms.map_id,
                    acq.item_name,
                    acq.item_type,
                    correct_type,
                )
                acq = acq.model_copy(update={"item_type": correct_type})
            fixed_acq.append(acq)

        # ── 이동 검증 ─────────────────────────────────────────────────────────
        # 마지막 맵(보스 구역)은 moves 비워야 함
        sorted_map_ids = sorted(s.map_id for s in map_specs)
        is_last_map = bool(sorted_map_ids) and ms.map_id == sorted_map_ids[-1]

        if is_last_map and ms.moves:
            logger.warning("story_planner: 마지막 맵(map_id=%d) moves 존재 → 제거", ms.map_id)
            ms = ms.model_copy(update={"moves": []})

        # forward 최대 1개, backward 최대 1개
        fixed_moves: list[MoveScript] = []
        forward_count = 0
        backward_count = 0

        spec_obj = next((s for s in map_specs if s.map_id == ms.map_id), None)

        # 이 맵의 sequential 인덱스 (map_id 오름차순, 위에서 이미 계산됨)
        cur_idx = sorted_map_ids.index(ms.map_id) if ms.map_id in sorted_map_ids else -1

        # 이 맵에서 이동 가능한 목적지: spec.exits 우선, 없거나 유효한 맵이 없으면 순서 기반
        # 주의: 샘플 맵 exits는 원본 DB ID를 가리키므로 현재 game map_id와 불일치할 수 있음
        valid_exit_names: set[str] = set()
        if spec_obj and spec_obj.exits:
            for ex in spec_obj.exits:
                dest_name = map_id_to_name.get(ex.to_map_id)
                if dest_name:
                    valid_exit_names.add(dest_name)
        # exits가 있어도 유효한 목적지가 없으면(원본 DB ID 불일치) 순서 기반으로 폴백
        if not valid_exit_names and cur_idx >= 0:
            if cur_idx > 0:
                prev_name = map_id_to_name.get(sorted_map_ids[cur_idx - 1])
                if prev_name:
                    valid_exit_names.add(prev_name)
            if cur_idx < len(sorted_map_ids) - 1:
                next_name = map_id_to_name.get(sorted_map_ids[cur_idx + 1])
                if next_name:
                    valid_exit_names.add(next_name)

        _fallback_hint = "아직 조건이 충족되지 않았습니다."
        n_acquisitions = len(fixed_acq)  # stage_dialogues 기준 = acquisitions 수
        for move in ms.moves:
            # move 목적지가 연결 가능한 맵에 없으면 제거
            if move.to_map_name not in valid_exit_names:
                logger.warning(
                    "story_planner: map_id=%d move to='%s' 유효한 연결 맵 아님 → 제거",
                    ms.map_id,
                    move.to_map_name,
                )
                continue

            if move.direction == "forward":
                if forward_count >= 1:
                    logger.warning("story_planner: map_id=%d forward move 중복 → 제거", ms.map_id)
                    continue
                # stage_dialogues 수를 acquisitions 수에 맞게 조정
                dialogues = [
                    (move.stage_dialogues[i] if i < len(move.stage_dialogues) else _fallback_hint)
                    for i in range(n_acquisitions)
                ]
                move = move.model_copy(update={"stage_dialogues": dialogues})
                fixed_moves.append(move)
                forward_count += 1
            elif move.direction == "backward":
                if backward_count >= 1:
                    logger.warning("story_planner: map_id=%d backward move 중복 → 제거", ms.map_id)
                    continue
                fixed_moves.append(move)
                backward_count += 1

        # ── forward move 누락 보완 ─────────────────────────────────────────────
        # 마지막 맵이 아닌데 forward move가 없으면 순서 기반으로 자동 삽입
        if not is_last_map and forward_count == 0 and cur_idx >= 0:
            if cur_idx < len(sorted_map_ids) - 1:
                next_id = sorted_map_ids[cur_idx + 1]
                dest_name = map_id_to_name.get(next_id)
                if dest_name:
                    fallback_dialogues = [_fallback_hint] * n_acquisitions
                    fallback_move = MoveScript(
                        direction="forward",
                        to_map_name=dest_name,
                        stage_dialogues=fallback_dialogues,
                    )
                    fixed_moves.append(fallback_move)
                    logger.warning(
                        "story_planner: map_id=%d forward move 누락 → '%s'으로 폴백 삽입",
                        ms.map_id,
                        dest_name,
                    )

        # ── backward move 누락 보완 ────────────────────────────────────────────
        # 첫 번째 맵이 아닌데 backward move가 없으면 이전 맵으로 자동 삽입
        if cur_idx > 0 and backward_count == 0:
            prev_id = sorted_map_ids[cur_idx - 1]
            prev_name = map_id_to_name.get(prev_id)
            if prev_name:
                fallback_backward = MoveScript(
                    direction="backward",
                    to_map_name=prev_name,
                    stage_dialogues=[],
                )
                fixed_moves.append(fallback_backward)
                logger.info(
                    "story_planner: map_id=%d backward move 누락 → '%s'으로 자동 삽입",
                    ms.map_id,
                    prev_name,
                )

        # has_boss는 마지막 맵만 True로 강제 — LLM 응답 무관하게 보장
        out[ms.map_id] = ms.model_copy(
            update={
                "npcs": fixed_npcs,
                "acquisitions": fixed_acq,
                "moves": fixed_moves,
                "has_boss": is_last_map,
            }
        )

    return out


def _fallback_screenplay(map_specs: list[MapSpec]) -> dict[int, MapScreenplay]:
    last_map_id = max((s.map_id for s in map_specs), default=-1)
    return {
        spec.map_id: _fallback_single_map(spec, is_last=(spec.map_id == last_map_id))
        for spec in map_specs
    }


def _fallback_single_map(spec: MapSpec, is_last: bool = False) -> MapScreenplay:
    return MapScreenplay(
        map_id=spec.map_id,
        narrative=f"{spec.name}에서의 여정이 시작된다.",
        npcs=[],
        acquisitions=[],
        moves=[],
        has_boss=is_last,
    )
