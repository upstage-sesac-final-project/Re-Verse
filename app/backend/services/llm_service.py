"""
LLM Service
Agent 호출을 담당하는 서비스 레이어
"""

import asyncio
from datetime import datetime

from app.backend.core.config import settings
from app.backend.schemas.llm import AgentResponse, ToolCall, UserInputRequest


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

        # 의도 분류
        if any(keyword in user_input for keyword in ["npc", "캐릭터", "주민", "사람"]):
            intent = "modify_npc"
            tool_name = "modify_npc"
            message = "NPC를 수정하는 중입니다..."

        elif any(keyword in user_input for keyword in ["맵", "지형", "타일", "지도", "건물"]):
            intent = "modify_map"
            tool_name = "modify_map"
            message = "맵을 수정하는 중입니다..."

        else:
            intent = "unknown"
            tool_name = "none"
            message = "요청을 이해하지 못했습니다. 더 구체적으로 말씀해주세요."

        # Mock tool call 생성
        tool_calls = []
        if tool_name != "none":
            tool_calls.append(
                ToolCall(
                    tool_name=tool_name,
                    parameters={
                        "user_input": request.request,
                        "game_id": request.game_id,
                    },
                    result={
                        "status": "success",
                        "modified_files": ["Actors.json"]
                        if intent == "modify_npc"
                        else ["Map001.json"],
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            )

        # 시뮬레이션 지연 (실제 Agent 호출 시뮬레이션)
        await asyncio.sleep(0.5)

        return AgentResponse(
            intent=intent,
            tool_calls=tool_calls,
            result={
                "intent": intent,
                "processed": True,
                "user_input": request.request,
                "modifications": [tool_name] if tool_name != "none" else [],
            },
            message=message,
            success=True if intent != "unknown" else False,
        )


# 싱글톤 인스턴스
llm_service = LLMService()
