"""RDS(PostgreSQL) 연결 세션.

DATABASE_URL이 비어 있으면 엔진을 만들지 않으며, 앱은 DB 없이도 기동할 수 있습니다.
프로덕션 .env에는 GitHub Secret ENV_FILE로 주입한 연결 문자열을 넣습니다.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.backend.core.config import settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine | None:
    """DATABASE_URL이 있을 때만 엔진 생성(지연 초기화)."""
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine
    if not settings.DATABASE_URL or not settings.DATABASE_URL.strip():
        return None
    _engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    logger.info("SQLAlchemy engine 초기화 완료")
    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends용 DB 세션 제너레이터."""
    get_engine()
    if _SessionLocal is None:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다.")
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> tuple[bool, str]:
    """헬스체크: SELECT 1."""
    eng = get_engine()
    if eng is None:
        return True, "skipped (DATABASE_URL empty)"
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as e:
        return False, str(e)
