"""GenerationValidator 이후 라우팅 로직."""

from agent.generation.state import GenerationState

MAX_RETRY = 2


def route_after_validator(state: GenerationState) -> str:
    """검증 성공 시 END, 실패 시 Architect 재시도 (최대 2회)."""
    if state.get("success", False):
        return "__end__"
    if state.get("retry_count", 0) < MAX_RETRY:
        return "architect"
    return "__end__"
