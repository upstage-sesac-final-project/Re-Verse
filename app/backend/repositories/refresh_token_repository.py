"""RefreshToken Repository — 리프레시 토큰 DB 접근 계층."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    async def create(
        self,
        token: str,
        user_id: int,
        db: AsyncSession,
    ) -> RefreshToken:
        expires_at = datetime.now(UTC) + timedelta(hours=settings.REFRESH_TOKEN_EXPIRATION_HOURS)
        refresh = RefreshToken(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
        )
        db.add(refresh)
        await db.commit()
        return refresh

    async def find_by_token(self, token: str, db: AsyncSession) -> RefreshToken | None:
        result = await db.execute(select(RefreshToken).where(RefreshToken.token == token))
        return result.scalar_one_or_none()

    async def revoke(self, refresh: RefreshToken, db: AsyncSession) -> None:
        refresh.revoked = True
        await db.commit()


refresh_token_repository = RefreshTokenRepository()
