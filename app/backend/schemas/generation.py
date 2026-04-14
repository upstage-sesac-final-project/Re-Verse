"""Full Generation API 요청/응답 Pydantic 스키마.

canonical: docs/The_world/generation_api.md
"""

from pydantic import BaseModel, Field


class GenerationOptions(BaseModel):
    playtime_minutes: int = Field(default=7, ge=5, le=15)
    seed: int | None = None
    phase_limit: str | None = Field(
        default=None,
        description="디버그용. None=전체 생성, 'assets'=에셋만, 'maps'=맵까지",
    )
    map_source: str | None = Field(
        default=None,
        description="맵 생성 방식. None/'algorithmic'=D+E로 타일 생성, 'samples'=샘플맵 선택기 사용",
    )


class GenerationRequest(BaseModel):
    project_id: int
    prompt: str = Field(min_length=5, max_length=1000)
    options: GenerationOptions = GenerationOptions()


class GenerationStartResponse(BaseModel):
    generation_id: str
    status: str = "started"
    estimated_seconds: int = 60
    ws_url: str
    queue_position: int = 0  # 0이면 즉시 시작, 1이상이면 대기열
    queue_wait_seconds: int = 0  # 예상 대기 시간


class GenerationStatusResponse(BaseModel):
    generation_id: str
    status: str  # idle | queued | in_progress | completed | completed_with_warnings | failed | cancelled
    progress: int = 0
    phase: str | None = None
    message: str | None = None
    completed_phases: list[str] = []
    is_success: bool | None = None
    final_message: str | None = None
    validation_errors: list[str] = []
    error_phase: str | None = None
    error_message: str | None = None
    queue_position: int = 0
    queue_wait_seconds: int = 0
