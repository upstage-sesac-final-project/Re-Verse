"""LLM 재랭킹.

룰 필터가 뽑은 후보 20~30개의 압축 표현을 LLM에 넘기고, MapIntent에 가장
어울리는 N개의 file_name을 받아온다.
"""

import logging
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.generation.mapgen.intent.schema import MapIntent
from agent.generation.mapgen.sample_selector.filter import ScoredEntry

logger = logging.getLogger(__name__)


class RankedMaps(BaseModel):
    """LLM 재랭킹 결과."""

    file_names: list[str] = Field(
        description="선택된 맵의 file_name 리스트. 적합도 순서로 정렬.",
    )
    reasoning: str = Field(
        default="",
        description="간단한 선택 이유 (한국어, 1~2문장).",
    )


_SYSTEM_PROMPT = """당신은 RPG 맵 큐레이터입니다.
사용자의 게임 의도(MapIntent)와 후보 맵 목록을 받아, 가장 어울리는 N개를 골라 file_name으로 반환합니다.

선택 원칙:
- 사용자의 era/biome/structures/mood와 의미적으로 잘 맞는 맵을 우선합니다.
- **연결성(Connectivity)**: 후보 중에 서로 이어지는 맵(exits 정보 참고)이 있다면, 이를 하나의 세트로 선택하는 것을 매우 선호합니다. (예: 숲 입구 -> 숲 내부 -> 숲 보스방)
- 가능하면 **다양한 tileset_id가 포함**되도록 골라 게임에 변화를 줍니다.
- 동일하거나 매우 비슷한 맵을 중복 선택하지 마세요.
- 정확히 요청된 N개의 file_name만 반환합니다.
- file_name은 후보 목록에 있는 것 중에서만 선택하세요. 임의로 만들지 마세요."""


def _format_candidate(scored: ScoredEntry) -> str:
    e = scored["entry"]
    tags = ",".join(e["tags"])
    exits = []
    for ex in e.get("exits", []):
        if ex.get("leads_to_name") != "Unknown":
            exits.append(f"{ex['direction']}→{ex['leads_to_name']}({ex['leads_to_id']})")
    exit_str = " | exits: " + ", ".join(exits) if exits else ""
    return (
        f"{e['file_name']} | ts{e['tileset_id']} | {e['display_name']} "
        f"({e['width']}x{e['height']}) | [{tags}] | {e['description']}{exit_str}"
    )


def _format_intent(intent: MapIntent) -> str:
    return (
        f"era={intent.era}, scale={intent.scale}, n_maps={intent.n_maps}\n"
        f"biome={intent.biome}\n"
        f"structures={intent.structures}\n"
        f"mood={intent.mood}\n"
        f"raw_keywords={intent.raw_keywords}"
    )


async def llm_rerank(
    intent: MapIntent,
    candidates: list[ScoredEntry],
) -> list[str]:
    """후보 중에서 intent.n_maps개를 골라 file_name 리스트를 반환."""
    if not candidates:
        return []

    candidate_block = "\n".join(_format_candidate(c) for c in candidates)
    user_msg = (
        f"사용자 의도:\n{_format_intent(intent)}\n\n"
        f"후보 맵 ({len(candidates)}개):\n{candidate_block}\n\n"
        f"위 후보 중 정확히 {intent.n_maps}개를 골라 RankedMaps 형식으로 반환하세요."
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    valid_names = {c["entry"]["file_name"] for c in candidates}

    try:
        result = await invoke_llm(messages, structured_output=RankedMaps, temperature=0.0)
        ranked = cast(RankedMaps, result)
        chosen = [n for n in ranked.file_names if n in valid_names][: intent.n_maps]
        if ranked.reasoning:
            logger.info("재랭킹 사유: %s", ranked.reasoning)
        if len(chosen) < intent.n_maps:
            # LLM이 부족하게 골랐거나 잘못된 이름을 냈으면 룰 점수 상위로 보충
            for c in candidates:
                fn = c["entry"]["file_name"]
                if fn not in chosen:
                    chosen.append(fn)
                if len(chosen) >= intent.n_maps:
                    break
        return chosen
    except Exception:
        logger.exception("LLM 재랭킹 실패, 룰 점수 상위로 fallback")
        return [c["entry"]["file_name"] for c in candidates[: intent.n_maps]]
