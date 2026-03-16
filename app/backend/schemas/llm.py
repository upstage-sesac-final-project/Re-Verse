"""
LLM Request/Response Schemas
Frontend ↔ Backend ↔ Agent 간 데이터 교환 스키마
"""

from typing import Any

from pydantic import BaseModel, Field

# ==================== Frontend → Backend ====================


class UserInputRequest(BaseModel):
    """사용자 입력 요청 (Frontend → Backend)"""

    request: str = Field(..., description="유저 입력 프롬프트", min_length=1)
    game_id: str | None = Field(None, description="게임 ID (선택)")
    session_id: str | None = Field(None, description="세션 ID (선택)")


# ==================== Agent Response ====================


class ToolCall(BaseModel):
    """Agent가 호출한 도구 정보"""

    tool_name: str = Field(..., description="도구 이름 (예: modify_map, modify_npc)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="도구 파라미터")
    result: dict[str, Any] | None = Field(None, description="도구 실행 결과")


class AgentResponse(BaseModel):
    """Agent 응답 (Agent → Backend)"""

    intent: str = Field(..., description="의도 분류 (예: modify_map, modify_npc, create_event)")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="호출된 도구 목록")
    result: dict[str, Any] = Field(default_factory=dict, description="처리 결과")
    message: str = Field("", description="사용자에게 보여줄 메시지")
    success: bool = Field(True, description="성공 여부")


# ==================== Backend → Frontend ====================


class ProcessResponse(BaseModel):
    """프로세스 처리 응답"""

    code: int = Field(201, description="성공 시 201")
    message: str = Field("", description="처리 메시지")
    result: dict[str, Any] = Field(default_factory=dict, description="처리 결과")

    # 추가 정보
    intent: str | None = Field(None, description="파악된 의도")
    modifications: list[str] | None = Field(None, description="수정된 항목 목록")
    affected_files: list[str] | None = Field(None, description="영향받은 파일 목록")
