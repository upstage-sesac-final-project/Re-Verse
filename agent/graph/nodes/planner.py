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

import json
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
    action_type: Literal["query", "create", "update", "delete", "list", "search"] = Field(
        description='실행 유형. 목록/검색은 "list" 또는 "search" 사용'
    )
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
    reasoning: str = Field(
        description="계획 수립 전 사고 과정: 사용자 요청에서 실제로 필요한 작업이 무엇인지, 불필요한 엔티티는 무엇인지 먼저 정리"
    )
    execution_plan: list[_ExecutionStep] = Field(description="순서 있는 실행 단계 목록")


async def planner(state: AgentState) -> dict:
    """Definition 결과를 받아 실행 계획을 수립한다.

    Args:
        state: 현재 AgentState.

    Returns:
        execution_plan 을 담은 dict.
    """
    logger.info("=" * 60)
    logger.info("[Planner] 노드 진입")
    logger.info(
        "[Planner] 입력 state | intent=%s | target_files=%s",
        state.get("intent"),
        state.get("target_files"),
    )
    logger.debug(
        "[Planner] modifications=%s",
        state.get("modifications"),
    )
    logger.debug(
        "[Planner] extracted_ids=%s",
        state.get("extracted_ids"),
    )
    logger.debug(
        "[Planner] user_input=%s",
        state.get("user_input"),
    )

    messages = build_prompt(state)
    logger.debug(
        "[Planner] 프롬프트 생성 완료 | 메시지 수=%d | human 길이=%d자",
        len(messages),
        len(messages[-1].content) if messages else 0,
    )

    try:
        logger.info("[Planner] LLM 호출 시작")
        result = cast(_PlannerOutput, await invoke_llm(messages, structured_output=_PlannerOutput))
        execution_plan = [step.model_dump() for step in result.execution_plan]

        logger.info(
            "[Planner] LLM 호출 성공 | steps=%d | reasoning=%s",
            len(execution_plan),
            result.reasoning,
        )
        try:
            plan_json = json.dumps(execution_plan, ensure_ascii=False, default=str)
            max_len = 16000
            if len(plan_json) > max_len:
                plan_json = plan_json[:max_len] + f"... (truncated, full_len={len(plan_json)})"
            logger.info("[Planner] execution_plan JSON: %s", plan_json)
        except (TypeError, ValueError) as dump_err:
            logger.warning("[Planner] execution_plan JSON 로깅 실패: %s", dump_err)
        for step in execution_plan:
            logger.debug(
                "[Planner] step %d | action=%s | file=%s | depends_on=%s | condition=%s | desc=%s",
                step["step_id"],
                step["action_type"],
                step["target_file"],
                step["depends_on"],
                step["condition"] or "(없음)",
                step["description"],
            )
    except Exception as e:
        logger.error("[Planner] LLM 호출 실패: %s", e, exc_info=True)
        execution_plan = []

    logger.info("[Planner] 노드 종료 | 반환 step 수=%d", len(execution_plan))
    logger.info("=" * 60)

    return {"execution_plan": execution_plan}
