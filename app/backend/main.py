"""
Re:Verse Backend - FastAPI 진입점

Docker(EC2)에서 `uvicorn app.backend.main:app` 으로 실행됩니다.
프론트(Vercel https://re-verse.ai.kr)는 `vercel.json` rewrites로
`/api` -> `https://api.re-verse.ai.kr` 로 프록시합니다.
"""

# ruff: noqa: E402
import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

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

    # Orphan 정리: 이전 비정상 종료로 남아있는 game 폴더 → S3 업로드 후 삭제
    if settings.STORAGE_BACKEND == "s3":
        from app.backend.services.s3_game_storage import sync_game_to_s3
        from app.backend.services.session_manager import get_orphan_game_ids

        storage_path = Path(settings.STORAGE_PATH).resolve()
        orphans = get_orphan_game_ids(storage_path)
        if orphans:
            logger.info("Orphan cleanup: %d 개 폴더 발견", len(orphans))
        for game_id in orphans:
            orphan_dir = storage_path / game_id
            try:
                sync_game_to_s3(game_id)
                shutil.rmtree(orphan_dir)
                logger.info("Orphan cleanup: S3 업로드 + 삭제 완료 | %s", game_id)
            except Exception:
                logger.warning("Orphan cleanup 실패, 폴더 삭제 | %s", game_id)
                shutil.rmtree(orphan_dir, ignore_errors=True)

    # DB 테이블 생성 (checkfirst=True, 기존 데이터 보존)
    await init_db()

    setup_langsmith()

    # 주기적 인메모리 상태 정리 (60초마다)
    async def _periodic_cleanup():
        from app.backend.api.v1.endpoints.generation import _cleanup_stale_states

        while True:
            await asyncio.sleep(60)
            try:
                _cleanup_stale_states()
            except Exception:
                pass

    cleanup_task = asyncio.create_task(_periodic_cleanup())

    yield

    cleanup_task.cancel()

    # Shutdown — 활성 세션 일괄 S3 업로드
    logger.info("Re:Verse Backend Shutting down...")
    if settings.STORAGE_BACKEND == "s3":
        from app.backend.services.s3_game_storage import sync_game_to_s3
        from app.backend.services.session_manager import get_all_active

        active = get_all_active()
        if active:
            logger.info("Shutdown: %d 개 활성 세션 S3 업로드 중...", len(active))
        for game_id in active:
            try:
                sync_game_to_s3(game_id)
                local_dir = Path(settings.STORAGE_PATH).resolve() / game_id
                if local_dir.is_dir():
                    shutil.rmtree(local_dir)
                logger.info("Shutdown: S3 업로드 + 정리 완료 | %s", game_id)
            except Exception:
                logger.error("Shutdown: S3 업로드 실패 | %s", game_id, exc_info=True)


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


# 게임 뷰어: data/는 프로젝트별 파일, 나머지는 base_game 공유 에셋으로 서빙
@app.get("/game/{game_id}/{path:path}")
async def serve_game_file(game_id: str, path: str):
    """프로젝트별 data/ → base_game fallback 순으로 게임 파일 서빙."""
    if not path:
        path = "index.html"
    # 1) 프로젝트별 파일 (data/ JSON 등)
    project_file = Path(settings.STORAGE_PATH).resolve() / game_id / path
    if project_file.is_file():
        return FileResponse(str(project_file))
    # 2) base_game 공유 에셋 (img, js, css, audio 등)
    base_file = Path(settings.BASE_GAME_PATH).resolve() / path
    if base_file.is_file():
        return FileResponse(str(base_file))
    # 3) S3 redirect fallback (EC2에 base_game 없을 때)
    if settings.STORAGE_BACKEND == "s3":
        s3_prefix = settings.S3_PREFIX.strip("/")
        if path.startswith("data/"):
            s3_key = f"{s3_prefix}/{game_id}/{path}"
        else:
            s3_key = f"{s3_prefix}/base_game/{path}"
        s3_url = (
            f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        )
        return RedirectResponse(url=s3_url, status_code=302)
    raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
