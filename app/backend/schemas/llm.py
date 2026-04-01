"""
LLM Request/Response Schemas
Frontend <-> Backend <-> Agent 간 데이터 교환 스키마
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ==================== Frontend -> Backend ====================


class UserInputRequest(BaseModel):
    """사용자 입력 요청 (Frontend -> Backend)"""

    project_id: int = Field(..., description="프로젝트 DB ID")
    message: str = Field(..., description="유저 입력 프롬프트", min_length=1)


# ==================== Agent Response ====================


class ToolCall(BaseModel):
    """Agent가 호출한 도구 정보"""

    tool_name: str = Field(..., description="도구 이름 (예: modify_map, modify_npc)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="도구 파라미터")
    result: dict[str, Any] | None = Field(None, description="도구 실행 결과")


class AgentResponse(BaseModel):
    """Agent 응답 (Agent -> Backend)"""

    intent: str = Field(..., description="의도 분류")
    tool_calls: list[ToolCall] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    message: str = Field("", description="사용자에게 보여줄 메시지")
    success: bool = Field(True)


# ==================== Backend -> Frontend ====================


class ChangeLog(BaseModel):
    """단일 변경 로그 항목"""

    step_id: int = Field(..., description="실행 순서")
    tool_name: str = Field(..., description="호출된 도구 이름")
    description: str = Field("", description="작업 설명")
    success: bool = Field(True)
    result_summary: str = Field("", description="결과 요약")


class ProcessResponse(BaseModel):
    """프로세스 처리 응답"""

    code: int = Field(201, description="성공 시 201")
    message: str = Field("", description="처리 메시지")
    result: dict[str, Any] = Field(default_factory=dict)

    intent: str | None = Field(None, description="파악된 의도")
    modifications: list[str] | None = Field(None, description="수정된 항목 목록")
    affected_files: list[str] | None = Field(None, description="영향받은 파일 목록")
    changes_log: list[ChangeLog] = Field(default_factory=list, description="실행된 변경 로그")
    reload_required: bool = Field(False, description="프론트엔드 게임 리로드 필요 여부")
    success: bool = Field(True, description="처리 성공 여부")


class ConversationLogResponse(BaseModel):
    """대화 이력 응답"""

    id: int
    user_input: str
    agent_response: str | None
    intent: str | None
    success: bool
    processing_time: float | None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
