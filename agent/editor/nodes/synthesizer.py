"""Synthesizer 노드 — 최종 사용자 응답 생성.

validator 의 검증 결과 + changes_log 를 바탕으로 final_response 를 만든다.
Phase H: 결정론 템플릿 기반 (LLM 0 회). soundness_warnings 포장 + hold 응답
렌더 훅 추가. YB.md 8-3 경로 분기 준수:
  - router terminal / definition hold → 기존 final_response 재사용
  - executor/validator 완료 → build_final_response (결정론)
"""

import logging

from agent.editor.nodes.validator.responder import build_final_response, build_hold_response
from agent.editor.state import AgentState

logger = logging.getLogger(__name__)


async def synthesizer(state: AgentState) -> dict:
    passed = state.get("success", True)
    retry_count = state.get("retry_count", 0)

    logger.info("─── ✍️  Synthesizer START ──────────────────────────────")
    logger.info("  intent : %s", state.get("intent"))
    logger.info("  passed : %s | retry_count : %d", passed, retry_count)

    # Phase H: definition 이 resolve=False 로 끝낸 경우 hold 응답 렌더
    if state.get("resolve") is False:
        hold_q = state.get("hold_question") or state.get("message_for_user") or ""
        hold_r = state.get("hold_reason")
        response = build_hold_response(hold_q, hold_r)
        logger.info(
            "─── ✅ Synthesizer END (hold, reason=%s, len=%d) ────────────",
            hold_r,
            len(response),
        )
        return {"final_response": response}

    # router terminal 이나 definition 의 기존 params_sufficient=False 경로에서
    # 이미 final_response 를 set 해 뒀다면 그대로 반환.
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
    soundness_warnings = state.get("soundness_warnings", []) or []

    if not passed:
        logger.warning("  ❌ 실패 상태 (retry=%d) — 에러 응답 생성", retry_count)

    response = build_final_response(
        success=passed,
        summary=validation_summary,
        changes_log=changes_log,
        details=validation_details,
        soundness_warnings=soundness_warnings,
    )

    logger.info(
        "─── ✅ Synthesizer END (len=%d, warnings=%d) ────────────",
        len(response),
        len(soundness_warnings),
    )
    return {"final_response": response}
