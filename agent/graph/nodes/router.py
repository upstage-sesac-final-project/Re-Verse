"""Router 노드 — 1단계: 사용자 의도 분류 및 라우팅 결정.

담당: 세종님
"""

import logging

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm  # noqa: F401
from agent.graph.state import AgentState
from agent.prompts.router_prompt import build_prompt  # noqa: F401

logger = logging.getLogger(__name__)


class _RouterOutput(BaseModel):
    intent: str = Field(description="분류된 의도")
    confidence: float = Field(ge=0.0, le=1.0, description="분류 신뢰도")
    reasoning: str = Field(description="분류 근거")
    response: str = Field(
        default="", description="clarification/chat/out_of_scope 시 즉시 반환할 응답"
    )


async def router(state: AgentState) -> dict:
    # TODO: 구현 필요
    raise NotImplementedError
