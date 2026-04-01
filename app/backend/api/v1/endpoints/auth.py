"""인증 엔드포인트 — 회원가입, 로그인, 토큰 갱신, 로그아웃, /me."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.security import get_current_user
from app.backend.db.session import get_db
from app.backend.models.user import User
from app.backend.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.backend.services.auth_service import auth_service

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """회원가입 — 이메일 중복 확인 후 JWT + refresh token 즉시 발급."""
    return await auth_service.register(
        username=request.username,
        email=request.email,
        password=request.password,
        db=db,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """로그인 — 이메일 + 비밀번호 검증 후 JWT + refresh token 발급."""
    return await auth_service.login(
        email=request.email,
        password=request.password,
        db=db,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """토큰 갱신 — refresh token으로 새 access + refresh token 발급 (rotation)."""
    return await auth_service.refresh(
        refresh_token_str=request.refresh_token,
        db=db,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """로그아웃 — refresh token 폐기."""
    await auth_service.logout(
        refresh_token_str=request.refresh_token,
        db=db,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """현재 로그인 사용자 정보 조회."""
    return current_user
