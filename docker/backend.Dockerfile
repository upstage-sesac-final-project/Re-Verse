# Re:Verse Backend - FastAPI, Python 3.12, uv
# EC2에서 단독 실행용
# 빌드 컨텍스트: 프로젝트 루트 (Re-Verse/)

# ------------------------------------------------------------
# Stage 1: RPG Maker MZ MCP 서버 빌드 (Node)
# - stdio MCP는 백엔드 컨테이너 내부에 실행파일이 있어야 함
# - 4개 MCP를 각각 clone + build 후 /mcp/<key> 로 모은다.
# ------------------------------------------------------------
FROM node:20-alpine AS mcp-builder
WORKDIR /mcp
RUN apk add --no-cache git bash

# 기본값은 현재 운영 중인 리포 1개만 지정.
# 나머지 3개는 docker-compose.prod.yml 또는 CI ENV_FILE에서 URL을 주입.
ARG MCP_REPO_DEFAULT=https://github.com/k4zuki0539/-rpgmaker-mz-mcp.git
ARG MCP_REPO_MAKER=
ARG MCP_REPO_LOWER=
ARG MCP_REPO_UNDERSCORE=

RUN set -eux; \
    mkdir -p /mcp/default /mcp/mcp_maker /mcp/rpgmaker_lower /mcp/rpgmaker_underscore; \
    build_one() { \
      key="$1"; \
      url="$2"; \
      if [ -z "$url" ]; then \
        echo "skip $key (repo url empty)"; \
        return 0; \
      fi; \
      work="/tmp/src-$key"; \
      rm -rf "$work"; \
      git clone "$url" "$work"; \
      cd "$work"; \
      if [ -f package-lock.json ]; then npm ci; else npm install; fi; \
      npm run build; \
      cp -R "$work"/. "/mcp/$key/"; \
    }; \
    build_one default "$MCP_REPO_DEFAULT"; \
    build_one mcp_maker "$MCP_REPO_MAKER"; \
    build_one rpgmaker_lower "$MCP_REPO_LOWER"; \
    build_one rpgmaker_underscore "$MCP_REPO_UNDERSCORE"

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
# - 다중 MCP 루트: /app/mcp/<key>
# - 기존 단일 경로 호환: /app/mcp-server -> /app/mcp/default
COPY --from=mcp-builder /mcp /app/mcp
RUN ln -s /app/mcp/default /app/mcp-server
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
