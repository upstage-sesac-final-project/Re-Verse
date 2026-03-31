"""Auth Service — 회원가입, 로그인, 토큰 갱신, 로그아웃."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    revoke_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.backend.models.user import User
from app.backend.schemas.auth import TokenResponse


class AuthService:
    async def _issue_tokens(self, user: User, db: AsyncSession) -> TokenResponse:
        """access + refresh token 발급 공통 로직."""
        access_token = create_access_token({"sub": str(user.id), "email": user.email})
        refresh_token = await create_refresh_token(user.id, db)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
            user_id=user.id,
            username=user.username,
            is_admin=getattr(user, "is_admin", False),
        )

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        db: AsyncSession,
    ) -> TokenResponse:
        """회원가입 — 이메일 중복 확인 후 JWT + refresh token 즉시 발급."""
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 등록된 이메일입니다.",
            )

        is_admin = bool(settings.ADMIN_EMAIL and email == settings.ADMIN_EMAIL)
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_admin=is_admin,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return await self._issue_tokens(user, db)

    async def login(
        self,
        email: str,
        password: str,
        db: AsyncSession,
    ) -> TokenResponse:
        """로그인 — 이메일 + 비밀번호 검증 후 JWT + refresh token 발급."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        return await self._issue_tokens(user, db)

    async def refresh(
        self,
        refresh_token_str: str,
        db: AsyncSession,
    ) -> TokenResponse:
        """토큰 갱신 — refresh token으로 새 access + refresh token 발급 (rotation)."""
        old_refresh = await verify_refresh_token(refresh_token_str, db)

        old_refresh.revoked = True
        await db.commit()

        result = await db.execute(select(User).where(User.id == old_refresh.user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="사용자를 찾을 수 없습니다.",
            )

        return await self._issue_tokens(user, db)

    async def logout(
        self,
        refresh_token_str: str,
        db: AsyncSession,
    ) -> None:
        """로그아웃 — refresh token 폐기."""
        await revoke_refresh_token(refresh_token_str, db)


auth_service = AuthService()
