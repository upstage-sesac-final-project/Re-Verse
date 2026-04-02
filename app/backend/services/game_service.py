"""Game Service — 프로젝트 수준 CRUD.

Executor(게임 데이터 수정)와는 별개의 레이어.
Executor는 이 서비스를 호출하지 않는다.
"""

import logging
import shutil
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.models.game import Project
from app.backend.repositories.project_repository import project_repository

logger = logging.getLogger(__name__)


class GameService:
    async def create_project(
        self,
        user_id: int,
        name: str,
        description: str | None,
        db: AsyncSession,
    ) -> Project:
        # ① 프로젝트 수 제한
        count = await project_repository.count_by_user(user_id, db)
        if count >= settings.MAX_PROJECTS_PER_USER:
            logger.warning(
                "[GameService] 프로젝트 생성 제한 초과 | user_id=%d, count=%d",
                user_id,
                count,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"프로젝트는 최대 {settings.MAX_PROJECTS_PER_USER}개까지 생성 가능합니다.",
            )

        # ② game_id 채번 (UUID 기반 — 동시 요청 충돌 방지)
        game_id = f"game_{uuid.uuid4().hex[:8]}"

        # ③ 트랜잭션 + 롤백
        project = Project(
            user_id=user_id,
            name=name,
            description=description,
            game_id=game_id,
        )
        await project_repository.create(project, db)

        try:
            self._copy_base_game(game_id)
            await project_repository.commit(db)
            await project_repository.refresh(project, db)
        except Exception:
            logger.error(
                "[GameService] 프로젝트 생성 실패 — 롤백 | user_id=%d, game_id=%s",
                user_id,
                game_id,
                exc_info=True,
            )
            await project_repository.rollback(db)
            self._cleanup_game_folder(game_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="프로젝트 생성 중 오류가 발생했습니다.",
            )
        logger.info(
            "[GameService] 프로젝트 생성 완료 | user_id=%d, project_id=%d, game_id=%s",
            user_id,
            project.id,
            game_id,
        )
        return project

    async def list_projects(self, user_id: int, db: AsyncSession) -> list[Project]:
        return await project_repository.find_by_user(user_id, db)

    async def get_project(self, project_id: int, user_id: int, db: AsyncSession) -> Project:
        project = await project_repository.find_by_id(project_id, db)
        if project is None:
            logger.warning("[GameService] 프로젝트 없음 | project_id=%d", project_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="프로젝트를 찾을 수 없습니다.",
            )
        if project.user_id != user_id:
            logger.warning(
                "[GameService] 접근 권한 없음 | project_id=%d, owner=%d, requester=%d",
                project_id,
                project.user_id,
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다.",
            )
        return project

    async def update_project(
        self,
        project_id: int,
        user_id: int,
        name: str | None,
        description: str | None,
        db: AsyncSession,
    ) -> Project:
        project = await self.get_project(project_id, user_id, db)
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        await project_repository.commit(db)
        await project_repository.refresh(project, db)
        return project

    async def delete_project(self, project_id: int, user_id: int, db: AsyncSession) -> None:
        project = await self.get_project(project_id, user_id, db)
        game_id = project.game_id
        try:
            await project_repository.delete(project, db)
        except Exception:
            logger.error(
                "[GameService] 프로젝트 삭제 실패 — 롤백 | project_id=%d, game_id=%s",
                project_id,
                game_id,
                exc_info=True,
            )
            await project_repository.rollback(db)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="프로젝트 삭제 중 오류가 발생했습니다.",
            )
        # DB 삭제 성공 후 리소스 정리
        from app.backend.services.llm_service import remove_game_lock

        remove_game_lock(game_id)
        try:
            self._delete_game_folder(game_id)
        except Exception:
            logger.warning("게임 폴더 삭제 실패 (orphan): game_id=%s", game_id)

    # ── 파일 시스템 헬퍼 ──────────────────────────────────

    def _copy_base_game(self, game_id: str) -> None:
        if settings.STORAGE_BACKEND == "s3":
            self._s3_copy_base_game(game_id)
        else:
            src = Path(settings.BASE_GAME_PATH).resolve()
            dst = Path(settings.STORAGE_PATH).resolve() / game_id
            if not src.exists():
                raise FileNotFoundError(f"base_game 경로 없음: {src}")
            shutil.copytree(src, dst)

    def _delete_game_folder(self, game_id: str) -> None:
        if settings.STORAGE_BACKEND == "s3":
            self._s3_delete_game(game_id)
        else:
            target = Path(settings.STORAGE_PATH).resolve() / game_id
            if target.exists():
                shutil.rmtree(target)

    def _cleanup_game_folder(self, game_id: str) -> None:
        try:
            self._delete_game_folder(game_id)
        except Exception:
            logger.warning("롤백 중 폴더 정리 실패: game_id=%s", game_id)

    def _s3_copy_base_game(self, game_id: str) -> None:
        client = boto3.client("s3", region_name=settings.AWS_REGION)
        bucket = settings.S3_BUCKET_NAME
        prefix = settings.S3_PREFIX.strip("/")
        src_prefix = f"{prefix}/base_game/"
        dst_prefix = f"{prefix}/{game_id}/"
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=src_prefix):
            for obj in page.get("Contents", []):
                src_key = obj["Key"]
                rel = src_key[len(src_prefix) :]
                if not rel:
                    continue
                dst_key = f"{dst_prefix}{rel}"
                client.copy_object(
                    Bucket=bucket,
                    CopySource={"Bucket": bucket, "Key": src_key},
                    Key=dst_key,
                )

    def _s3_delete_game(self, game_id: str) -> None:
        client = boto3.client("s3", region_name=settings.AWS_REGION)
        bucket = settings.S3_BUCKET_NAME
        prefix = f"{settings.S3_PREFIX.strip('/')}/{game_id}/"
        paginator = client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        except ClientError as e:
            logger.error("S3 삭제 실패 game_id=%s: %s", game_id, e)
            raise


game_service = GameService()
