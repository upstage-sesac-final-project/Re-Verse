# syntax=docker/dockerfile:1
# Re:Verse Backend - FastAPI, Python 3.12, uv
# EC2에서 단독 실행용
# 빌드 컨텍스트: 프로젝트 루트 (Re-Verse/)

# ------------------------------------------------------------
# Stage 1: 통합 RPG Maker MZ MCP 서버 빌드 (Node)
# - stdio MCP는 백엔드 컨테이너 내부에 실행파일이 있어야 함
# - 단일 리포를 clone + build 후 /mcp/default 로 복사한다.
# ------------------------------------------------------------
FROM node:20-alpine AS mcp-builder
WORKDIR /mcp
RUN apk add --no-cache git bash

ARG MCP_REPO=https://github.com/rein1225/RPGMakerMZ_MCP.git

RUN --mount=type=cache,target=/root/.npm \
    set -eux; \
    git clone --depth 1 "$MCP_REPO" /tmp/src-mcp; \
    cd /tmp/src-mcp; \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi; \
    npm run build; \
    cp -R /tmp/src-mcp/. /mcp/default/

FROM python:3.12-slim

# debconf가 대화형 입력을 기다리지 않도록 설정
# nodesource 설치 스크립트(setup_20.x)가 내부적으로 apt-get을 실행할 때도 적용됨
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 시스템 의존성 설치 (DB 빌드 도구 및 MCP용 Node.js 포함)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# MCP 빌드 산출물을 런타임 이미지에 포함 (컨테이너 내부 경로 기준)
# - 다중 MCP 루트: /app/mcp/<key>
# - 기존 단일 경로 호환: /app/mcp-server -> /app/mcp/default
COPY --from=mcp-builder /mcp /app/mcp
RUN ln -s /app/mcp/default /app/mcp-server
ENV MCP_NODE_SERVER_PATH=/app/mcp-server/dist/index.js

# uv 설치 (pip 캐시 마운트로 반복 빌드 가속)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install uv

# 의존성 파일 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./

# 패키지 및 앱 코드 복사
COPY app/backend ./app/backend
COPY agent ./agent
COPY shared ./shared

# 의존성 설치 (프로덕션 환경)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# 헬스체크 엔드포인트
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# FastAPI 앱 실행
CMD ["uv", "run", "uvicorn", "app.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
