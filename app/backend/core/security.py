"""JWT 인증 + 비밀번호 해싱 + Refresh Token."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.db.session import get_db
from app.backend.models.user import User
from shared.log_context import set_current_user

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _pre_hash(password: str) -> bytes:
    """SHA-256 pre-hash (bcrypt 72바이트 한도 우회)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(_pre_hash(plain_password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_pre_hash(plain_password), hashed.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        logger.warning("[Security] access token 디코딩 실패")
        return None


async def create_refresh_token(user_id: int, db: AsyncSession) -> str:
    """Refresh token 생성 후 DB 저장."""
    from app.backend.repositories.refresh_token_repository import refresh_token_repository

    token = secrets.token_urlsafe(64)
    await refresh_token_repository.create(token=token, user_id=user_id, db=db)
    return token


async def verify_refresh_token(token: str, db: AsyncSession):
    """Refresh token 검증 — 유효하면 RefreshToken 반환, 아니면 401."""
    from app.backend.repositories.refresh_token_repository import refresh_token_repository

    refresh = await refresh_token_repository.find_by_token(token, db)
    if refresh is None or refresh.revoked:
        logger.warning("[Security] 유효하지 않은 refresh token 사용 시도")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 refresh token입니다.",
        )
    expires_at = refresh.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        logger.warning("[Security] 만료된 refresh token 사용 시도 | user_id=%d", refresh.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="만료된 refresh token입니다.",
        )
    return refresh


async def revoke_refresh_token(token: str, db: AsyncSession) -> None:
    """Refresh token 폐기."""
    from app.backend.repositories.refresh_token_repository import refresh_token_repository

    refresh = await refresh_token_repository.find_by_token(token, db)
    if refresh is not None:
        await refresh_token_repository.revoke(refresh, db)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    from app.backend.repositories.user_repository import user_repository

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if user_id is None:
        logger.warning("[Security] 토큰에 사용자 정보(sub) 없음")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 정보가 없습니다.",
        )
    user = await user_repository.find_by_id(int(user_id), db)
    if user is None:
        logger.warning("[Security] 토큰의 사용자가 DB에 없음 | user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )
    # 로깅 컨텍스트에 유저 정보 설정 (이후 로그에 username_id 자동 포함)
    set_current_user(user.username, user.id)
    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """관리자 전용 의존성 — is_admin=False면 403."""
    if not getattr(current_user, "is_admin", False):
        logger.warning("[Security] 관리자 권한 없음 | user_id=%d", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
    return current_user
