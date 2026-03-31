"""LLM API Endpoints — 인증 적용 + 대화 이력 조회."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.security import get_current_user
from app.backend.db.session import get_db
from app.backend.models.game import ConversationLog
from app.backend.models.user import User
from app.backend.schemas.llm import (
    ConversationLogResponse,
    ProcessResponse,
    UserInputRequest,
)
from app.backend.services.game_service import game_service
from app.backend.services.llm_service import llm_service

router = APIRouter()


@router.post("/process", response_model=ProcessResponse)
async def process_user_input(
    request: UserInputRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProcessResponse:
    """사용자 입력을 처리하는 메인 엔드포인트 (인증 필수)."""
    try:
        return await llm_service.process_chat(
            project_id=request.project_id,
            message=request.message,
            user_id=current_user.id,
            db=db,
        )
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("LLM 처리 오류")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="요청 처리 중 오류가 발생했습니다.",
        )


@router.get("/history/{project_id}", response_model=list[ConversationLogResponse])
async def get_conversation_history(
    project_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대화 이력 조회 (인증 + 소유권 확인)."""
    await game_service.get_project(project_id, current_user.id, db)

    result = await db.execute(
        select(ConversationLog)
        .where(ConversationLog.project_id == project_id)
        .order_by(ConversationLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()
    return [ConversationLogResponse.model_validate(log) for log in logs]
