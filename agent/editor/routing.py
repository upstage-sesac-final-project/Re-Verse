"""조건부 라우팅 함수 — 워크플로우 분기 로직."""

import logging

from agent.editor.state import AgentState

logger = logging.getLogger(__name__)


def route_after_router(state: AgentState) -> str:
    """Router 이후 분기.

    - 게임_요소_생성 / 게임_요소_수정 → definition
    - 게임_요소_조회 → reader
    - 추가_정보_필요 / 일반_대화 / 범위_외 → __end__ (final_response 포함)
    """
    intent = state.get("intent", "범위_외")

    if intent in ("게임_요소_생성", "게임_요소_수정"):
        logger.info("[route] router → definition (intent=%s)", intent)
        return "definition"
    if intent == "게임_요소_조회":
        logger.info("[route] router → reader (intent=%s)", intent)
        return "reader"
    logger.info("[route] router → __end__ (intent=%s)", intent)
    return "__end__"


def route_after_definition(state: AgentState) -> str:
    """Definition 이후 분기.

    - 파라미터 충분 → planner
    - 파라미터 불충분 → __end__ (clarification 메시지 포함)
    """
    if state.get("params_sufficient", False):
        logger.info("[route] definition → planner")
        return "planner"
    logger.info("[route] definition → __end__ (params_sufficient=False)")
    return "__end__"


def route_after_validator(state: AgentState) -> str:
    """Validator 이후 분기.

    - 검증 통과 → synthesizer
    - 검증 실패 + retry < MAX_RETRIES → executor (재시도)
    - 검증 실패 + retry >= MAX_RETRIES → synthesizer (에러 응답 포함)
    """
    success = state.get("success", False)
    retry_count = state.get("retry_count", 0)

    if success:
        logger.info("[route] validator → synthesizer (success)")
        return "synthesizer"

    if retry_count < 2:
        logger.info("[route] validator → executor (retry %d/2)", retry_count + 1)
        return "executor"

    logger.warning("[route] validator → synthesizer (max retries reached, retry=%d)", retry_count)
    return "synthesizer"
