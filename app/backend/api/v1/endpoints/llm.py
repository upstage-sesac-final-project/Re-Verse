"""
LLM API Endpoints
사용자 입력을 받아 Agent로 전달하고 결과를 반환
"""

from fastapi import APIRouter, HTTPException, status

from app.backend.schemas.llm import (
    ProcessResponse,
    UserInputRequest,
)
from app.backend.services.llm_service import llm_service

router = APIRouter()


@router.post("/process", response_model=ProcessResponse)
async def process_user_input(request: UserInputRequest) -> ProcessResponse:
    """
    사용자 입력을 처리하는 메인 엔드포인트

    Flow:
    1. Frontend에서 {"request": "유저 프롬프트"} 전달
    2. Backend가 Agent에 전달
    3. Agent가 의도 분류 및 tool 호출
    4. Backend가 Frontend에 결과 반환

    Args:
        request: 사용자 입력 요청

    Returns:
        ProcessResponse: 처리 결과

    Raises:
        HTTPException: 처리 실패 시
    """
    try:
        # Agent 호출
        agent_response = await llm_service.process_user_input(request)

        # 실패한 경우
        if not agent_response.success:
            return ProcessResponse(
                code=400,
                message=agent_response.message,
                result=agent_response.result,
                intent=agent_response.intent,
                modifications=[],
                affected_files=[],
            )

        # 성공한 경우
        # tool_calls에서 수정된 파일 목록 추출
        affected_files = []
        modifications = []

        for tool_call in agent_response.tool_calls:
            modifications.append(tool_call.tool_name)
            if tool_call.result and "modified_files" in tool_call.result:
                affected_files.extend(tool_call.result["modified_files"])

        return ProcessResponse(
            code=201,
            message=agent_response.message,
            result=agent_response.result,
            intent=agent_response.intent,
            modifications=modifications if modifications else [],
            affected_files=affected_files if affected_files else [],
        )

    except Exception as e:
        # 예상치 못한 에러
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"서버 내부 오류: {str(e)}"
        )
