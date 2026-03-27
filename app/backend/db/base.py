"""SQLAlchemy 선언적 베이스 (향후 Alembic/모델 확장 시 사용)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
