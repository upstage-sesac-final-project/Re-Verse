# Re:Verse Backend - FastAPI, Python 3.12, uv
# EC2에서 단독 실행용
# 빌드 컨텍스트: 프로젝트 루트 (Re-Verse/)

# ------------------------------------------------------------
# Stage 1: RPG Maker MZ MCP 서버 빌드 (Node)
# - stdio MCP는 백엔드 컨테이너 내부에 실행파일이 있어야 함
# - 여기서 git clone + build를 수행하고, 런타임 이미지로 산출물만 복사한다.
# ------------------------------------------------------------
FROM node:20-alpine AS mcp-builder
WORKDIR /mcp
RUN apk add --no-cache git
RUN git clone https://github.com/k4zuki0539/-rpgmaker-mz-mcp.git .
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치 (DB 빌드 도구 및 MCP용 Node.js 포함)
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# MCP 빌드 산출물을 런타임 이미지에 포함 (컨테이너 내부 경로 기준)
# - MCP_NODE_SERVER_PATH는 기본적으로 아래 경로를 가리키게 설정한다.
COPY --from=mcp-builder /mcp /app/mcp-server
ENV MCP_NODE_SERVER_PATH=/app/mcp-server/dist/index.js

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
