"""편집 세션 진입/이탈 엔드포인트."""

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.core.security import get_current_user
from app.backend.db.session import get_db
from app.backend.models.user import User
from app.backend.services.game_service import game_service
from app.backend.services.s3_game_storage import sync_game_from_s3, sync_game_to_s3
from app.backend.services.session_manager import (
    get_game_lock,
    is_active,
    register_session,
    unregister_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{project_id}/enter")
async def enter_editor(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """편집 세션 시작 — S3에서 게임 데이터 다운로드."""
    project = await game_service.get_project(project_id, current_user.id, db)
    game_id = project.game_id

    lock = await get_game_lock(game_id)
    async with lock:
        # 이미 활성 세션이면 409 (register_session 내부에서 raise)
        if is_active(game_id):
            # 같은 사용자가 재진입하는 경우 허용 (새로고침 등)
            from app.backend.services.session_manager import _active_sessions

            existing = _active_sessions.get(game_id)
            if existing and existing.user_id == current_user.id:
                logger.info(
                    "[Editor] 기존 세션 재진입 | game_id=%s, user_id=%d",
                    game_id,
                    current_user.id,
                )
                return {"status": "ok", "game_id": game_id}
            # 다른 사용자 → 409
            register_session(game_id, current_user.id, project_id)  # raises 409

        if settings.STORAGE_BACKEND == "s3":
            logger.info("[Editor] S3 → 로컬 다운로드 시작 | game_id=%s", game_id)
            await asyncio.to_thread(sync_game_from_s3, game_id)
            logger.info("[Editor] S3 → 로컬 다운로드 완료 | game_id=%s", game_id)

        register_session(game_id, current_user.id, project_id)

    return {"status": "ok", "game_id": game_id}


@router.post("/{project_id}/exit")
async def exit_editor(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """편집 세션 종료 — S3 업로드 + 로컬 정리."""
    project = await game_service.get_project(project_id, current_user.id, db)
    game_id = project.game_id

    lock = await get_game_lock(game_id)
    async with lock:
        # S3 업로드 (로컬 폴더가 있으면 항상 시도)
        if settings.STORAGE_BACKEND == "s3":
            local_dir = Path(settings.STORAGE_PATH).resolve() / game_id
            if local_dir.is_dir():
                logger.info("[Editor] 로컬 → S3 업로드 시작 | game_id=%s", game_id)
                await asyncio.to_thread(sync_game_to_s3, game_id)
                await asyncio.to_thread(shutil.rmtree, local_dir)
                logger.info("[Editor] S3 업로드 + 로컬 정리 완료 | game_id=%s", game_id)

        unregister_session(game_id)

    return {"status": "ok"}
