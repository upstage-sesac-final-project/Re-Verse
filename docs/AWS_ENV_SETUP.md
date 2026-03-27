# AWS + Vercel 연동 요약 (이번에 코드에 반영된 내용)

## 프론트 (Vercel)

- 프로덕션 URL: `https://re-verse.ai.kr`
- API는 `vercel.json`의 `rewrites`로 `/api/*` → `https://api.re-verse.ai.kr/api/*` 로 전달합니다.
- `/game/*` 도 동일하게 API 도메인으로 프록시합니다.
- 빌드 시 `VITE_API_URL=/api` 로 상대 경로 호출을 유지합니다.

## 백엔드 (EC2 Docker)

- 공개 API 베이스: `https://api.re-verse.ai.kr` (Nginx 등으로 443 → 백엔드 8000 프록시 가정)
- CORS는 `CORS_ORIGINS`로 제어합니다. **쉼표 구분** 또는 **JSON 배열 문자열** 둘 다 지원합니다.
- 프로덕션 `ENV_FILE`에는 반드시 `https://re-verse.ai.kr` 을 포함하세요. `https://*.vercel.app` 같은 와일드카드는 Starlette CORS에서 기대대로 동작하지 않을 수 있습니다.

## 저장소 이중 모드

| 모드 | 설명 |
|------|------|
| `STORAGE_BACKEND=local` | `STORAGE_PATH` 아래만 사용 (로컬 개발·테스트) |
| `STORAGE_BACKEND=s3` | 요청 처리 전 S3에서 `games/{game_id}/` 를 내려받고, LLM 처리 성공 후 다시 업로드 |

- S3 버킷: `upstage-sesac-31-reverse-project-s3`
- Prefix: `games` → 객체 키 예: `games/game_001/data/Actors.json`
- EC2 IAM 역할에 `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` 등 부여

## RDS

- `DATABASE_URL` 이 비어 있으면 SQLAlchemy 엔진을 만들지 않으며, `/health/db` 는 `skipped` 로 응답합니다.
- 설정 시 PostgreSQL + `psycopg` 드라이버 URL 예:
  `postgresql+psycopg://user:pass@host:5432/dbname?sslmode=require`

## GitHub Actions

- 기존처럼 `ENV_FILE` 시크릿에 위 변수들이 포함된 `.env` 전체를 넣으면 EC2 배포 시 동일하게 적용됩니다.

## 변경·추가된 주요 파일

- `app/backend/core/config.py` — CORS, S3, RDS, STORAGE_BACKEND
- `app/backend/core/game_paths.py` — 게임 `data/` 경로 단일화
- `app/backend/services/s3_game_storage.py` — S3 동기화
- `app/backend/db/session.py`, `db/base.py` — RDS 연결
- `app/backend/main.py` — CORS, `/health/db`, `/health/s3`, storage 디렉터리 생성
- `app/backend/services/llm_service.py` — S3 모드 시 동기화 훅
- `agent/graph/nodes/executor.py` — `_get_data_path` 가 `STORAGE_PATH` 기준으로 통일
- `vercel.json` — API 도메인 `https://api.re-verse.ai.kr`
- `.env.example` — 변수 템플릿
