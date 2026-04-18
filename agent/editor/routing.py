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


# route_after_validator 는 Phase A 에서 제거됨.
# 실제 workflow (workflow.py) 는 validator → synthesizer 로 항상 전진한다.
# retry 는 validator 내부의 run_partial_retry 가 수행한다.
