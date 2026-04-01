"""Project Repository — 프로젝트 및 대화 로그 DB 접근 계층."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.game import ConversationLog, Project


class ProjectRepository:
    async def count_by_user(self, user_id: int, db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count()).select_from(Project).where(Project.user_id == user_id)
        )
        return result.scalar() or 0

    async def get_max_id(self, db: AsyncSession) -> int:
        result = await db.execute(select(func.max(Project.id)))
        return result.scalar() or 0

    async def create(self, project: Project, db: AsyncSession) -> None:
        db.add(project)
        await db.flush()

    async def commit(self, db: AsyncSession) -> None:
        await db.commit()

    async def rollback(self, db: AsyncSession) -> None:
        await db.rollback()

    async def refresh(self, project: Project, db: AsyncSession) -> None:
        await db.refresh(project)

    async def find_by_id(self, project_id: int, db: AsyncSession) -> Project | None:
        result = await db.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def find_by_user(self, user_id: int, db: AsyncSession) -> list[Project]:
        result = await db.execute(
            select(Project).where(Project.user_id == user_id).order_by(Project.updated_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, project: Project, db: AsyncSession) -> None:
        await db.delete(project)
        await db.commit()

    async def save_conversation_log(
        self,
        db: AsyncSession,
        project_id: int,
        user_input: str,
        agent_response: str | None,
        intent: str | None,
        success: bool,
        processing_time: float,
        error_message: str | None = None,
    ) -> None:
        log = ConversationLog(
            project_id=project_id,
            user_input=user_input,
            agent_response=agent_response,
            intent=intent,
            success=success,
            processing_time=processing_time,
            error_message=error_message,
        )
        db.add(log)
        await db.commit()


project_repository = ProjectRepository()
