"""A 노드 — game_designer: 자연어 입력 → GameSpec.

canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.A
"""

import logging
from collections import deque
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from agent.generation.models import GameSpec
from agent.generation.progress import publish_progress
from agent.generation.prompts.game_designer_prompt import SYSTEM_PROMPT
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7  # 창의적 세계관/스토리 기획


async def game_designer(state: GenerationState) -> dict:
    """A 노드: 사용자 입력 → GameSpec."""
    gen_id = state["generation_id"]
    options = state.get("options", {})
    play_time = options.get("play_time", 7)  # 기본값 7분

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "spec",
            "progress": 2,
            "message": f"게임 기획 중... (예상 플레이 시간: {play_time}분)",
        },
    )

    # 플레이 시간 정보를 포함한 사용자 메시지 구성
    user_input = state["user_input"]
    full_user_prompt = f"플레이 시간: {play_time}분\n설명: {user_input}"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=full_user_prompt),
    ]

    spec = cast(
        GameSpec, await invoke_llm(messages, structured_output=GameSpec, temperature=_TEMPERATURE)
    )
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
