"""조건부 라우팅 함수 — 워크플로우 분기 로직."""

import logging

from agent.editor.intents import DEFINITION_INTENTS, READER_INTENTS, IntentValue
from agent.editor.state import AgentState

logger = logging.getLogger(__name__)


def route_after_router(state: AgentState) -> str:
    """Router 이후 분기 — Phase C 기준 영문 intent.

    - object_create / object_update / event_create / event_update → definition
    - query / game_overview → reader
    - multi_intent / out_of_scope / small_talk / clarification_needed → __end__
    """
    intent = state.get("intent", IntentValue.OUT_OF_SCOPE)

    if intent in DEFINITION_INTENTS:
        logger.info("[route] router → definition (intent=%s)", intent)
        return "definition"
    if intent in READER_INTENTS:
        logger.info("[route] router → reader (intent=%s)", intent)
        return "reader"
    logger.info("[route] router → __end__ (intent=%s)", intent)
    return "__end__"


def route_after_definition(state: AgentState) -> str:
    """Definition 이후 분기.

    - resolve=False (hold) → __end__ (유저에게 hold_question 반환)
    - 파라미터 충분 → planner
    - 파라미터 불충분 → __end__ (기존 경로, clarification 메시지 포함)

    hold 분기와 params_sufficient 분기는 병행 허용. 재설계가 완료된 이후
    params_sufficient 는 resolve 로 완전히 대체 예정.
    """
    # Phase D+E-1: hold 감지 우선
    if state.get("resolve") is False:
        logger.info(
            "[route] definition → __end__ (hold, reason=%s)",
            state.get("hold_reason"),
        )
        return "__end__"

    if state.get("params_sufficient", False):
        logger.info("[route] definition → planner")
        return "planner"
    logger.info("[route] definition → __end__ (params_sufficient=False)")
    return "__end__"


# route_after_validator 는 Phase A 에서 제거됨.
# 실제 workflow (workflow.py) 는 validator → synthesizer 로 항상 전진한다.
# retry 는 validator 내부의 run_partial_retry 가 수행한다.
