"""Planner 노드 — 3단계: 수정 시나리오 계획 수립.

담당: 화진님
"""

import logging

from agent.core.llm_client import invoke_llm  # noqa: F401
from agent.graph.state import AgentState
from agent.prompts.planner_prompt import build_prompt  # noqa: F401

logger = logging.getLogger(__name__)


async def planner(state: AgentState) -> dict:
    # TODO: 구현 필요
    raise NotImplementedError
