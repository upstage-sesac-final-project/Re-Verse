"""Router 노드 — 1단계: 사용자 의도 분류 및 라우팅 결정.

담당: 세종님
"""

import logging
import time
from typing import Literal

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.router_prompt import build_prompt

logger = logging.getLogger(__name__)

_TERMINAL_INTENTS = frozenset({"추가_정보_필요", "복합_의도", "일반_대화", "범위_외"})
_ACTION_INTENTS = frozenset({"게임_요소_생성", "게임_요소_수정", "게임_요소_조회"})
_CONFIDENCE_THRESHOLD = 0.7


class _RouterOutput(BaseModel):
    resolved_input: str = Field(default="", description="맥락이 해소된 완전한 요청 문장")
    intent: Literal[
        "게임_요소_생성",
        "게임_요소_수정",
        "게임_요소_조회",
        "추가_정보_필요",
        "복합_의도",
        "일반_대화",
        "범위_외",
    ] = Field(description="분류된 의도")
    confidence: float = Field(ge=0.0, le=1.0, description="분류 신뢰도")
    reasoning: str = Field(description="분류 근거")
    response: str = Field(
        default="", description="clarification/chat/out_of_scope 시 즉시 반환할 응답"
    )


async def router(state: AgentState) -> dict:
    user_input = state.get("user_input", "")

    # 빈 입력 사전 차단 — LLM 호출 없이 즉시 반환
    if not user_input.strip():
        logger.info("🔀 Router: 빈 입력 감지 → 추가_정보_필요 (LLM 호출 없음)")
        return {
            "intent": "추가_정보_필요",
            "confidence": 1.0,
            "final_response": "무엇을 도와드릴까요? 만들거나 수정하고 싶은 게임 요소를 알려주세요.",
        }

    logger.info("─── 🔀 Router START ────────────────────────────────")
    logger.info("  input : %r", user_input)

    messages = build_prompt(state)
    _t0 = time.perf_counter()
    output: _RouterOutput = await invoke_llm(messages, structured_output=_RouterOutput)  # type: ignore[assignment]
    _elapsed = time.perf_counter() - _t0

    logger.info(
        "  intent: %s (confidence=%.2f, elapsed=%.2fs)",
        output.intent,
        output.confidence,
        _elapsed,
    )
    logger.info("  reason: %s", output.reasoning)

    intent = output.intent

    # confidence 가 기준 미만이면 추가 정보 요청으로 강제 전환
    if intent in _ACTION_INTENTS and output.confidence < _CONFIDENCE_THRESHOLD:
        logger.warning(
            "  ⚠️  confidence %.2f < %.2f → 추가_정보_필요로 강제 전환 (원래 의도: %s)",
            output.confidence,
            _CONFIDENCE_THRESHOLD,
            intent,
        )
        intent = "추가_정보_필요"

    # resolved_input: coref 해소된 입력. 비어 있으면 원본 사용.
    resolved = output.resolved_input.strip() if output.resolved_input else ""
    if resolved:
        logger.info("  resolved: %r", resolved)

    result: dict = {
        "intent": intent,
        "confidence": output.confidence,
        "user_input": resolved or user_input,  # 해소된 입력으로 덮어씀
    }

    # 터미널 인텐트는 즉시 응답을 final_response 에 기록
    if intent == "복합_의도":
        result["final_response"] = (
            "요청을 하나씩 입력해주세요. 예) '슬라임 HP 올려줘' 후 '드래곤 만들어줘'"
        )
        logger.info("─── 🛑 Router END → 복합_의도 (terminal) ──────────────")
    elif intent in _TERMINAL_INTENTS:
        result["final_response"] = output.response or "조금 더 구체적으로 말씀해주시겠어요?"
        logger.info("─── 🛑 Router END → %s (terminal) ─────────────────────", intent)
    else:
        next_node = "reader" if intent == "게임_요소_조회" else "definition"
        logger.info("─── ✅ Router END → %s (next: %s) ──────────────", intent, next_node)

    return result
