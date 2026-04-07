"""게임 프로젝트 스키마."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    prompt: str | None = None  # 게임 생성 요청 프롬프트 (The World 파이프라인)


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    game_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    world_summary: str | None = None  # 생성 결과 요약 (The World 파이프라인 실행 시)

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
