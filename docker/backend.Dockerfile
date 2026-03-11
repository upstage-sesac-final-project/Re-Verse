# Re:Verse Backend - FastAPI, Python 3.12, uv
# EC2에서 단독 실행용
# 빌드 컨텍스트: 프로젝트 루트 (Re-Verse/)

FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치 (필요시)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
RUN pip install --no-cache-dir uv

# 의존성 파일 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./

# 패키지 및 앱 코드 복사
COPY app/backend ./app/backend
COPY agent ./agent
COPY shared ./shared

# 의존성 설치 (프로덕션 환경)
RUN uv sync --frozen --no-dev

# 헬스체크 엔드포인트
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# FastAPI 앱 실행
CMD ["uv", "run", "uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
