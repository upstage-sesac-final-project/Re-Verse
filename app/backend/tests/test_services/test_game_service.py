"""GameService 단위 테스트."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.game import Project
from app.backend.models.user import User
from app.backend.services.game_service import game_service


class TestCreateProject:
    async def test_create_success(self, db_session: AsyncSession, test_user: User):
        with patch.object(game_service, "_copy_base_game"):
            project = await game_service.create_project(
                user_id=test_user.id,
                name="Service Test",
                description="desc",
                db=db_session,
            )
        assert project.name == "Service Test"
        assert project.user_id == test_user.id
        assert project.game_id.startswith("game_")
        assert project.status == "draft"

    async def test_create_limit_exceeded(self, db_session: AsyncSession, test_user: User):
        for i in range(3):
            p = Project(
                user_id=test_user.id,
                name=f"P{i}",
                game_id=f"game_svc_{i:03d}",
            )
            db_session.add(p)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await game_service.create_project(
                user_id=test_user.id, name="Over", description=None, db=db_session
            )
        assert exc_info.value.status_code == 400

    async def test_create_rollback_on_copy_failure(self, db_session: AsyncSession, test_user: User):
        """base_game 복사 실패 시 DB 롤백 + 폴더 정리."""
        with (
            patch.object(game_service, "_copy_base_game", side_effect=FileNotFoundError("no base")),
            patch.object(game_service, "_cleanup_game_folder") as mock_cleanup,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await game_service.create_project(
                    user_id=test_user.id, name="Fail", description=None, db=db_session
                )
            assert exc_info.value.status_code == 500
            mock_cleanup.assert_called_once()


class TestGetProject:
    async def test_get_success(self, db_session: AsyncSession, test_project: Project):
        project = await game_service.get_project(test_project.id, test_project.user_id, db_session)
        assert project.id == test_project.id

    async def test_get_not_found(self, db_session: AsyncSession, test_user: User):
        with pytest.raises(HTTPException) as exc_info:
            await game_service.get_project(9999, test_user.id, db_session)
        assert exc_info.value.status_code == 404

    async def test_get_forbidden(
        self, db_session: AsyncSession, test_project: Project, other_user: User
    ):
        with pytest.raises(HTTPException) as exc_info:
            await game_service.get_project(test_project.id, other_user.id, db_session)
        assert exc_info.value.status_code == 403


class TestUpdateProject:
    async def test_update_name(self, db_session: AsyncSession, test_project: Project):
        updated = await game_service.update_project(
            project_id=test_project.id,
            user_id=test_project.user_id,
            name="New Name",
            description=None,
            db=db_session,
        )
        assert updated.name == "New Name"
        assert updated.description == test_project.description

    async def test_update_both(self, db_session: AsyncSession, test_project: Project):
        updated = await game_service.update_project(
            project_id=test_project.id,
            user_id=test_project.user_id,
            name="N",
            description="D",
            db=db_session,
        )
        assert updated.name == "N"
        assert updated.description == "D"


class TestDeleteProject:
    async def test_delete_success(self, db_session: AsyncSession, test_project: Project):
        pid = test_project.id
        uid = test_project.user_id

        with patch.object(game_service, "_delete_game_folder"):
            await game_service.delete_project(pid, uid, db_session)

        with pytest.raises(HTTPException) as exc_info:
            await game_service.get_project(pid, uid, db_session)
        assert exc_info.value.status_code == 404

    async def test_delete_cleans_up_game_lock(
        self, db_session: AsyncSession, test_project: Project
    ):
        """프로젝트 삭제 시 _game_locks에서 해당 lock이 제거되는지 확인."""
        from app.backend.services.llm_service import _game_locks

        game_id = test_project.game_id
        # lock을 미리 생성해둠
        _game_locks[game_id] = asyncio.Lock()

        with patch.object(game_service, "_delete_game_folder"):
            await game_service.delete_project(test_project.id, test_project.user_id, db_session)

        assert game_id not in _game_locks

    async def test_delete_forbidden(
        self, db_session: AsyncSession, test_project: Project, other_user: User
    ):
        with pytest.raises(HTTPException) as exc_info:
            await game_service.delete_project(test_project.id, other_user.id, db_session)
        assert exc_info.value.status_code == 403

    async def test_delete_folder_failure_is_warning(
        self, db_session: AsyncSession, test_project: Project
    ):
        """폴더 삭제 실패해도 DB 삭제는 유지 (orphan 허용)."""
        pid = test_project.id
        uid = test_project.user_id

        with patch.object(game_service, "_delete_game_folder", side_effect=OSError("disk error")):
            # 에러가 raise되지 않아야 함
            await game_service.delete_project(pid, uid, db_session)

        with pytest.raises(HTTPException) as exc_info:
            await game_service.get_project(pid, uid, db_session)
        assert exc_info.value.status_code == 404


class TestListProjects:
    async def test_list_empty(self, db_session: AsyncSession, test_user: User):
        projects = await game_service.list_projects(test_user.id, db_session)
        assert projects == []

    async def test_list_returns_own_only(
        self,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
        test_project: Project,
    ):
        own = await game_service.list_projects(test_user.id, db_session)
        assert len(own) == 1

        others = await game_service.list_projects(other_user.id, db_session)
        assert len(others) == 0
