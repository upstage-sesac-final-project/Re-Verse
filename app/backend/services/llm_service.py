"""
LLM Service
Agent 호출을 담당하는 서비스 레이어
"""

import asyncio

from app.backend.core.config import settings
from app.backend.schemas.llm import AgentResponse, ToolCall, UserInputRequest
from app.backend.services.json_modify_tools.dispatcher import (
    run_enemies,
    run_items,
    run_map_villager,
)


class LLMService:
    """LLM Agent 호출 서비스"""

    def __init__(self):
        self.timeout = settings.AGENT_TIMEOUT
        self.max_retries = settings.MAX_RETRIES

    async def process_user_input(self, user_request: UserInputRequest) -> AgentResponse:
        """
        사용자 입력을 Agent에 전달하고 결과를 받아옴

        Args:
            user_request: 사용자 입력 요청

        Returns:
            AgentResponse: Agent 처리 결과
        """
        try:
            # Agent 호출 (현재는 mock, 실제로는 agent 모듈 호출)
            agent_result = await self._call_agent(user_request)

            return agent_result

        except TimeoutError:
            return AgentResponse(
                intent="error",
                tool_calls=[],
                result={"error": "Agent timeout"},
                message="요청 처리 시간이 초과되었습니다.",
                success=False,
            )
        except Exception as e:
            return AgentResponse(
                intent="error",
                tool_calls=[],
                result={"error": str(e)},
                message=f"처리 중 오류가 발생했습니다: {str(e)}",
                success=False,
            )

    async def _call_agent(self, request: UserInputRequest) -> AgentResponse:
        """
        실제 Agent 호출 (MVP: Mock 구현)
        TODO: agent 모듈과 연동
        """
        # MVP: 간단한 키워드 기반 의도 파악 (임시)
        user_input = request.request.lower()

        # 의도 분류 + 편집 함수 호출
        tool_calls = []

        if any(keyword in user_input for keyword in ["적", "몬스터", "몹"]):
            intent = "modify_enemy"
            tool_name = "edit_enemies"
            message = "몬스터를 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_enemies, request.request)

        elif any(keyword in user_input for keyword in ["아이템", "템"]):
            intent = "modify_item"
            tool_name = "edit_items"
            message = "아이템을 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_items, request.request)

        elif any(keyword in user_input for keyword in ["맵", "지형", "타일", "지도", "건물"]):
            intent = "modify_map"
            tool_name = "edit_map_villager"
            message = "맵을 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_map_villager, request.request)

        else:
            intent = "unknown"
            tool_name = "none"
            tool_result = None
            message = "요청을 이해하지 못했습니다. 더 구체적으로 말씀해주세요."

        if tool_result is not None:
            tool_calls.append(
                ToolCall(
                    tool_name=tool_name,
                    parameters={
                        "user_input": request.request,
                        "game_id": request.game_id,
                    },
                    result=tool_result,
                )
            )

        # tool_result 기반으로 실제 성공 여부 판단
        edit_success = tool_result.get("success", False) if tool_result else False

        return AgentResponse(
            intent=intent,
            tool_calls=tool_calls,
            result={
                "intent": intent,
                "processed": edit_success,
                "user_input": request.request,
                "modifications": [tool_name] if edit_success else [],
                "error": tool_result.get("stderr") if tool_result and not edit_success else None,
            },
            message=message
            if edit_success
            else tool_result.get("stderr", message)
            if tool_result
            else message,
            success=edit_success if intent != "unknown" else False,
        )


# 싱글톤 인스턴스
llm_service = LLMService()
