"""인증 API 테스트 — 회원가입, 로그인, 토큰 갱신, 로그아웃, /me."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.refresh_token import RefreshToken
from app.backend.models.user import User


class TestRegister:
    """POST /api/v1/auth/register"""

    async def test_register_success(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@example.com",
                "password": "securepass123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["username"] == "newuser"
        assert data["user_id"] > 0
        assert data["expires_in"] > 0

    async def test_register_duplicate_email(self, client: AsyncClient, test_user: User):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "another",
                "email": test_user.email,
                "password": "securepass123",
            },
        )
        assert resp.status_code == 409

    async def test_register_short_password(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "user",
                "email": "short@example.com",
                "password": "1234567",  # min_length=8
            },
        )
        assert resp.status_code == 422

    async def test_register_short_username(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "a",  # min_length=2
                "email": "short@example.com",
                "password": "securepass123",
            },
        )
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "user",
                "email": "not-an-email",
                "password": "securepass123",
            },
        )
        assert resp.status_code == 422


class TestLogin:
    """POST /api/v1/auth/login"""

    async def test_login_success(self, client: AsyncClient, test_user: User):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["user_id"] == test_user.id
        assert data["username"] == test_user.username

    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "somepassword123",
            },
        )
        assert resp.status_code == 401


class TestRefresh:
    """POST /api/v1/auth/refresh"""

    async def test_refresh_success(self, client: AsyncClient, test_user: User):
        """refresh token으로 새 access + refresh token 발급."""
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123",
            },
        )
        old_refresh = login_resp.json()["refresh_token"]
        old_access = login_resp.json()["access_token"]  # noqa : F841

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": old_refresh,
            },
        )
        assert refresh_resp.status_code == 200
        data = refresh_resp.json()
        assert data["access_token"]
        assert data["refresh_token"]
        # rotation: 새 refresh token은 이전과 달라야 함
        assert data["refresh_token"] != old_refresh
        assert data["user_id"] == test_user.id

    async def test_refresh_revokes_old_token(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """refresh 후 기존 token은 폐기(revoked) 상태."""
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123",
            },
        )
        old_refresh = login_resp.json()["refresh_token"]

        await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": old_refresh,
            },
        )

        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.token == old_refresh)
        )
        token_row = result.scalar_one()
        assert token_row.revoked is True

    async def test_refresh_reuse_revoked_token(self, client: AsyncClient, test_user: User):
        """폐기된 refresh token 재사용 시 401."""
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123",
            },
        )
        old_refresh = login_resp.json()["refresh_token"]

        # 1차 refresh (성공, old token 폐기)
        await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": old_refresh,
            },
        )

        # 2차 refresh (폐기된 토큰 재사용 → 401)
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": old_refresh,
            },
        )
        assert resp.status_code == 401

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": "invalid-token-value",
            },
        )
        assert resp.status_code == 401

    async def test_refresh_new_access_token_works(self, client: AsyncClient, test_user: User):
        """갱신된 access token으로 /me 접근 가능."""
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123",
            },
        )

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": login_resp.json()["refresh_token"],
            },
        )
        new_token = refresh_resp.json()["access_token"]

        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["id"] == test_user.id


class TestLogout:
    """POST /api/v1/auth/logout"""

    async def test_logout_success(self, client: AsyncClient, test_user: User):
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123",
            },
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/logout",
            json={
                "refresh_token": refresh_token,
            },
        )
        assert resp.status_code == 204

        # 로그아웃 후 refresh 시도 → 401
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": refresh_token,
            },
        )
        assert resp.status_code == 401

    async def test_logout_invalid_token_no_error(self, client: AsyncClient):
        """존재하지 않는 token으로 logout해도 에러 없음."""
        resp = await client.post(
            "/api/v1/auth/logout",
            json={
                "refresh_token": "nonexistent-token",
            },
        )
        assert resp.status_code == 204


class TestMe:
    """GET /api/v1/auth/me"""

    async def test_me_success(self, client: AsyncClient, test_user: User, auth_headers: dict):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == test_user.id
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email

    async def test_me_no_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    async def test_register_then_access_me(self, client: AsyncClient):
        """회원가입으로 받은 토큰으로 /me 접근."""
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "flowuser",
                "email": "flow@example.com",
                "password": "flowpass1234",
            },
        )
        token = reg_resp.json()["access_token"]

        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "flow@example.com"
