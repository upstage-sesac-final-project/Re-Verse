"""Generation API 엔드포인트 인증/소유권 테스트."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.backend.api.v1.endpoints.generation as gen_module
from app.backend.core.security import create_access_token
from app.backend.models.game import Project
from app.backend.models.user import User
from app.backend.schemas.generation import GenerationStatusResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_generation_state():
    """각 테스트 전후로 인메모리 상태 초기화."""
    gen_module._generation_states.clear()
    gen_module._generation_owners.clear()
    yield
    gen_module._generation_states.clear()
    gen_module._generation_owners.clear()


@pytest.fixture
def seeded_generation(test_user: User) -> str:
    """test_user 소유의 in_progress generation 상태를 미리 심어둔다."""
    gen_id = "gen_test0001"
    gen_module._generation_states[gen_id] = GenerationStatusResponse(
        generation_id=gen_id,
        status="in_progress",
        progress=30,
    )
    gen_module._generation_owners[gen_id] = test_user.id
    return gen_id


@pytest.fixture
def test_token(test_user: User) -> str:
    """test_user JWT 토큰 문자열 (WS 쿼리 파라미터용)."""
    return create_access_token({"sub": str(test_user.id), "email": test_user.email})


@pytest.fixture
def other_token(other_user: User) -> str:
    """other_user JWT 토큰 문자열."""
    return create_access_token({"sub": str(other_user.id), "email": other_user.email})


# ---------------------------------------------------------------------------
# POST /api/v1/generate
# ---------------------------------------------------------------------------


class TestStartGeneration:
    """POST /api/v1/generate"""

    async def test_no_auth_returns_401(self, client: AsyncClient, test_project: Project):
        resp = await client.post(
            "/api/v1/generate",
            json={"project_id": test_project.id, "prompt": "판타지 RPG 세계관"},
        )
        assert resp.status_code == 401

    async def test_nonexistent_project_returns_404(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/generate",
            json={"project_id": 9999, "prompt": "판타지 RPG 세계관"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_other_users_project_returns_404(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        """다른 사용자의 프로젝트로 생성 요청 시 404."""
        resp = await client.post(
            "/api/v1/generate",
            json={"project_id": test_project.id, "prompt": "판타지 RPG 세계관"},
            headers=other_auth_headers,
        )
        assert resp.status_code == 404

    async def test_success_returns_202(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        with patch(
            "app.backend.api.v1.endpoints.generation.run_generation_workflow",
            new_callable=AsyncMock,
            return_value={
                "is_success": True,
                "final_project": None,
                "completed_phases": [],
                "final_message": "완료",
                "validation_errors": [],
            },
        ):
            resp = await client.post(
                "/api/v1/generate",
                json={"project_id": test_project.id, "prompt": "판타지 RPG 세계관"},
                headers=auth_headers,
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "generation_id" in data
        assert data["generation_id"].startswith("gen_")
        assert "ws_url" in data
        assert data["status"] == "started"

    async def test_success_registers_owner(
        self, client: AsyncClient, auth_headers: dict, test_project: Project, test_user: User
    ):
        """생성 시작 시 _generation_owners에 소유자가 등록된다."""
        with patch(
            "app.backend.api.v1.endpoints.generation.run_generation_workflow",
            new_callable=AsyncMock,
            return_value={
                "is_success": True,
                "final_project": None,
                "completed_phases": [],
                "final_message": "완료",
                "validation_errors": [],
            },
        ):
            resp = await client.post(
                "/api/v1/generate",
                json={"project_id": test_project.id, "prompt": "판타지 RPG 세계관"},
                headers=auth_headers,
            )

        gen_id = resp.json()["generation_id"]
        assert gen_module._generation_owners.get(gen_id) == test_user.id

    async def test_prompt_too_short_returns_422(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.post(
            "/api/v1/generate",
            json={"project_id": test_project.id, "prompt": "짧"},
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/generate/{generation_id}/status
# ---------------------------------------------------------------------------


class TestGetGenerationStatus:
    """GET /api/v1/generate/{generation_id}/status"""

    async def test_no_auth_returns_401(self, client: AsyncClient, seeded_generation: str):
        resp = await client.get(f"/api/v1/generate/{seeded_generation}/status")
        assert resp.status_code == 401

    async def test_nonexistent_gen_id_returns_404(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/generate/gen_notexist/status", headers=auth_headers)
        assert resp.status_code == 404

    async def test_other_users_gen_returns_404(
        self, client: AsyncClient, other_auth_headers: dict, seeded_generation: str
    ):
        """타인 소유 generation_id → 존재 여부 노출 없이 404."""
        resp = await client.get(
            f"/api/v1/generate/{seeded_generation}/status",
            headers=other_auth_headers,
        )
        assert resp.status_code == 404

    async def test_owner_gets_status(
        self, client: AsyncClient, auth_headers: dict, seeded_generation: str
    ):
        resp = await client.get(
            f"/api/v1/generate/{seeded_generation}/status", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["generation_id"] == seeded_generation
        assert data["status"] == "in_progress"
        assert data["progress"] == 30


# ---------------------------------------------------------------------------
# DELETE /api/v1/generate/{generation_id}
# ---------------------------------------------------------------------------


class TestCancelGeneration:
    """DELETE /api/v1/generate/{generation_id}"""

    async def test_no_auth_returns_401(self, client: AsyncClient, seeded_generation: str):
        resp = await client.delete(f"/api/v1/generate/{seeded_generation}")
        assert resp.status_code == 401

    async def test_nonexistent_gen_id_returns_404(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/generate/gen_notexist", headers=auth_headers)
        assert resp.status_code == 404

    async def test_other_users_gen_returns_404(
        self, client: AsyncClient, other_auth_headers: dict, seeded_generation: str
    ):
        resp = await client.delete(
            f"/api/v1/generate/{seeded_generation}", headers=other_auth_headers
        )
        assert resp.status_code == 404

    async def test_owner_can_cancel(
        self, client: AsyncClient, auth_headers: dict, seeded_generation: str
    ):
        resp = await client.delete(f"/api/v1/generate/{seeded_generation}", headers=auth_headers)
        assert resp.status_code == 204
        assert gen_module._generation_states[seeded_generation].status == "cancelled"


# ---------------------------------------------------------------------------
# WS /api/v1/generate/ws/{generation_id}
# ---------------------------------------------------------------------------


class TestGenerationWebSocket:
    """WS /api/v1/generate/ws/{generation_id}"""

    def _sync_client(self):
        """WebSocket 테스트용 동기 TestClient (의존성 오버라이드 유지)."""
        from app.backend.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_no_token_rejected(self, seeded_generation: str):
        """?token 파라미터 없으면 1008로 거부."""
        with pytest.raises((WebSocketDisconnect, Exception)):
            with self._sync_client().websocket_connect(f"/api/v1/generate/ws/{seeded_generation}"):
                pass

    def test_invalid_token_rejected(self, seeded_generation: str):
        """잘못된 토큰은 1008로 거부."""
        with pytest.raises((WebSocketDisconnect, Exception)):
            with self._sync_client().websocket_connect(
                f"/api/v1/generate/ws/{seeded_generation}?token=invalid.token.here"
            ):
                pass

    def test_other_user_token_rejected(self, seeded_generation: str, other_token: str):
        """소유자가 아닌 사용자의 토큰은 1008로 거부."""
        with pytest.raises((WebSocketDisconnect, Exception)):
            with self._sync_client().websocket_connect(
                f"/api/v1/generate/ws/{seeded_generation}?token={other_token}"
            ):
                pass

    def test_owner_token_accepted(self, seeded_generation: str, test_token: str):
        """소유자 토큰은 정상 연결 수락."""
        with self._sync_client().websocket_connect(
            f"/api/v1/generate/ws/{seeded_generation}?token={test_token}"
        ) as ws:
            # 연결이 수락되었으면 여기까지 도달
            assert ws is not None
