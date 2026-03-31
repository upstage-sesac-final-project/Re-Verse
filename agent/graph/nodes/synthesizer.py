"""Synthesizer 노드 — 6단계: 사용자 친화적 최종 응답 생성.

담당: 세종님
"""

import logging

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.synthesizer_prompt import build_prompt

logger = logging.getLogger(__name__)


async def synthesizer(state: AgentState) -> dict:
    passed = state.get("success", True)

    logger.info(
        "Synthesizer 시작: intent=%s, passed=%s",
        state.get("intent"),
        passed,
    )

    messages = build_prompt(state)
    response: str = await invoke_llm(messages)  # type: ignore[assignment]

    logger.info("Synthesizer 완료: response_len=%d", len(response))
    return {"final_response": response}
