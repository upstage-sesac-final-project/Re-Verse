# 🎮 Re:Verse

> 자연어 명령을 해석해 RPG 게임 요소를 제한된 범위 안에서 수정하고,
> 그 결과를 웹에서 바로 확인할 수 있게 만드는 AI 기반 게임 제작 도구입니다.
>
> 프로젝트명인 **Re:Verse**는 **Reply(대답하다) + Universe(세계관)**의 합성어이자,
> 세상을 뒤집는다는 **Reverse**의 중의적 표현입니다.

---

## ✨ 프로젝트 개요

기존 RPG 제작 도구는 강력하지만, 비개발자나 초보자가 다루기엔 진입장벽이 높습니다.
**Re:Verse**는 사용자가 복잡한 에디터를 직접 다루지 않아도, 자연어로 원하는 요소를 설명하면 시스템이 이를 해석해 게임에 반영하는 것을 목표로 합니다.

현재 저장소에는 다음이 함께 포함되어 있습니다.

- `app/frontend`: React/Vite 기반 에디터 UI
- `app/backend`: FastAPI API 서버
- `agent`: LangGraph 기반 에이전트 워크플로우

---

## 🎯 MVP 목표

- 웹에서 자연어 명령 입력
- 명령을 해석해 Python 기반 수정 로직과 연결
- 수정 결과를 웹에서 즉시 확인
- 최소 1회 이상 생성/수정 사이클 완성

### ✅ MVP 포함 범위

- RPG Maker DB 내용 수정
- 간단한 대사 변경
- 소규모 맵 요소 수정

### 🚫 MVP 제외 범위

- 완전 자유형 월드 생성
- 복잡한 연속 퀘스트 자동 생성
- 다단계 추론 기반 자동 설계
- 자율 에이전트형 장기 작업

---

## 🔄 시스템 흐름

```text
사용자 자연어 입력
       ↓
LLM (의도 파악 및 라우팅)
       ↓
JSON 파일 수정 (RPG Maker 데이터 반영)
       ↓
웹에서 결과 확인
```

---

## ✅ 현재 구현 상태 (요약)

- React 에디터 화면에서 채팅 기반 명령 입력 가능
- FastAPI에서 `/api/v1/*` API 제공 (Auth/Games/LLM/Admin/Docs)
- Agent 파이프라인(`router → definition → planner → executor → validator → synthesizer`) 구성
- `storage/games`를 프론트/백엔드에서 `/game` 경로로 서빙해 결과 확인 가능
- Validator는 파일별 스키마 검증 결과를 `validation_results` 형식으로 반환

---

## 🧱 기술 스택

| 분류 | 기술 |
|------|------|
| **Frontend** | React 18, Vite, Redux Toolkit |
| **Backend** | FastAPI, Python 3.12, uv |
| **Database** | SQLite 기본 (`DATABASE_URL`로 변경 가능), Supabase/AWS 확장 고려 |
| **AI Model** | Solar Pro 계열 (환경변수로 설정) |
| **AI Agent** | LangGraph, LangSmith |
| **RAG** | Upstage 임베딩 + ChromaDB |
| **배포/운영** | Docker, GitHub Actions, AWS |
| **게임 엔진** | RPG Maker MZ |

---

## 📂 저장소 구조

```text
.
├─ app/
│  ├─ backend/      # FastAPI API, 서비스, DB, 테스트
│  └─ frontend/     # React/Vite UI
├─ agent/           # LangGraph 기반 에이전트 파이프라인
├─ docs/            # 프로젝트/노드/배포/RPGMaker 문서
├─ storage/
│  └─ games/        # RPG Maker 프로젝트 데이터
├─ docker/          # Dockerfiles, nginx 설정
└─ scripts/         # 보조 스크립트
```

---

## ⚙️ 로컬 실행 (Quick Start)

### 1) 준비

- Python 3.12+
- `uv`
- Node.js / `npm`

### 2) Python 의존성 설치

```bash
uv sync --extra dev
```

### 3) 환경변수 준비

```bash
cp .env.example .env
```

필수 확인 항목:

- `JWT_SECRET_KEY`
- `LLM_API_KEY`
- `STORAGE_PATH`
- `DATABASE_URL`

### 4) 백엔드 실행

```bash
uv run uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5) 프론트엔드 실행

```bash
cd app/frontend
npm install
npm run dev
```

기본 접속:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

---

## 🧪 테스트 & 품질 체크

### Agent 테스트

```bash
# 전체 실행
python -m pytest agent/tests/ -v

# 커버리지 포함
python -m pytest agent/tests/ --cov --cov-report=term-missing

# 특정 파일만
python -m pytest agent/tests/test_executor_mvp.py -v

# 키워드 필터
python -m pytest agent/tests/ -k "enemy" -v
```

### Backend 테스트

```bash
# 전체 실행
python -m pytest app/backend/tests/ -v

# 커버리지 포함
python -m pytest app/backend/tests/ --cov --cov-report=term-missing
```

### 전체 테스트 + 커버리지

```bash
python -m pytest --cov --cov-report=term-missing
```

### 린트

```bash
uv run ruff check .
```

### 프론트엔드

```bash
cd app/frontend
npm run lint
```

---

## 🧭 핵심 경로

- Backend entry: `app/backend/main.py`
- Frontend entry: `app/frontend/src/main.jsx`
- Agent workflow: `agent/graph/workflow.py`
- Validator node: `agent/graph/nodes/validator.py`
- 프로젝트 문서 인덱스: `docs/index.md`

---

## 📚 문서

- 전체 문서 인덱스: [`docs/index.md`](docs/index.md)
- 빠른 실행 가이드: [`docs/project/setup.md`](docs/project/setup.md)
- Validator 실행 가이드: [`docs/nodes/validator/test_run.md`](docs/nodes/validator/test_run.md)
- 배포 문서: [`docs/deployment/deployment.md`](docs/deployment/deployment.md)
- RPG Maker 구조 메모: [`docs/rpgmaker/rpgmaker_structure.md`](docs/rpgmaker/rpgmaker_structure.md)
