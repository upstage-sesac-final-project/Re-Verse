"""Intake node — 대화 맥락 해소 + 분류 + operation 추출.

LLM 1회, structured output.
Router + Definition Step 1 을 합친 것.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from new_agent.prompts import build_intake_system_prompt, build_intake_user_prompt

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Structured output 스키마
# ──────────────────────────────────────────────

class OperationSubject(BaseModel):
    name: str = Field(default="", description="대상 엔티티 이름. '모든 액터'처럼 전체 대상이면 그대로 적어줄 것")
    scope: Literal["single", "all"] = Field(default="single", description="단일 대상이면 single, 전체 대상(모든/전체/전원/다)이면 all")

class OperationValue(BaseModel):
    kind: str = Field(default="", description="값 종류 (armor, weapon, skill, param, ...)")
    name: str = Field(default="", description="값 이름 (필드명이나 엔티티명)")
    amount: float | int | None = Field(default=None, description="숫자값이 있으면 여기에 (25, 100, 0.5 등)")
    hints: str | None = Field(default=None, description="추가 컨텍스트 (슬롯 타입 등)")

class OperationTuple(BaseModel):
    op: Literal["create", "update", "delete", "read"] = Field(description="작업 유형")
    file: str = Field(description="대상 JSON 파일")
    subject: OperationSubject = Field(default_factory=OperationSubject)
    field: str | None = Field(default=None, description="대상 필드")
    value: OperationValue | None = Field(default=None)

class IntakeOutput(BaseModel):
    resolved_input: str = Field(description="맥락이 해소된 완전한 요청 문장")
    kind: Literal["actionable", "chat", "out_of_scope", "need_more_info"] = Field(
        description="요청 분류"
    )
    operation_tuples: list[OperationTuple] = Field(
        default_factory=list, description="추출된 operations"
    )
    clarification_question: str | None = Field(
        default=None, description="추가 질문 (need_more_info 시)"
    )


# ──────────────────────────────────────────────
# Node
# ──────────────────────────────────────────────

async def intake(state: dict) -> dict:
    """Intake node entry point."""
    user_input: str = state.get("user_input", "")
    conversation_history: list[dict] = state.get("conversation_history", [])

    if not user_input.strip():
        return {
            "kind": "need_more_info",
            "resolved_input": "",
            "operation_tuples": [],
            "clarification_question": "요청 내용을 입력해주세요.",
            "final_response": "요청 내용을 입력해주세요.",
        }

    system_prompt = build_intake_system_prompt()
    user_prompt = build_intake_user_prompt(user_input, conversation_history)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        result = await invoke_llm(messages, structured_output=IntakeOutput)
        output: IntakeOutput = result  # type: ignore[assignment]
    except Exception as e:
        logger.error("[intake] LLM 호출 실패: %s", e)
        return {
            "kind": "need_more_info",
            "resolved_input": user_input,
            "operation_tuples": [],
            "clarification_question": "요청을 처리하는 중 오류가 발생했습니다. 다시 시도해주세요.",
            "final_response": "요청을 처리하는 중 오류가 발생했습니다. 다시 시도해주세요.",
        }

    result_dict: dict[str, Any] = {
        "kind": output.kind,
        "resolved_input": output.resolved_input,
        "operation_tuples": [op.model_dump() for op in output.operation_tuples],
    }

    # non-actionable → final_response 채우고 END
    if output.kind == "need_more_info":
        q = output.clarification_question or "요청을 좀 더 구체적으로 말씀해주시겠어요?"
        result_dict["clarification_question"] = q
        result_dict["final_response"] = q
    elif output.kind == "chat":
        result_dict["final_response"] = output.resolved_input
    elif output.kind == "out_of_scope":
        result_dict["final_response"] = "죄송합니다, RPG Maker MZ 게임 수정 관련 요청만 처리할 수 있습니다."

    logger.info(
        "[intake] kind=%s resolved='%s' ops=%d",
        output.kind, output.resolved_input[:80], len(output.operation_tuples),
    )
    return result_dict
