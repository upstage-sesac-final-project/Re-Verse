# syntax=docker/dockerfile:1
# Re:Verse Backend - FastAPI, Python 3.12, uv
# EC2에서 단독 실행용
# 빌드 컨텍스트: 프로젝트 루트 (Re-Verse/)
#
# MCP(Node stdio 서버)는 현재 배포에서 비활성화. executor_v2 dispatch 경로로 처리.
# - MCP 기능 복귀 시: mcp-builder 스테이지 + nodejs 설치 + MCP_NODE_SERVER_PATH를 복원하고
#   `MCP_ENABLED=true` 를 주입한다.

FROM python:3.12-slim

# debconf가 대화형 입력을 기다리지 않도록 설정
ENV DEBIAN_FRONTEND=noninteractive

# MCP 비활성 기본값. docker-compose의 env_file/environment에서 재정의 가능하지만
# 이미지 레벨 기본을 명시해 오작동(= MCP 호출 시 바이너리 없음) 가능성을 낮춘다.
ENV MCP_ENABLED=false

WORKDIR /app

# 시스템 의존성 설치 (DB 빌드 도구)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv 설치 (pip 캐시 마운트로 반복 빌드 가속)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install uv

# 의존성 파일 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./

# 의존성만 먼저 설치 (코드 변경에 영향받지 않는 레이어)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 패키지 및 앱 코드 복사
COPY app/backend ./app/backend
COPY agent ./agent
COPY shared ./shared

# 프로젝트 자체 설치 (코드 변경 시 이 레이어만 재실행)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# 헬스체크 엔드포인트
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# FastAPI 앱 실행
CMD ["uv", "run", "uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
