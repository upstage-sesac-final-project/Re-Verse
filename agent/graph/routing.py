"""조건부 라우팅 함수 — 워크플로우 분기 로직."""

from agent.graph.state import AgentState


def route_after_router(state: AgentState) -> str:
    """Router 이후 분기.

    - 게임_요소_생성 / 게임_요소_수정 / 게임_요소_조회 → definition
    - 추가_정보_필요 / 일반_대화 / 범위_외 → __end__ (final_response 포함)
    """
    intent = state.get("intent", "범위_외")

    if intent == "게임_맵_수정":
        return "map_node"
    if intent in ("게임_요소_생성", "게임_요소_수정", "게임_요소_조회"):
        return "definition"
    return "__end__"


def route_after_definition(state: AgentState) -> str:
    """Definition 이후 분기.

    - 파라미터 충분 → planner
    - 파라미터 불충분 → __end__ (clarification 메시지 포함)
    """
    if state.get("params_sufficient", False):
        return "planner"
    return "__end__"


def route_after_validator(state: AgentState) -> str:
    """Validator 이후 분기.

    - 검증 통과 → synthesizer
    - 검증 실패 + retry < MAX_RETRIES → executor (재시도)
    - 검증 실패 + retry >= MAX_RETRIES → synthesizer (에러 응답 포함)
    """
    validation = state.get("validation_result", {})
    retry_count = state.get("retry_count", 0)

    if validation.get("passed", False):
        return "synthesizer"

    if retry_count < 2:
        return "executor"

    return "synthesizer"
