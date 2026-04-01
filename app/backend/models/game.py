"""Project & ConversationLog 모델."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    game_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="draft"
    )  # 개발중 : draft , 공유 가능(배포됨) : published
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user = relationship("User", back_populates="projects")
    conversation_logs = relationship(
        "ConversationLog", back_populates="project", cascade="all, delete-orphan"
    )


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), index=True, nullable=False
    )
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    agent_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    modified_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    changes_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    processing_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    project = relationship("Project", back_populates="conversation_logs")
