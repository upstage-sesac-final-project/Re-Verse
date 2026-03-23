"""Synthesizer 노드 — 6단계: 사용자 친화적 최종 응답 생성.

담당: 세종님
"""

import logging

from agent.core.llm_client import invoke_llm  # noqa: F401
from agent.graph.state import AgentState
from agent.prompts.synthesizer_prompt import build_prompt  # noqa: F401

logger = logging.getLogger(__name__)


async def synthesizer(state: AgentState) -> dict:
    # TODO: 구현 필요
    raise NotImplementedError
