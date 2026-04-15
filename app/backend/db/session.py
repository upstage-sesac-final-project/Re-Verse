"""DB 세션 (Async SQLAlchemy).

DATABASE_URL이 비어 있으면 엔진을 만들지 않으며, 앱은 DB 없이도 기동할 수 있습니다.
dev: sqlite+aiosqlite:///./storage/reverse.db
prod: postgresql+psycopg://user:pass@host:5432/dbname
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.backend.core.config import settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_async_session: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine | None:
    """DATABASE_URL이 있을 때만 엔진 생성(지연 초기화)."""
    global _engine, _async_session
    if _engine is not None:
        return _engine
    if not settings.DATABASE_URL or not settings.DATABASE_URL.strip():
        return None

    connect_args: dict = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    is_sqlite = settings.DATABASE_URL.startswith("sqlite")
    _engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args=connect_args,
        # SQLite: 동시 읽기 허용, 쓰기만 직렬화. PostgreSQL: 풀 확장.
        pool_size=5 if is_sqlite else 10,
        max_overflow=5 if is_sqlite else 20,
        pool_recycle=300,
        pool_pre_ping=True,
        pool_timeout=30,
    )
    _async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # SQLite WAL 모드: 읽기/쓰기 동시 접근 허용
    if is_sqlite:

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    logger.info("AsyncSQLAlchemy engine 초기화 완료")
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 async DB 세션 제너레이터."""
    get_engine()
    if _async_session is None:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다.")
    async with _async_session() as session:
        yield session


async def init_db() -> None:
    """테이블 생성 (checkfirst=True, 기존 데이터 보존)."""
    import app.backend.models  # noqa: F401 — metadata에 모델 등록
    from app.backend.db.base import Base

    engine = get_engine()
    if engine is None:
        logger.warning("DATABASE_URL 미설정 — 테이블 생성 건너뜀")
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB 테이블 생성/확인 완료")


async def check_database_connection() -> tuple[bool, str]:
    """헬스체크: SELECT 1."""
    engine = get_engine()
    if engine is None:
        return True, "skipped (DATABASE_URL empty)"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:
        return False, str(e)
