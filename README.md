# Re:Verse

Re:Verse는 AI를 이용해 RPG Maker MZ 프로젝트를 수정하고, 그 결과를 바로 확인할 수 있게 만드는 실험용 편집 프로젝트입니다.

현재 저장소는 다음 요소를 함께 포함합니다.

- React/Vite 프런트엔드
- FastAPI 백엔드
- LangGraph 기반 에이전트 파이프라인
- 실제 RPG Maker 프로젝트 파일을 담는 로컬 스토리지

현재 기준의 핵심 흐름은 아래와 같습니다.

1. 편집기 UI에서 요청을 입력합니다.
2. 프런트엔드가 백엔드 LLM 엔드포인트로 요청을 보냅니다.
3. 백엔드와 에이전트가 게임 데이터 수정 작업을 수행합니다.
4. 내장된 게임 뷰어, 맵 뷰어, 데이터 뷰어에서 결과를 확인합니다.

## 현재 저장소 구조

아래 트리는 캐시나 생성물보다 실제 소스와 실행에 중요한 경로 위주로 정리한 것입니다.

```text
.
|- agent/
|  |- core/                # LLM 클라이언트와 에이전트 설정
|  |- graph/               # LangGraph 워크플로우, 상태, 노드
|  |- monitoring/          # LangSmith 설정
|  |- prompts/             # planner/router/executor 프롬프트와 예시
|  |- rag/                 # retriever, embeddings, vector store 관련 코드
|  |- schemas/             # RPG Maker 중심 스키마 정의
|  |- tests/               # 에이전트 및 통합 테스트
|  `- utils/
|- app/
|  |- backend/
|  |  |- api/v1/           # FastAPI 라우터와 엔드포인트
|  |  |- core/             # 설정, 의존성, 보안, 게임 경로
|  |  |- db/               # DB 세션과 엔진 헬퍼
|  |  |- models/           # 도메인/DB 모델
|  |  |- rpgmaker/         # RPG Maker 파일 관리, 파서, 검증, 템플릿
|  |  |- schemas/          # API 요청/응답 스키마
|  |  |- services/         # LLM, 게임, 스토리지, 시나리오 서비스
|  |  |- tests/            # 백엔드 테스트
|  |  `- utils/
|  `- frontend/
|     |- public/
|     |- src/
|     |  |- components/    # 채팅, 게임 미리보기, 레이아웃 컴포넌트
|     |  |- hooks/
|     |  |- pages/
|     |  |- services/      # 프런트 API 클라이언트
|     |  |- store/
|     |  `- utils/
|     |- package.json
|     `- vite.config.js
|- docker/
|  |- backend.Dockerfile
|  |- frontend.Dockerfile
|  `- nginx.conf
|- docs/
|  |- API.md
|  |- AWS_ENV_SETUP.md
|  |- PROGRESS.md
|  |- RPGMAKER_STRUCTURE.md
|  |- RPGMAKER_TILE_RENDERING.md
|  `- SETUP.md
|- scripts/
|  |- deploy.sh
|  |- init_rpgmaker.sh
|  `- setup.sh
|- shared/
|  |- constants/           # Python/TypeScript 공용 상수
|  `- types/               # Python/TypeScript 공용 타입
|- storage/
|  |- games/
|  |  `- game_001/         # 현재 앱이 미리보기에 사용하는 샘플 RPG Maker 프로젝트
|  `- vector_store.db
|- docker-compose.yml
|- docker-compose.prod.yml
|- pyproject.toml
|- README-DEPLOYMENT.md
|- README-EXECUTOR-MVP.md
`- vercel.json
```

## 현재 구현된 것

### 프런트엔드

- React 18 + Vite + Tailwind CSS 기반 UI
- `/editor` 경로의 편집 화면
- 백엔드로 프롬프트를 보내는 채팅 UI
- 게임 미리보기 영역
- RPG Maker iframe 뷰어
- 맵 뷰어
- 게임 데이터 뷰어
- 개발 환경에서 `storage/games/...` 를 `/game/...` 로 서빙하는 Vite 미들웨어

### 백엔드

- `app/backend/main.py` 의 FastAPI 앱
- 헬스체크 엔드포인트
- `/health`
- `/health/db`
- `/health/s3`
- 메인 API prefix: `/api/v1`
- 현재 실제로 연결된 API 엔드포인트:
- `POST /api/v1/llm/process`
- 게임 정적 파일 마운트 경로:
- `/game`

### 에이전트

- `agent/graph` 아래 LangGraph 워크플로우
- `agent/prompts` 아래 역할별 프롬프트
- `agent/schemas`, `agent/rag` 아래 RPG Maker 스키마/RAG 지원 코드
- `agent/tests` 아래 별도 테스트 세트

### 스토리지

- 로컬 게임 데이터는 `storage/games` 아래에 저장됩니다.
- 현재 프런트 미리보기는 `storage/games/game_001` 을 기준으로 동작합니다.

## 로컬 개발

### 준비물

- Python 3.12 이상
- `uv`
- Node.js 와 `npm`
- 선택 사항: Docker / Docker Compose

### 1. 환경 변수

예시 파일을 복사한 뒤 필요한 값을 수정합니다.

```bash
cp .env.example .env
```

자주 보는 환경 변수:

- `STORAGE_PATH`: 로컬 게임 저장 경로, 기본값 `./storage/games`
- `CORS_ORIGINS`: 허용할 프런트엔드 origin 목록
- `STORAGE_BACKEND`: `local` 또는 `s3`
- `DATABASE_URL`: 비워두면 DB 헬스체크는 skipped 처리
- `MCP_*`: MCP executor 연동용 설정

### 2. 백엔드 실행

루트에서 Python 의존성을 설치합니다.

```bash
uv sync --extra dev
```

백엔드를 실행합니다.

```bash
uv run uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
```

주요 주소:

- API root: `http://localhost:8000/`
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

### 3. 프런트엔드 실행

프런트 의존성을 설치합니다.

```bash
cd app/frontend
npm install
```

개발 서버를 실행합니다.

```bash
npm run dev
```

현재 Vite 개발 서버 포트는 `3000` 으로 설정되어 있습니다.

### 4. Docker 실행

백엔드 중심의 로컬 compose:

```bash
docker compose up -d
```

백엔드 + 프런트 dev 컨테이너 실행:

```bash
docker compose --profile full-dev up
```

## 테스트와 린트

루트에서:

```bash
uv run pytest
uv run ruff check .
```

`app/frontend` 에서:

```bash
npm run lint
```

## 주요 경로

- 백엔드 엔트리포인트: `app/backend/main.py`
- 프런트 엔트리포인트: `app/frontend/src/main.jsx`
- 프런트 편집 페이지: `app/frontend/src/pages/GameEditor.jsx`
- LLM API 구현: `app/backend/api/v1/endpoints/llm.py`
- 에이전트 워크플로우: `agent/graph/workflow.py`
- 샘플 게임: `storage/games/game_001`

## 관련 문서

- `README-DEPLOYMENT.md`: 배포 관련 문서
- `README-EXECUTOR-MVP.md`: executor MVP 관련 문서
- `docs/API.md`: API 관련 메모
- `docs/AWS_ENV_SETUP.md`: AWS 환경 설정
- `docs/RPGMAKER_STRUCTURE.md`: RPG Maker 프로젝트 구조 정리
- `docs/RPGMAKER_TILE_RENDERING.md`: 타일 렌더링 메모

## 참고

- 이 저장소는 애플리케이션 코드와 실제 RPG Maker 프로젝트 파일을 함께 포함합니다.
- 프런트엔드의 일부 디렉터리는 확장용으로 미리 만들어져 있으며, 현재는 부분 구현 상태입니다.
- 이 README는 초기 아이디어 설명보다 현재 저장소 상태와 실행 구조를 우선해서 정리했습니다.
