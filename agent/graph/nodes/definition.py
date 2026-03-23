"""Definition 노드 — 2단계: RAG(?) 조회 + 게임 JSON에서 ID 매핑.

담당: 정민님
"""

import logging

from agent.core.llm_client import invoke_llm  # noqa: F401
from agent.graph.state import AgentState
from agent.prompts.definition_prompt import build_prompt  # noqa: F401

logger = logging.getLogger(__name__)


async def definition(state: AgentState) -> dict:
    # TODO: 구현 필요
    raise NotImplementedError
