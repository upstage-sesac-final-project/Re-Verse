"""테스트 공통 fixtures — file-based SQLite + TestClient + 인증 헬퍼."""

import os

# main.py가 import 시 agent 패키지를 참조하므로 미리 mock
import tempfile
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

_test_storage = tempfile.mkdtemp(prefix="reverse_test_games_")
_test_base = tempfile.mkdtemp(prefix="reverse_test_base_")

# 파일 기반 임시 SQLite: event loop 간 커넥션 공유 문제를 방지한다.
# (sync TestClient 내부에서 별도 event loop가 생성되어도 동일 DB 파일에 접근 가능)
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="reverse_test_")
os.close(_TEST_DB_FD)

with patch.dict(
    os.environ,
    {
        "JWT_SECRET_KEY": "test-secret-key-for-testing",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TEST_DB_PATH}",
        "STORAGE_PATH": _test_storage,
        "BASE_GAME_PATH": _test_base,
    },
):
    with patch("agent.monitoring.langsmith_setup.setup_langsmith"):
        from app.backend.core.security import create_access_token, hash_password
        from app.backend.db.base import Base
        from app.backend.db.session import get_db
        from app.backend.main import app
        from app.backend.models.game import Project
        from app.backend.models.user import User

# NullPool: 커넥션을 pool에 보관하지 않고 매번 새로 열고 닫는다.
# sync TestClient(별도 event loop)에서 pytest event loop의 커넥션을 재사용하다
# 발생하는 "no active connection" 오류를 방지한다.
TEST_ENGINE = create_async_engine(
    f"sqlite+aiosqlite:///{_TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
TestSessionLocal = async_sessionmaker(TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    """매 테스트마다 테이블 생성/삭제."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """테스트에서 직접 DB를 조작할 때 사용."""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient (FastAPI TestClient 대체)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """기본 테스트 유저 생성."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    """소유권 테스트용 다른 유저."""
    user = User(
        username="otheruser",
        email="other@example.com",
        hashed_password=hash_password("otherpassword123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """test_user의 JWT Bearer 헤더."""
    token = create_access_token({"sub": str(test_user.id), "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers(other_user: User) -> dict[str, str]:
    """other_user의 JWT Bearer 헤더."""
    token = create_access_token({"sub": str(other_user.id), "email": other_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_project(db_session: AsyncSession, test_user: User) -> Project:
    """기본 테스트 프로젝트 생성 (파일 시스템 복사 없이 DB만)."""
    project = Project(
        user_id=test_user.id,
        name="Test Project",
        description="A test project",
        game_id="game_test_001",
        status="draft",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project
