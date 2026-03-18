"""
Re:Verse Backend - FastAPI 진입점

이 파일은 Docker 컨테이너에서 uvicorn app.backend.main:app으로 실행되는 진입점입니다.
실제 구현 시 FastAPI 앱을 여기에 정의해야 합니다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.backend.api.v1 import api_router
from app.backend.core.config import settings


# lifespan 이벤트 : 앱 시작/종료 시 실행
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Re:Verse Backend Starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")

    yield

    # Shutdown
    logger.info("👋 Re:Verse Backend Shutting down...")


# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title="Re:Verse API",
    description="AI-powered RPG game creation tool using natural language",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 설정 (Vercel 프론트엔드와의 통신을 위해)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 헬스체크 엔드포인트 (Docker 헬스체크용)
@app.get("/health")
async def health_check():
    """
    헬스체크 엔드포인트
    Docker 컨테이너의 HEALTHCHECK에서 사용됩니다.
    """
    return {"status": "healthy", "message": "Re:Verse Backend is running"}


# 기본 루트 엔드포인트
@app.get("/")
async def root():
    """
    API 루트 엔드포인트
    """
    return {"message": "Welcome to Re:Verse API", "docs": "/docs", "health": "/health"}


# API 라우터들은 여기서 include 하세요
# 예: app.include_router(llm_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")

# storage/games 정적 파일 서빙 (게임 뷰어용)
app.mount("/game", StaticFiles(directory=settings.STORAGE_PATH, html=True), name="game")

if __name__ == "__main__":
    import uvicorn

    # Production Environment
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    # Development Environment
    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
