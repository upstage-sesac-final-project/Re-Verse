"""
Re:Verse Backend - FastAPI 진입점

Docker(EC2)에서 `uvicorn app.backend.main:app` 으로 실행됩니다.
프론트(Vercel https://re-verse.ai.kr)는 `vercel.json` rewrites로 `/api` → `https://api.re-verse.ai.kr` 로 프록시합니다.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from agent.monitoring.langsmith_setup import setup_langsmith
from app.backend.api.v1 import api_router
from app.backend.core.config import settings
from app.backend.db.session import check_database_connection, get_engine
from app.backend.services.s3_game_storage import check_s3_bucket_access


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Re:Verse Backend Starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"Storage: backend={settings.STORAGE_BACKEND}, path={settings.STORAGE_PATH}")

    # 게임 정적 서빙/에이전트가 쓸 디렉터리 보장
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    # DB 엔진 선로딩(선택)
    get_engine()

    setup_langsmith()

    yield

    # Shutdown
    logger.info("👋 Re:Verse Backend Shutting down...")


app = FastAPI(
    title="Re:Verse API",
    description="AI-powered RPG game creation tool using natural language",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Docker HEALTHCHECK 및 로드밸런서용 기본 헬스."""
    return {"status": "healthy", "message": "Re:Verse Backend is running"}


@app.get("/health/db")
async def health_database():
    """RDS 연결 확인. DATABASE_URL 미설정 시 skipped."""
    ok, detail = check_database_connection()
    return {"ok": ok, "detail": detail}


@app.get("/health/s3")
async def health_s3():
    """S3 버킷 접근(IAM). STORAGE_BACKEND=local 이면 skipped."""
    ok, detail = check_s3_bucket_access()
    return {"ok": ok, "detail": detail}


@app.get("/")
async def root():
    return {"message": "Welcome to Re:Verse API", "docs": "/docs", "health": "/health"}


app.include_router(api_router, prefix="/api/v1")

# 게임 뷰어: 로컬/EC2 모두 STORAGE_PATH 아래 파일을 그대로 서빙 (프로덕션은 S3 동기화 후 동일 경로)
app.mount(
    "/game",
    StaticFiles(directory=settings.STORAGE_PATH, html=True),
    name="game",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
