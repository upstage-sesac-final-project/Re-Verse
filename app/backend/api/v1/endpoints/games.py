"""게임 프로젝트 CRUD 엔드포인트."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.core.security import get_current_user
from app.backend.db.session import get_db
from app.backend.models.user import User
from app.backend.schemas.game import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.backend.services.game_service import game_service

router = APIRouter()


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 프로젝트 목록 조회."""
    projects = await game_service.list_projects(current_user.id, db)
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects),
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 생성 (base_game 복사, game_id 채번)."""
    project = await game_service.create_project(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        db=db,
    )
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 상세 조회 (소유권 확인)."""
    project = await game_service.get_project(project_id, current_user.id, db)
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    request: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 이름/설명 수정 (소유권 확인)."""
    project = await game_service.update_project(
        project_id=project_id,
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        db=db,
    )
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 삭제 (DB cascade + 게임 폴더 삭제)."""
    await game_service.delete_project(project_id, current_user.id, db)


@router.get("/{project_id}/data/{filename}")
async def get_game_data(
    project_id: int,
    filename: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """게임 JSON 파일 서빙 (소유권 확인 + path traversal 방어)."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="잘못된 파일명입니다.",
        )

    project = await game_service.get_project(project_id, current_user.id, db)
    file_path = Path(settings.STORAGE_PATH).resolve() / project.game_id / "data" / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="파일을 찾을 수 없습니다.",
        )

    data = json.loads(file_path.read_text(encoding="utf-8"))
    return JSONResponse(content=data)
