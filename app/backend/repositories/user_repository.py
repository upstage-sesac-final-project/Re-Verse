"""User Repository — 사용자 DB 접근 계층."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.user import User


class UserRepository:
    async def find_by_email(self, email: str, db: AsyncSession) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def find_by_id(self, user_id: int, db: AsyncSession) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        username: str,
        email: str,
        hashed_password: str,
        db: AsyncSession,
    ) -> User:
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


user_repository = UserRepository()
