"""A 노드 — game_designer: 자연어 입력 → GameSpec.

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.A
"""

import logging
from collections import deque
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from agent.generation.models import GameSpec, GuardrailResult
from agent.generation.progress import publish_progress
from agent.generation.prompts.game_designer_prompt import SYSTEM_PROMPT
from agent.generation.prompts.guardrail_prompt import build_guardrail_messages
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7  # 창의적 세계관/스토리 기획
_MAX_MAPS = 6  # 5~10분 게임에 적합


async def game_designer(state: GenerationState) -> dict:
    """A 노드: 사용자 입력 → GameSpec."""
    gen_id = state["generation_id"]
    user_input = state["user_input"]
    options = state.get("options", {})
    playtime_minutes = options.get("playtime_minutes", 7)

    # 1. 가드레일 체크 (부적절한 입력 필터링)
    logger.info("game_designer: 가드레일 체크 시작")
    guardrail_messages = build_guardrail_messages(user_input)
    guardrail_res = cast(
        GuardrailResult,
        await invoke_llm(guardrail_messages, structured_output=GuardrailResult, temperature=0.1),
    )

    if guardrail_res.decision == "unsafe":
        error_msg = f"부적절한 요청으로 생성이 중단되었습니다: {guardrail_res.reason}"
        logger.warning("game_designer: 부적절한 입력 감지 - %s", guardrail_res.reason)
        await publish_progress(
            gen_id,
            {
                "type": "error",
                "phase": "spec",
                "message": error_msg,
            },
        )
        return {
            "is_success": False,
            "final_message": error_msg,
            "error_phase": "spec",
            "error_message": guardrail_res.reason,
        }

    # 2. 본 게임 기획 시작
    # 목표 맵 개수 계산 (5분→3개, 10분→6개, 15분→9개)
    target_n_maps = (playtime_minutes * 3) // 5
    logger.info(
        "game_designer 시작: playtime=%d분, target_n_maps=%d", playtime_minutes, target_n_maps
    )

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "spec",
            "progress": 2,
            "message": f"게임 기획 중... (목표 맵 개수: {target_n_maps}개)",
        },
    )

    # 플레이 시간 및 정확한 맵 개수 지시
    user_input = state["user_input"]
    full_user_prompt = (
        f"목표 플레이 시간: {playtime_minutes}분\n"
        f"요구사항: 반드시 정확히 **{target_n_maps}개**의 맵을 기획하십시오. (부족하거나 넘치지 않게 주의)\n"
        f"설명: {user_input}"
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=full_user_prompt),
    ]

    spec = cast(
        GameSpec, await invoke_llm(messages, structured_output=GameSpec, temperature=_TEMPERATURE)
    )

    # 맵 개수 제한: 5~10분 게임에 적합한 최대 수로 클리핑
    if len(spec.maps) > _MAX_MAPS:
        logger.warning("game_designer: 맵 %d개 → %d개로 잘라냄", len(spec.maps), _MAX_MAPS)
        town = [m for m in spec.maps if m.type == "town"][:1]
        boss = [m for m in spec.maps if m.type == "boss"][:1]
        middle = [m for m in spec.maps if m.type in ("dungeon", "field")][: _MAX_MAPS - 2]
        spec = spec.model_copy(update={"maps": town + middle + boss})
        # connects_to 보정
        map_names = {m.name for m in spec.maps}
        for m in spec.maps:
            m.connects_to = [c for c in m.connects_to if c in map_names]

    _validate_map_connections(spec)

    logger.info("game_designer 완료: title=%s maps=%d", spec.title, len(spec.maps))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "spec",
            "summary": f"{spec.title} — 맵 {len(spec.maps)}개, 캐릭터 {len(spec.characters)}명 기획 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("spec")
    return {"game_spec": spec, "completed_phases": completed}


def _validate_map_connections(spec: GameSpec) -> None:
    """connects_to 양방향 일관성 검사 + BFS 연결성 체크.

    오류 발견 시 경고 로그만 남기고 계속 진행 (LLM 출력이므로 best-effort).
    """
    map_names = {m.name for m in spec.maps}

    # 양방향 체크
    connects_to_set: dict[str, set[str]] = {m.name: set(m.connects_to) for m in spec.maps}
    for m in spec.maps:
        for target in m.connects_to:
            if target not in map_names:
                logger.warning(
                    "game_designer: connects_to 대상 '%s' 미존재 (맵 '%s')", target, m.name
                )
            elif m.name not in connects_to_set.get(target, set()):
                logger.warning(
                    "game_designer: 단방향 연결 — '%s' → '%s' (역방향 없음)", m.name, target
                )

    # BFS 연결성 체크
    if not spec.maps:
        return
    adj: dict[str, list[str]] = {m.name: m.connects_to for m in spec.maps}
    start = spec.maps[0].name
    visited = {start}
    q: deque[str] = deque([start])
    while q:
        cur = q.popleft()
        for nb in adj.get(cur, []):
            if nb in map_names and nb not in visited:
                visited.add(nb)
                q.append(nb)

    isolated = map_names - visited
    if isolated:
        logger.warning("game_designer: 고립된 맵 발견: %s", isolated)
