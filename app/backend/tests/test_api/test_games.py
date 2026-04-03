"""게임 프로젝트 CRUD API 테스트."""

from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.game import Project
from app.backend.models.user import User


class TestCreateProject:
    """POST /api/v1/games"""

    async def test_create_project_success(self, client: AsyncClient, auth_headers: dict):
        with patch.object(
            __import__("app.backend.services.game_service", fromlist=["GameService"]).GameService,
            "_copy_base_game",
        ):
            resp = await client.post(
                "/api/v1/games",
                json={"name": "My RPG", "description": "An RPG game"},
                headers=auth_headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My RPG"
        assert data["description"] == "An RPG game"
        assert data["game_id"].startswith("game_")
        assert data["status"] == "draft"

    async def test_create_project_no_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/games",
            json={"name": "No Auth"},
        )
        assert resp.status_code == 401

    async def test_create_project_empty_name(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/games",
            json={"name": "", "description": "empty name"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_create_project_limit(
        self,
        client: AsyncClient,
        test_user: User,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        """MAX_PROJECTS_PER_USER(3) 초과 시 400."""
        for i in range(3):
            project = Project(
                user_id=test_user.id,
                name=f"Project {i}",
                game_id=f"game_limit_{i:03d}",
            )
            db_session.add(project)
        await db_session.commit()

        with patch.object(
            __import__("app.backend.services.game_service", fromlist=["GameService"]).GameService,
            "_copy_base_game",
        ):
            resp = await client.post(
                "/api/v1/games",
                json={"name": "Over Limit"},
                headers=auth_headers,
            )
        assert resp.status_code == 400


class TestListProjects:
    """GET /api/v1/games"""

    async def test_list_empty(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/games", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["projects"] == []
        assert data["total"] == 0

    async def test_list_with_projects(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.get("/api/v1/games", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["projects"][0]["name"] == "Test Project"

    async def test_list_only_own_projects(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        """다른 사용자의 프로젝트는 보이지 않음."""
        resp = await client.get("/api/v1/games", headers=other_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGetProject:
    """GET /api/v1/games/{project_id}"""

    async def test_get_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.get(f"/api/v1/games/{test_project.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == test_project.id

    async def test_get_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/games/9999", headers=auth_headers)
        assert resp.status_code == 404

    async def test_get_forbidden(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        """다른 사용자의 프로젝트 접근 시 403."""
        resp = await client.get(f"/api/v1/games/{test_project.id}", headers=other_auth_headers)
        assert resp.status_code == 403


class TestUpdateProject:
    """PATCH /api/v1/games/{project_id}"""

    async def test_update_name(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.patch(
            f"/api/v1/games/{test_project.id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"
        assert resp.json()["description"] == test_project.description

    async def test_update_description(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.patch(
            f"/api/v1/games/{test_project.id}",
            json={"description": "New description"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "New description"

    async def test_update_forbidden(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        resp = await client.patch(
            f"/api/v1/games/{test_project.id}",
            json={"name": "Hacked"},
            headers=other_auth_headers,
        )
        assert resp.status_code == 403


class TestDeleteProject:
    """DELETE /api/v1/games/{project_id}"""

    async def test_delete_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        with patch.object(
            __import__("app.backend.services.game_service", fromlist=["GameService"]).GameService,
            "_delete_game_folder",
        ):
            resp = await client.delete(f"/api/v1/games/{test_project.id}", headers=auth_headers)
        assert resp.status_code == 204

        # 삭제 확인
        resp = await client.get(f"/api/v1/games/{test_project.id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_forbidden(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        resp = await client.delete(f"/api/v1/games/{test_project.id}", headers=other_auth_headers)
        assert resp.status_code == 403

    async def test_delete_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/games/9999", headers=auth_headers)
        assert resp.status_code == 404
