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
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

# Agent config를 먼저 로드하여 load_dotenv() 실행
from agent.core.config import agent_config  # noqa: F401
from agent.monitoring.langsmith_setup import setup_langsmith
from app.backend.api.v1 import api_router
from app.backend.core.config import loaded_env_file_path, settings
from app.backend.db.session import check_database_connection, init_db
from app.backend.services.s3_game_storage import check_s3_bucket_access
from app.backend.utils.discord_alerts import extract_request_context, send_discord_error_alert
from shared.logging_config import setup_logging

logger = logging.getLogger(__name__)


class RequestIdASGIMiddleware:
    """BaseHTTPMiddleware 대신 순수 ASGI — 예외 시 uvicorn 이중 트레이스백 로그 완화."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("x-request-id", request_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)


async def _cleanup_db_orphan_folders() -> None:
    """DB에 game_id 레코드가 없는 game 폴더를 startup 시 삭제 (로컬/S3 공통).

    S3 모드에서는 DB에 없는 폴더를 S3 업로드 없이 바로 삭제한다.
    S3에 저장된 데이터는 delete_project 호출 시 S3에서도 삭제되므로,
    DB 레코드가 없다면 해당 프로젝트는 이미 삭제된 것으로 간주한다.
    """
    from sqlalchemy import select

    from app.backend.db.session import _async_session
    from app.backend.models.game import Project

    storage_path = Path(settings.STORAGE_PATH).resolve()
    if not storage_path.is_dir():
        return
    if _async_session is None:
        logger.debug("[Orphan] DB 세션 없음 — 건너뜀")
        return

    try:
        async with _async_session() as session:
            result = await session.execute(select(Project.game_id))
            db_game_ids: set[str] = set(result.scalars().all())
    except Exception:
        logger.warning("[Orphan] DB 조회 실패 — 건너뜀", exc_info=True)
        return

    orphan_dirs = [
        child
        for child in storage_path.iterdir()
        if child.is_dir() and child.name.startswith("game_") and child.name not in db_game_ids
    ]
    if not orphan_dirs:
        return

    logger.info("[Orphan] DB에 없는 game 폴더 %d개 발견, 정리 시작", len(orphan_dirs))
    for orphan_dir in orphan_dirs:
        try:
            shutil.rmtree(orphan_dir)
            logger.info("[Orphan] 삭제 완료 | %s", orphan_dir.name)
        except Exception:
            logger.warning("[Orphan] 삭제 실패 | %s", orphan_dir.name, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Re:Verse Backend Starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info("Env file (DISCORD 등은 이 파일·쉘 환경변수에서 로드): %s", loaded_env_file_path())
    if (settings.DISCORD_WEBHOOK_URL or "").strip():
        logger.info(
            "Discord error alerts: ON (DISCORD_WEBHOOK_URL 길이=%s자)",
            len(settings.DISCORD_WEBHOOK_URL.strip()),
        )
    else:
        logger.info(
            "Discord error alerts: OFF — DISCORD_WEBHOOK_URL 비어 있음. "
            "`.env`에 `#`로 주석 처리돼 있으면 로드되지 않습니다(주석 제거). "
            "배포 시에는 GitHub Actions 시크릿 ENV_FILE(또는 EC2 `.env.production`)에 URL을 넣으세요."
        )
    if (settings.DISCORD_TOKEN_WEBHOOK_URL or "").strip():
        logger.info(
            "Discord token/cost alerts: ON (DISCORD_TOKEN_WEBHOOK_URL 길이=%s자)",
            len(settings.DISCORD_TOKEN_WEBHOOK_URL.strip()),
        )
    else:
        logger.info(
            "Discord token/cost alerts: OFF — DISCORD_TOKEN_WEBHOOK_URL 비어 있음 "
            "(채팅 에이전트·맵 생성 워크플로 한 실행당 토큰 요약)."
        )
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

    # DB에 없는 orphan game 폴더 정리 (로컬/S3 공통)
    await _cleanup_db_orphan_folders()

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

    # SQLite WAL checkpoint 보장: engine.dispose()로 연결을 정상 종료
    # dispose() 없이 프로세스가 죽으면 WAL → main DB checkpoint가 실행되지 않아
    # 재시작 시 커밋된 데이터가 소실될 수 있음
    from app.backend.db.session import get_engine

    engine = get_engine()
    if engine is not None:
        try:
            await engine.dispose()
            logger.info("DB engine disposed (WAL checkpoint 완료)")
        except Exception:
            logger.warning("DB engine dispose 실패", exc_info=True)


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
app.add_middleware(RequestIdASGIMiddleware)


# ── 글로벌 예외 핸들러 ────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 트레이스백은 여기 한 곳만: shared.logging_config에서 uvicorn.error의
    # "Exception in ASGI application" 중복 로그를 필터링한다.
    logger.error("Unhandled error: %s", exc, exc_info=True)

    # Discord 웹훅 (DISCORD_WEBHOOK_URL 설정 시만). 헬스체크 노이즈 제외.
    if settings.DISCORD_WEBHOOK_URL and not request.url.path.startswith("/health"):
        try:
            ctx = await extract_request_context(request, exc)
            await send_discord_error_alert(ctx)
        except Exception:
            logger.warning("Discord error alert 실패 (무시)", exc_info=True)

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
    # 2) data/ 요청이면 base_game fallback 건너뛰고 S3로 직행
    #    (로컬 삭제 후 base_game 초기 데이터가 반환되는 문제 방지)
    if settings.STORAGE_BACKEND == "s3" and path.startswith("data/"):
        s3_prefix = settings.S3_PREFIX.strip("/")
        s3_key = f"{s3_prefix}/{game_id}/{path}"
        s3_url = (
            f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        )
        return RedirectResponse(url=s3_url, status_code=302)
    # 3) base_game 공유 에셋 (img, js, css, audio 등 — data/ 제외)
    base_file = Path(settings.BASE_GAME_PATH).resolve() / path
    if base_file.is_file():
        return FileResponse(str(base_file))
    # 4) S3 redirect fallback (EC2에 base_game 없을 때)
    if settings.STORAGE_BACKEND == "s3":
        s3_prefix = settings.S3_PREFIX.strip("/")
        s3_key = f"{s3_prefix}/base_game/{path}"
        s3_url = (
            f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        )
        return RedirectResponse(url=s3_url, status_code=302)
    raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
