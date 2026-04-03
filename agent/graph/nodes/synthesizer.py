"""Synthesizer 노드 — 6단계: 사용자 친화적 최종 응답 생성.

담당: 세종님
"""

import logging
import time

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.synthesizer_prompt import build_prompt

logger = logging.getLogger(__name__)


async def synthesizer(state: AgentState) -> dict:
    passed = state.get("success", True)
    retry_count = state.get("retry_count", 0)

    logger.info("─── ✍️  Synthesizer START ──────────────────────────────")
    logger.info("  intent : %s", state.get("intent"))
    logger.info("  passed : %s | retry_count : %d", passed, retry_count)

    if not passed:
        logger.warning("  ❌ 실패 상태로 진입 (retry=%d) — 에러 응답 생성", retry_count)

    messages = build_prompt(state)
    _t0 = time.perf_counter()
    response: str = await invoke_llm(messages)  # type: ignore[assignment]
    _elapsed = time.perf_counter() - _t0

    logger.info(
        "─── ✅ Synthesizer END (elapsed=%.2fs, len=%d) ────────────", _elapsed, len(response)
    )
    return {"final_response": response}
