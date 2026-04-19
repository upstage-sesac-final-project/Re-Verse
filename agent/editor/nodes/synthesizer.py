"""Synthesizer 노드 — 최종 사용자 응답 생성 + effective success 확정.

validator 의 검증 결과 + changes_log 를 바탕으로 final_response 를 만든다.
Phase H: 결정론 템플릿 기반 (LLM 0 회). soundness_warnings 포장 + hold 응답
렌더 훅 추가. YB.md 8-3 경로 분기 준수:
  - router terminal / definition hold → 기존 final_response 재사용
  - executor/validator 완료 → build_final_response (결정론)

Task 20: effective_success 정책 —
  - resolve=False (hold) → False
  - intent 가 terminal (multi_intent / out_of_scope / small_talk / clarification_needed) → False
  - changes_log 비었거나 전부 skipped → False
  - 그 외 → validator 의 `success` 를 따른다 (schema 통과 여부)
"""

import logging

from agent.editor.intents import TERMINAL_INTENTS
from agent.editor.nodes.validator.responder import build_final_response, build_hold_response
from agent.editor.state import AgentState

logger = logging.getLogger(__name__)


def _compute_effective_success(state: AgentState) -> bool:
    """API 레이어가 믿을 수 있는 최종 success 판정."""
    # hold 중이면 작업 미완
    if state.get("resolve") is False:
        return False

    intent = state.get("intent", "")
    # terminal intent (multi_intent / out_of_scope / small_talk / clarification_needed) 는
    # 실제 작업을 안 한 상태
    if intent in TERMINAL_INTENTS:
        return False

    # validator 가 schema fail 로 확정했으면 그대로 False
    validator_success = state.get("success", True)
    if validator_success is False:
        return False

    # changes_log 가 전혀 없거나 전부 skipped 면 "아무것도 안 함"
    changes_log = state.get("changes_log", []) or []
    if not changes_log:
        # action intent 인데 changes_log 가 없으면 실패
        return False
    if all(e.get("skipped") for e in changes_log if isinstance(e, dict)):
        return False
    # 모든 엔트리가 실패인 경우도 False
    real_entries = [e for e in changes_log if isinstance(e, dict) and not e.get("skipped")]
    if real_entries and not any(e.get("success") for e in real_entries):
        return False

    return True


async def synthesizer(state: AgentState) -> dict:
    passed = state.get("success", True)
    retry_count = state.get("retry_count", 0)

    logger.info("─── ✍️  Synthesizer START ──────────────────────────────")
    logger.info("  intent : %s", state.get("intent"))
    logger.info("  passed : %s | retry_count : %d", passed, retry_count)

    effective_success = _compute_effective_success(state)
    if effective_success != passed:
        logger.info(
            "  effective_success 재판정: %s → %s (정책: hold / terminal / empty_log)",
            passed,
            effective_success,
        )

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
        return {"final_response": response, "success": False}

    # router terminal 이나 definition 의 기존 params_sufficient=False 경로에서
    # 이미 final_response 를 set 해 뒀다면 그대로 반환.
    existing = state.get("final_response")
    if existing:
        logger.info(
            "─── ✅ Synthesizer END (기존 응답 재사용, len=%d, success=%s) ────────────",
            len(existing),
            effective_success,
        )
        return {"final_response": existing, "success": effective_success}

    changes_log = state.get("changes_log", [])
    validation_summary = state.get("validation_summary", "")
    validation_details = state.get("validation_details", [])
    soundness_warnings = state.get("soundness_warnings", []) or []

    if not effective_success:
        logger.warning("  ❌ 실패 상태 (retry=%d) — 에러 응답 생성", retry_count)

    response = build_final_response(
        success=effective_success,
        summary=validation_summary,
        changes_log=changes_log,
        details=validation_details,
        soundness_warnings=soundness_warnings,
    )

    logger.info(
        "─── ✅ Synthesizer END (len=%d, warnings=%d, success=%s) ────────────",
        len(response),
        len(soundness_warnings),
        effective_success,
    )
    return {"final_response": response, "success": effective_success}
