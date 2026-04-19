"""Router 노드 — 1단계: 의도 분류 + parsed_command 구조화 + pending resume.

Phase C 재작성 포인트
- intent 값 영문 enum (`IntentValue`) 사용
- parsed_command { field, target, action } 구조 LLM structured output 으로 획득
- pending_store 조회하여 이전 hold 가 있으면 이번 턴이 답인지 LLM 판정
  (yes → 스냅샷 복원 + pending resolve + definition 재진입 힌트)
  (no  → pending drop + 새 intent 분류로 진행)
- game_overview 분기 추가

LLM 호출 수
- 빈 입력: 0 회
- pending 없음: 1 회 (intent + parsed_command 통합 structured output)
- pending 있음: 2 회 (yes/no + 위)
"""

import json
import logging
import time
from typing import Literal

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.editor.intents import (
    ACTION_INTENTS,
    DEFINITION_INTENTS,
    TERMINAL_INTENTS,
    IntentValue,
)
from agent.editor.pending_store import PendingStore, get_default_store
from agent.editor.prompts.router_prompt import build_prompt
from agent.editor.state import AgentState
from app.backend.core.game_paths import get_game_data_path

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.7


class _ParsedCommand(BaseModel):
    field: str = Field(default="", description="카테고리 라벨 (적/무기/이벤트 등)")
    target: str = Field(default="", description="대상 이름·id (따옴표 제거)")
    action: str = Field(default="", description="'생성' | '수정' | '조회' | ''")
    property: str = Field(
        default="", description="수정/조회 대상 속성 (예: HP, 공격력, 가격, 이름). 없으면 빈 문자열"
    )
    value: str = Field(
        default="", description="설정하려는 값 (예: 500, 냥냥펀치, 전설무기). 없으면 빈 문자열"
    )
    bulk_scope: str = Field(
        default="",
        description="다중 대상 범위 — 'all' | '' (단일). 예: '모든 적', '적 전부' 는 'all'",
    )
    additional_properties: list[dict] = Field(
        default_factory=list,
        description=(
            "같은 대상에 대해 **여러 속성을 동시에 지정** 하는 경우 사용. "
            "첫 속성은 property/value 에, 나머지는 이 배열에. "
            "각 원소: {'property': str, 'value': str}. "
            "예) '체력 400 mp 30 atk 15' → "
            "property='체력', value='400', "
            "additional_properties=[{'property':'mp','value':'30'}, {'property':'공격력','value':'15'}]. "
            "단일 속성이면 빈 list ([])."
        ),
    )


class _ParsedExtraction(BaseModel):
    """다중 엔티티 입력용 — primary 외 추가 대상."""

    field: str = Field(default="")
    target: str = Field(default="")
    action: str = Field(default="")
    property: str = Field(default="")
    value: str = Field(default="")


class _RouterOutput(BaseModel):
    resolved_input: str = Field(default="", description="맥락이 해소된 완전한 요청 문장")
    intent: Literal[
        "object_create",
        "object_update",
        "event_create",
        "event_update",
        "query",
        "game_overview",
        "multi_intent",
        "out_of_scope",
        "small_talk",
        "clarification_needed",
    ] = Field(description="분류된 의도 (영문 enum)")
    confidence: float = Field(ge=0.0, le=1.0, description="분류 신뢰도")
    parsed_command: _ParsedCommand = Field(
        default_factory=_ParsedCommand, description="구조화된 요청 (primary 대상)"
    )
    parsed_extractions: list[_ParsedExtraction] = Field(
        default_factory=list,
        description=(
            "같은 동작을 여러 대상에 동시 적용하는 경우 각 대상별 추출. "
            "primary 1 개만이면 빈 list. 예: '슬라임이랑 드래곤 만들어줘' → 2 개"
        ),
    )
    needs_context_lookup: bool = Field(
        default=False, description="조사·대명사 참조가 있어 맥락 조회가 필요한지"
    )
    reasoning: str = Field(description="분류 근거")
    response: str = Field(
        default="", description="terminal intent 시 즉시 반환할 응답"
    )


class _YesNoOutput(BaseModel):
    is_answer: bool = Field(
        description="현재 입력이 직전 hold 질문에 대한 '답' 인지 여부"
    )
    reasoning: str = Field(default="", description="판단 근거 한 줄")


_YESNO_SYSTEM = """\
당신은 대화 흐름을 분석하는 판별기입니다.
바로 직전에 시스템이 유저에게 질문(hold)을 던졌고, 유저가 새 입력을 보냈습니다.
이 새 입력이 그 질문에 대한 "답" 인지, 아니면 무관한 새 요청("딴소리")인지 판별하세요.

판정 기준:
- 질문에 대해 긍정/부정/선택을 표현하면 is_answer=true
  예) "어", "응", "그래", "아니", "1번으로", "검 A 로 해"
- 질문과 전혀 다른 새 요청을 하면 is_answer=false
  예) "아니 됐고 슬라임 만들어줘", "그건 놔두고 다른 거 하자"

reasoning 에 한 줄로 근거를 써라.
"""


async def _judge_pending_answer(user_input: str, hold_question: str) -> bool:
    """직전 hold 질문에 대한 답인지 LLM 에게 yes/no 판정 요청."""
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=_YESNO_SYSTEM),
        HumanMessage(
            content=(
                f"## 시스템이 던진 질문\n{hold_question}\n\n"
                f"## 유저의 새 입력\n{user_input}"
            )
        ),
    ]
    try:
        result: _YesNoOutput = await invoke_llm(  # type: ignore[assignment]
            messages, structured_output=_YesNoOutput
        )
        logger.info(
            "[Router] pending yes/no 판정: %s (%s)", result.is_answer, result.reasoning
        )
        return bool(result.is_answer)
    except Exception as e:  # pragma: no cover — LLM 장애 시 안전 기본값
        logger.warning("[Router] pending yes/no 판정 실패: %s → no(드롭)로 처리", e)
        return False


def _load_ranked_candidates(state: AgentState, game_id: str) -> list | None:
    """기존 동작 유지: SampleMapCandidates.json 로드."""
    ranked = state.get("ranked_map_candidates")
    if ranked:
        return ranked
    if not game_id:
        return None
    try:
        candidates_path = get_game_data_path(game_id) / "SampleMapCandidates.json"
        if candidates_path.exists():
            ranked = json.loads(candidates_path.read_text(encoding="utf-8"))
            logger.info("🔀 Router: 맵 후보군 로드 완료 (%d개)", len(ranked))
            return ranked
    except Exception as e:
        logger.warning("🔀 Router: 맵 후보군 로드 실패: %s", e)
    return None


async def router(state: AgentState, *, store: PendingStore | None = None) -> dict:
    """Router 진입점.

    Args:
        state: AgentState
        store: 테스트에서 주입 가능한 PendingStore. 기본은 전역 싱글톤.
    """
    user_input = state.get("user_input", "")
    game_id = state.get("game_id", "")
    conversation_id = state.get("conversation_id", "")
    ranked_candidates = _load_ranked_candidates(state, game_id)

    pstore = store or get_default_store()

    # ── 빈 입력 사전 차단 ───────────────────────────────────────
    if not user_input.strip():
        logger.info("🔀 Router: 빈 입력 → clarification_needed (LLM 0 회)")
        return {
            "intent": IntentValue.CLARIFICATION_NEEDED,
            "confidence": 1.0,
            "ranked_map_candidates": ranked_candidates,
            "final_response": "무엇을 도와드릴까요? 만들거나 수정하고 싶은 게임 요소를 알려주세요.",
            "success": False,
        }

    logger.info("─── 🔀 Router START ────────────────────────────────")
    logger.info("  input : %r", user_input)

    # ── pending 조회 및 이어받기 판정 ───────────────────────────
    pending_resumed = False
    pending_snapshot: dict = {}
    if conversation_id:
        entry = pstore.get(conversation_id)
        if entry is not None and entry.status == "active" and not entry.resolve:
            logger.info(
                "[Router] active hold 발견 (reason=%s) → yes/no 판정",
                entry.hold_reason,
            )
            is_answer = await _judge_pending_answer(user_input, entry.hold_question)
            if is_answer:
                pstore.mark_resolved(conversation_id)
                pending_snapshot = dict(entry.snapshot)
                pending_resumed = True
                logger.info("[Router] pending resolved → definition 재진입 힌트")
            else:
                pstore.mark_dropped(conversation_id)
                logger.info("[Router] pending dropped → 새 intent 분류 진행")

    # ── 메인 분류 LLM 호출 ──────────────────────────────────────
    messages = build_prompt(state)
    _t0 = time.perf_counter()
    output: _RouterOutput = await invoke_llm(  # type: ignore[assignment]
        messages, structured_output=_RouterOutput
    )
    _elapsed = time.perf_counter() - _t0

    logger.info(
        "  intent: %s (confidence=%.2f, elapsed=%.2fs)",
        output.intent,
        output.confidence,
        _elapsed,
    )
    logger.info("  reason: %s", output.reasoning)

    intent: str = output.intent

    # confidence 가 기준 미만인 액션 intent 는 clarification_needed 로 강제 전환
    if intent in ACTION_INTENTS and output.confidence < _CONFIDENCE_THRESHOLD:
        logger.warning(
            "  ⚠️  confidence %.2f < %.2f → clarification_needed 로 강제 전환 (원래: %s)",
            output.confidence,
            _CONFIDENCE_THRESHOLD,
            intent,
        )
        intent = IntentValue.CLARIFICATION_NEEDED

    resolved = output.resolved_input.strip() if output.resolved_input else ""
    if resolved:
        logger.info("  resolved: %r", resolved)

    parsed_command = output.parsed_command.model_dump()
    parsed_extractions = [e.model_dump() for e in output.parsed_extractions]

    result: dict = {
        "intent": intent,
        "confidence": output.confidence,
        "resolved_input": resolved,
        "parsed_command": parsed_command,
        "parsed_extractions": parsed_extractions,
        "needs_context_lookup": bool(output.needs_context_lookup),
        "pending_resumed": pending_resumed,
        "ranked_map_candidates": ranked_candidates,
    }

    # pending 이어받기 힌트는 따로 보존 (Phase D definition 이 소비 예정)
    if pending_resumed and pending_snapshot:
        result["resumed_snapshot"] = pending_snapshot

    # ── terminal intent 는 final_response 를 미리 채움 ───────────
    # terminal intent 는 synthesizer 안 거치고 __end__ 로 직통이라
    # success=False 도 여기서 함께 세팅 (API 레이어가 올바로 읽도록)
    if intent == IntentValue.MULTI_INTENT:
        result["final_response"] = (
            "요청을 하나씩 입력해주세요. 예) '슬라임 HP 올려줘' 후 '드래곤 만들어줘'"
        )
        result["success"] = False
        logger.info("─── 🛑 Router END → multi_intent (terminal) ─────────")
    elif intent in TERMINAL_INTENTS:
        result["final_response"] = output.response or "조금 더 구체적으로 말씀해주시겠어요?"
        result["success"] = False
        logger.info("─── 🛑 Router END → %s (terminal) ───────────────────", intent)
    elif intent in DEFINITION_INTENTS:
        logger.info("─── ✅ Router END → %s (next: definition) ───────────", intent)
    else:  # query / game_overview
        logger.info("─── ✅ Router END → %s (next: reader) ───────────────", intent)

    return result
