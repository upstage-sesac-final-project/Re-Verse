"""Synthesizer 노드 — 최종 사용자 응답 생성.

validator 의 검증 결과 + changes_log 를 바탕으로 final_response 를 만든다.
성공: 결정론 템플릿 (LLM 0회)
실패: 결정론 템플릿 + 상세 정보
"""

import logging

from agent.editor.nodes.validator.responder import build_final_response
from agent.editor.state import AgentState

logger = logging.getLogger(__name__)


async def synthesizer(state: AgentState) -> dict:
    passed = state.get("success", True)
    retry_count = state.get("retry_count", 0)

    logger.info("─── ✍️  Synthesizer START ──────────────────────────────")
    logger.info("  intent : %s", state.get("intent"))
    logger.info("  passed : %s | retry_count : %d", passed, retry_count)

    # definition 에서 params_sufficient=False 로 조기 종료한 경우
    existing = state.get("final_response")
    if existing:
        logger.info(
            "─── ✅ Synthesizer END (기존 응답 재사용, len=%d) ────────────",
            len(existing),
        )
        return {"final_response": existing}

    changes_log = state.get("changes_log", [])
    validation_summary = state.get("validation_summary", "")
    validation_details = state.get("validation_details", [])
    judge_feedback = state.get("judge_feedback", "")

    if not passed:
        logger.warning("  ❌ 실패 상태 (retry=%d) — 에러 응답 생성", retry_count)

    response = build_final_response(
        success=passed,
        summary=validation_summary,
        changes_log=changes_log,
        details=validation_details,
        judge_feedback=judge_feedback,
    )

    logger.info("─── ✅ Synthesizer END (len=%d) ────────────", len(response))
    return {"final_response": response}
