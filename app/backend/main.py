"""
Re:Verse Backend - FastAPI 진입점

이 파일은 Docker 컨테이너에서 uvicorn app.backend.main:app으로 실행되는 진입점입니다.
실제 구현 시 FastAPI 앱을 여기에 정의해야 합니다.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title="Re:Verse API",
    description="AI-powered RPG game creation tool using natural language",
    version="0.1.0",
)

# CORS 설정 (Vercel 프론트엔드와의 통신을 위해)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 로컬 프론트엔드
        "https://*.vercel.app",  # Vercel 배포된 프론트엔드
    ],
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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
