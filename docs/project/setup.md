# Project Setup

현재 저장소 기준의 최소 실행 절차만 정리한다.

## 준비물

- Python 3.12+
- `uv`
- Node.js / `npm`

## 1. Python 의존성 설치

```bash
uv sync --extra dev
```

## 2. 환경 변수 준비

```bash
cp .env.example .env
```

필수로 확인할 값:

- `JWT_SECRET_KEY`
- `LLM_API_KEY`
- `STORAGE_PATH`
- `DATABASE_URL`

## 3. 백엔드 실행

```bash
uv run uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 4. 프런트엔드 실행

```bash
cd app/frontend
npm install
npm run dev
```

## 5. validator 단독 실행

validator CLI 실행은 [../nodes/validator/test_run.md](../nodes/validator/test_run.md)를 참고한다.
