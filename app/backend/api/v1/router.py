"""
API 엔드포인트 정의
llm.py : Agent 요청 API
"""

from fastapi import APIRouter

from app.backend.api.v1.endpoints import llm

api_router = APIRouter()
api_router.include_router(llm.router, prefix="/llm", tags=["LLM"])
