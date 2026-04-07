"""GameDesigner 노드 — 1차 LLM: user_prompt → WorldSpec."""

import logging

from agent.core.llm_client import invoke_llm_json
from agent.generation.prompts.game_designer_prompt import build_game_designer_prompt
from agent.generation.schemas.world_spec import WorldSpec
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)


async def game_designer(state: GenerationState) -> dict:
    """사용자 prompt → WorldSpec 전체 생성."""
    prompt = state["user_prompt"]
    logger.info("[GameDesigner] 시작: prompt='%s'", prompt[:80])

    messages = build_game_designer_prompt(prompt)
    world_spec: WorldSpec = await invoke_llm_json(messages, WorldSpec, timeout=120.0)  # type: ignore

    logger.info(
        "[GameDesigner] 완료: title='%s', party=%d명, enemies=%d마리, maps=%d개",
        world_spec.game_title,
        len(world_spec.party),
        len(world_spec.enemies),
        len(world_spec.maps),
    )

    summary = _build_summary(world_spec)

    return {
        "world_spec": world_spec.model_dump(),
        "world_summary": summary,
    }


def _build_summary(spec: WorldSpec) -> str:
    party_str = ", ".join(f"{m.name}({m.class_name})" for m in spec.party)
    bosses = [e.name for e in spec.enemies if e.tier == "boss"]
    boss_str = ", ".join(bosses) if bosses else "없음"
    maps_str = ", ".join(m.name for m in spec.maps)
    difficulty_map = {"easy": "쉬움", "normal": "보통", "hard": "어려움"}
    return (
        f"게임을 생성했습니다!\n"
        f"- 제목: {spec.game_title}\n"
        f"- 세계관: {spec.theme}\n"
        f"- 스토리: {spec.story_synopsis}\n"
        f"- 파티: {party_str}\n"
        f"- 보스: {boss_str}\n"
        f"- 맵: {maps_str}\n"
        f"- 난이도: {difficulty_map.get(spec.difficulty, spec.difficulty)}"
    )
