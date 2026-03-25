"""Planner 노드 — 3단계: 수정 시나리오 계획 수립.

담당: 화진님

역할:
    Definition이 추출한 수정 내용을 받아, RPG Maker MZ 파일 구조 지식을 기반으로
    실행 순서가 있는 자연어 단계 계획(execution_plan)을 수립한다.
    파일에는 접근하지 않는다.

입력 (state):
    user_input, intent, modifications, extracted_ids, target_files

출력 (state):
    execution_plan: list[dict]
"""

import logging
from typing import Literal, cast

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.planner_prompt import build_prompt

logger = logging.getLogger(__name__)


class _ExecutionStep(BaseModel):
    step_id: int = Field(description="단계 번호 (1부터 시작)")
    description: str = Field(description="executor가 읽을 자연어 실행 지침")
    action_type: Literal["query", "create", "update", "delete"] = Field(description="실행 유형")
    target_file: str = Field(description="대상 JSON 파일명 (예: Skills.json)")
    target_info: dict = Field(description="이 step에서 다룰 데이터 명세")
    depends_on: list[int] = Field(
        default_factory=list,
        description="선행 step_id 목록. 빈 리스트면 즉시 실행",
    )
    condition: str = Field(
        default="",
        description="실행 조건. 없으면 빈 문자열",
    )


class _PlannerOutput(BaseModel):
    execution_plan: list[_ExecutionStep] = Field(description="순서 있는 실행 단계 목록")
    reasoning: str = Field(description="계획 수립 근거 (로깅용)")


async def planner(state: AgentState) -> dict:
    """Definition 결과를 받아 실행 계획을 수립한다.

    Args:
        state: 현재 AgentState.

    Returns:
        execution_plan 을 담은 dict.
    """
    logger.info(
        "Planner 시작 | intent=%s | target_files=%s",
        state.get("intent"),
        state.get("target_files"),
    )

    messages = build_prompt(state)

    try:
        result = cast(_PlannerOutput, await invoke_llm(messages, structured_output=_PlannerOutput))
        execution_plan = [step.model_dump() for step in result.execution_plan]
        logger.info(
            "Planner 완료 | steps=%d | reasoning=%s",
            len(execution_plan),
            result.reasoning,
        )
    except Exception as e:
        logger.error("Planner LLM 호출 실패: %s", e)
        execution_plan = []

    return {"execution_plan": execution_plan}
