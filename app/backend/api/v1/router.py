"""API 엔드포인트 정의"""

from fastapi import APIRouter

from app.backend.api.v1.endpoints import admin, auth, docs, games, llm

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(games.router, prefix="/games", tags=["Games"])
api_router.include_router(llm.router, prefix="/llm", tags=["LLM"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(docs.router, prefix="/docs", tags=["Docs"])
