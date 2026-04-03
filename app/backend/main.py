"""
Re:Verse Backend - FastAPI 진입점

Docker(EC2)에서 `uvicorn app.backend.main:app` 으로 실행됩니다.
프론트(Vercel https://re-verse.ai.kr)는 `vercel.json` rewrites로
`/api` -> `https://api.re-verse.ai.kr` 로 프록시합니다.
"""

# ruff: noqa: E402
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Agent config를 먼저 로드하여 load_dotenv() 실행
from agent.core.config import agent_config  # noqa: F401
from agent.monitoring.langsmith_setup import setup_langsmith
from app.backend.api.v1 import api_router
from app.backend.core.config import settings
from app.backend.db.session import check_database_connection, init_db
from app.backend.services.s3_game_storage import check_s3_bucket_access
from shared.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Re:Verse Backend Starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"Storage: backend={settings.STORAGE_BACKEND}, path={settings.STORAGE_PATH}")

    # 게임 정적 서빙/에이전트가 쓸 디렉터리 보장
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    # DB 테이블 생성 (checkfirst=True, 기존 데이터 보존)
    await init_db()

    setup_langsmith()

    yield

    # Shutdown
    logger.info("Re:Verse Backend Shutting down...")


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


# ── 미들웨어 ──────────────────────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Request ID 추적 (프로덕션 디버깅용)."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── 글로벌 예외 핸들러 ────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/health")
async def health_check():
    """Docker HEALTHCHECK 및 로드밸런서용 기본 헬스."""
    return {"status": "healthy", "message": "Re:Verse Backend is running"}


@app.get("/health/db")
async def health_database():
    """RDS 연결 확인. DATABASE_URL 미설정 시 skipped."""
    ok, detail = await check_database_connection()
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

# 게임 뷰어: 로컬/EC2 모두 STORAGE_PATH 아래 파일을 그대로 서빙
app.mount(
    "/game",
    StaticFiles(directory=settings.STORAGE_PATH, html=True),
    name="game",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
