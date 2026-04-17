# 🎮 Re:Verse

> **채팅으로 RPG를 만드세요.**
> Re:Verse는 **자연어로 RPG Maker MZ 게임을 제작**하는 도구입니다. 캐릭터, 맵, 이벤트를 **대화로 만들고** 바로 **플레이**할 수 있습니다.

🌐 **라이브 사이트:** [re-verse.ai.kr](https://re-verse.ai.kr/)

---

## ✨ 이 프로젝트가 해결하는 것

RPG Maker MZ는 강력하지만, 에디터를 처음 다루는 사람에게는 진입 장벽이 큽니다. **Re:Verse**는 그 간격을 줄이기 위해 만들어졌습니다.

| 관점 | 설명 |
|------|------|
| **사용자** | 복잡한 메뉴 대신 **한국어/자연어**로 “이렇게 바꿔줘”라고 말하면 됩니다. |
| **시스템** | LLM과 에이전트 파이프라인이 의도를 해석하고, **RPG Maker 데이터(JSON 등)**를 안전한 범위에서 수정합니다. |
| **결과** | 웹 에디터에서 수정 내용을 확인하고, `/game` 경로로 **빌드된 게임을 실행**해 볼 수 있습니다. |

공개 랜딩에서 강조하는 세 가지 축은 다음과 같습니다 ( [re-verse.ai.kr](https://re-verse.ai.kr/) 기준 ).

| 아이콘(랜딩) | 의미 |
|--------------|------|
| **자연어 생성** | 대화만으로 게임 요소를 만들고 고칩니다. |
| **즉시 플레이** | 생성·수정 직후 바로 실행해 동작을 확인합니다. |
| **MZ 전 요소** | 캐릭터부터 맵·이벤트까지 MZ 데이터 모델을 다루는 방향으로 설계되어 있습니다. |

---

## 🏷️ 이름: Re:Verse

랜딩 페이지의 설명처럼, **Re:Verse**는 두 가지 뜻을 겹쳐 둡니다.

- **Reply(대답하다) + Universe(세계관)** — 대화로 세계를 만든다는 뉘앙스
- **Reverse(뒤집다)** — 기존 RPG 제작 방식을 뒤집어 보자는 의미

즉, “대화로 세계를 열고, 흐름을 바꾼다”는 브랜드 메시지와 코드베이스의 목표가 맞물려 있습니다.

---

## 🧩 한 번에 보는 구조

이 저장소는 **프론트 · 백엔드 · AI 에이전트**가 한 레포에 있습니다.

```text
.
├─ app/frontend/     # React + Vite — 대시보드, 채팅 에디터, 게임 프리뷰 UI
├─ app/backend/      # FastAPI — REST API, JWT, 게임/LLM 라우팅, S3·DB 연동
├─ agent/            # LangGraph — 의도 분석, 계획, 실행, 검증, 응답 합성
├─ shared/           # 공통 로깅 등 (예: shared/logging_config.py)
├─ storage/games/    # STORAGE_BACKEND=local 일 때 게임 프로젝트 루트
├─ docker/           # 백엔드 이미지, 선택적 Nginx
├─ scripts/          # EC2 호스트 모니터링 등 운영 스크립트
└─ docs/             # 셋업, 배포, RPG Maker 구조, 노드별 문서
```

---

## 🔄 사용자 관점: 요청이 어떻게 흘러가나

아주 단순화하면 다음과 같습니다.

```text
채팅 입력
    → LLM + 에이전트(라우팅·계획·실행)
    → RPG Maker 프로젝트 파일 수정 (맵/액터/이벤트 등)
    → 검증(Validator) 후 응답
    → (프론트에서) 게임 실행 또는 다음 지시
```

에이전트 쪽 **노드 순서**는 대략 다음과 같이 이해하면 됩니다.

`router` → `definition` → `planner` → `executor` → `validator` → `synthesizer`

- **Router:** 무엇을 할지 분기
- **Planner / Executor:** 무엇을 어떤 파일에 어떻게 적용할지
- **Validator:** 스키마·일관성 검사 (`validation_results` 형태로 반환)
- **Synthesizer:** 사용자에게 돌려줄 자연어 응답 정리

자세한 노드 동작은 `docs/`와 `agent/editor/` 소스를 함께 보면 좋습니다.

---

## 🌍 프로덕션 아키텍처 (배포)

브라우저는 **HTTPS**로만 [re-verse.ai.kr](https://re-verse.ai.kr/)에 붙고, API는 **같은 사이트의 `/api`**로 호출합니다 (`VITE_API_URL=/api`). Mixed Content를 피하기 위해 Vercel이 백엔드로 넘겨 줍니다.

1. **Vercel** — 프론트 정적 빌드 + `vercel.json` **rewrites**
2. **`/api/*`, `/game/*`** → EC2에서 돌아가는 **FastAPI**(보통 포트 `8000`)
3. **EC2 Docker** — 백엔드 컨테이너 + (설정에 따라) 에이전트·워커
4. **S3** — `STORAGE_BACKEND=s3`일 때 게임 파일 동기화
5. **PostgreSQL(RDS 등)** — `DATABASE_URL`이 있을 때 사용자·프로젝트 메타 등 영속 데이터

```text
브라우저 → Vercel(HTTPS, rewrites) → EC2:8000(FastAPI + Agent) → S3 / RDS / LLM API
```

`vercel.json`에 적힌 **백엔드 호스트(IP 또는 도메인)**가 바뀌면 반드시 저장소에서 수정 후 Vercel에 다시 배포해야 합니다.

---

## ⚙️ 환경 변수: 어디를 보나

설정 로더는 `app/backend/core/config.py`를 기준으로 합니다.

| 상황 | 파일 |
|------|------|
| 로컬 | `.env.development` (`.env.development.example` 복사) |
| EC2 프로덕션 | `.env.production` — GitHub Actions 배포 시 **`ENV_FILE` 시크릿 전체**가 서버의 `.env.production`으로 **덮어쓰기**됩니다 |

**자주 만지는 키**

| 키 | 역할 |
|----|------|
| `JWT_SECRET_KEY` | 필수 — 비어 있으면 서버 기동 실패 |
| `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | 사용 중인 LLM 벤더 (예: Solar, OpenAI 호환 엔드포인트) |
| `DATABASE_URL` | PostgreSQL URL. **비어 있으면** DB 엔진 미생성, `/health/db` 등은 스킵 |
| `STORAGE_BACKEND` | `local` 또는 `s3` |
| `AWS_REGION`, `S3_BUCKET_NAME`, `S3_PREFIX` | S3 모드일 때 객체 경로 (`games/{game_id}/...` 등) |
| `DISCORD_*` | 예외 알림, 토큰/비용 알림, 버그 리포트 웹훅 (선택) |
| `DISCORD_TOKEN_ALERT_MIN_TOTAL_TOKENS` 등 | 토큰 알림 빈도 조절 |
| `LOG_DIR`, `LOG_RETENTION_HOURS` | 프로덕션에서 파일 로그 위치·날짜 폴더 보존 시간 |

전체 예시는 `.env.production.example`을 참고하세요.

---

## 💻 로컬 개발

**필요:** Python 3.12+, [uv](https://github.com/astral-sh/uv), Node.js 18+.

```bash
uv sync --extra dev
cp .env.development.example .env.development

cd app/frontend && npm install && cd ../..
```

```bash
# 터미널 1
uv run uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# 터미널 2
cd app/frontend && npm run dev
```

| 서비스 | URL |
|--------|-----|
| API 문서 (Swagger) | http://localhost:8000/docs |
| 프론트 (Vite 기본) | http://localhost:5173 |

Docker만 쓰는 흐름은 [`docs/deployment/deployment.md`](docs/deployment/deployment.md)를 보세요.

---

## 🚀 프로덕션 배포 요약

| 구분 | 내용 |
|------|------|
| 프론트 | Vercel — Git 연동 빌드, `vercel.json`으로 API·게임 경로 프록시 |
| 백엔드 | `main` 브랜치에 푸시 → `.github/workflows/deploy.yml`이 EC2에 SSH → `git` 동기화 → `ENV_FILE`로 `.env.production` 생성 → `docker compose` 빌드·기동 → **헬스체크** → 오래된 이미지 정리 |

**GitHub Repository secrets:** `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `ENV_FILE`

---

## ✅ CI / 자동화

| 파일 | 역할 |
|------|------|
| `.github/workflows/ci.yml` | `develop`, `main`에 push/PR 시 백엔드(ruff, mypy, pytest) + 프론트(ESLint, build) |
| `.github/dependabot.yml` | GitHub Actions 의존성 월간 점검 |

로컬에서 CI에 가깝게 돌리려면:

```bash
uv run pytest app/backend/tests agent/tests -v --tb=short -m "not integration"
uv run ruff check app/backend && uv run mypy app/backend
cd app/frontend && npm run lint && npm run build
```

---

## 📣 운영: 알림과 로그

| 종류 | 환경 변수 / 스크립트 |
|------|----------------------|
| HTTP 예외 요약 | `DISCORD_WEBHOOK_URL` |
| LLM 토큰·비용 | `DISCORD_TOKEN_WEBHOOK_URL` + `DISCORD_TOKEN_ALERT_MIN_*` |
| EC2 디스크·부하 | `scripts/ec2_host_monitor.sh`, `DISCORD_INFRA_WEBHOOK_URL`, `DISK_THRESHOLD`, `LOAD_FACTOR` |

EC2 호스트에 쌓이는 **애플리케이션 파일 로그** ( `docker-compose.prod.yml`에서 `./logs/backend` ↔ 컨테이너 `/app/logs` ):

```bash
cd ~/Re-Verse
tail -f "logs/backend/general/$(date +%Y-%m-%d)/anonymous/general.log"
```

---

## 🧭 코드 읽기 순서 (추천)

| 파일 | 이유 |
|------|------|
| `app/backend/main.py` | FastAPI 앱, 미들웨어, 라우트 진입 |
| `app/frontend/src/main.jsx` | 라우터·스토어·전역 UI |
| `agent/editor/workflow.py` | LangGraph 그래프 정의 |
| `agent/editor/nodes/validator.py` | 검증 로직 |
| `app/backend/core/config.py` | 환경 변수·CORS·스토리지 설정 |

---

## 📚 문서 모음

- [`docs/index.md`](docs/index.md) — 전체 목차
- [`docs/project/setup.md`](docs/project/setup.md) — 상세 셋업
- [`docs/deployment/deployment.md`](docs/deployment/deployment.md) — EC2·Vercel·Mixed Content
- [`docs/rpgmaker/rpgmaker_structure.md`](docs/rpgmaker/rpgmaker_structure.md) — MZ 데이터 구조
- [`docs/nodes/validator/test_run.md`](docs/nodes/validator/test_run.md) — Validator 실행

---

## 📄 라이선스

팀·조직 정책에 따릅니다.
