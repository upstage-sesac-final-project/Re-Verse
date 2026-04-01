# Re:Verse Backend API 명세서

## 목차
1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [인증 (Auth)](#3-인증-auth)
4. [게임 프로젝트 (Games)](#4-게임-프로젝트-games)
5. [LLM Agent (LLM)](#5-llm-agent-llm)
6. [헬스체크](#6-헬스체크)
7. [인프라 (RDS / S3)](#7-인프라-rds--s3)
8. [에러 응답 형식](#8-에러-응답-형식)
9. [환경 변수](#9-환경-변수)

---

## 1. 개요

| 항목 | 내용 |
|------|------|
| Base URL | `https://api.re-verse.ai.kr` (프로덕션) / `http://localhost:8000` (로컬) |
| API Prefix | `/api/v1` |
| 인증 방식 | JWT Bearer Token (`Authorization: Bearer <token>`) |
| Swagger | `{Base URL}/docs` |
| 프론트엔드 | `https://re-verse.ai.kr` (Vercel → `/api` 프록시) |

---

## 2. 아키텍처

### 2.1 레이어 구조

```
Endpoint (API)  →  Service (비즈니스 로직)  →  Repository (DB 접근)
```

| 레이어 | 경로 | 역할 |
|--------|------|------|
| Endpoint | `api/v1/endpoints/` | 요청 검증, 인증 확인, 응답 반환 |
| Service | `services/` | 비즈니스 로직, 외부 서비스 호출 |
| Repository | `repositories/` | DB 쿼리 (SQLAlchemy) |
| Schema | `schemas/` | 요청/응답 Pydantic 모델 |
| Model | `models/` | DB 테이블 정의 (SQLAlchemy ORM) |

### 2.2 게임 파일 처리 흐름 (S3 모드)

```
[프로젝트 생성]
  GameService → S3의 base_game/ 폴더를 복사 → S3에 game_00x/ 생성

[LLM 호출]
  ① Backend: S3에서 game_00x/ → 로컬 storage/games/game_00x/ 다운로드
  ② Agent: 로컬 파일을 직접 읽기/수정 (일반 파일 I/O)
  ③ Backend: 로컬 → S3 업로드
  ④ Backend: 로컬 폴더 삭제
```

> Agent가 S3에 직접 접근하지 않고 로컬 파일을 사용하는 이유:
> - 파일 반복 접근 시 S3 HTTP 호출 대비 성능 우위
> - 실패 시 로컬 폴더만 삭제하면 S3 원본이 보존됨 (트랜잭션 안전성)
> - Agent 코드가 인프라에 비종속 (로컬 개발 시 S3 없이 동작)

---

## 3. 인증 (Auth)

모든 인증 엔드포인트 prefix: `/api/v1/auth`

### 3.1 회원가입

```
POST /api/v1/auth/register
```

**Request Body**
```json
{
  "username": "string (2~50자)",
  "email": "string (이메일 형식)",
  "password": "string (8~100자)"
}
```

**Response `201 Created`**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "abc123...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user_id": 1,
  "username": "testuser"
}
```

| 에러 코드 | 상황 |
|-----------|------|
| `409` | 이미 등록된 이메일 |
| `422` | 유효성 검증 실패 (비밀번호 8자 미만, 이름 2자 미만 등) |

---

### 3.2 로그인

```
POST /api/v1/auth/login
```

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```

**Response `200 OK`** — 회원가입과 동일한 `TokenResponse`

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 이메일 또는 비밀번호 불일치 |

---

### 3.3 토큰 갱신

```
POST /api/v1/auth/refresh
```

**Request Body**
```json
{
  "refresh_token": "abc123..."
}
```

**Response `200 OK`** — 새로운 `TokenResponse` (Refresh Token Rotation 적용)

> Rotation: 갱신 시 기존 refresh token은 폐기(revoked)되고 새 token 발급

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 유효하지 않거나 폐기/만료된 refresh token |

---

### 3.4 로그아웃

```
POST /api/v1/auth/logout
```

**Request Body**
```json
{
  "refresh_token": "abc123..."
}
```

**Response `204 No Content`** — 본문 없음

> 존재하지 않는 token으로 요청해도 에러 없이 204 반환

---

### 3.5 내 정보 조회

```
GET /api/v1/auth/me
```

**Headers**: `Authorization: Bearer <access_token>` (필수)

**Response `200 OK`**
```json
{
  "id": 1,
  "username": "testuser",
  "email": "user@example.com",
  "created_at": "2026-03-31T12:00:00+00:00"
}
```

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 토큰 없음 / 유효하지 않은 토큰 |

### 3.6 토큰 사양

| 항목 | 값 |
|------|-----|
| Access Token 유효기간 | 30분 (설정: `JWT_EXPIRATION_MINUTES`) |
| Refresh Token 유효기간 | 24시간 (설정: `REFRESH_TOKEN_EXPIRATION_HOURS`) |
| 알고리즘 | HS256 |
| Access Token Payload | `{ "sub": "user_id", "email": "...", "exp": ... }` |

---

## 4. 게임 프로젝트 (Games)

모든 엔드포인트에 `Authorization: Bearer <token>` 필수.

prefix: `/api/v1/games`

### 4.1 프로젝트 목록 조회

```
GET /api/v1/games
```

**Response `200 OK`**
```json
{
  "projects": [
    {
      "id": 1,
      "user_id": 1,
      "name": "My RPG",
      "description": "An RPG game",
      "game_id": "game_001",
      "status": "draft",
      "created_at": "2026-03-31T12:00:00+00:00",
      "updated_at": "2026-03-31T12:00:00+00:00"
    }
  ],
  "total": 1
}
```

> 로그인한 사용자의 프로젝트만 반환 (다른 사용자 프로젝트 비노출)

---

### 4.2 프로젝트 생성

```
POST /api/v1/games
```

**Request Body**
```json
{
  "name": "My RPG (1~200자, 필수)",
  "description": "설명 (선택)"
}
```

**Response `201 Created`** — `ProjectResponse` (위 목록의 단일 항목과 동일)

**동작**: base_game 폴더를 복사하여 `game_00x` 폴더를 생성하고, DB에 프로젝트 레코드를 추가합니다.

| 에러 코드 | 상황 |
|-----------|------|
| `400` | 사용자당 프로젝트 수 제한 초과 (기본 3개) |
| `401` | 인증 없음 |
| `422` | name이 빈 문자열 |
| `500` | base_game 복사 실패 (자동 롤백) |

---

### 4.3 프로젝트 상세 조회

```
GET /api/v1/games/{project_id}
```

**Response `200 OK`** — `ProjectResponse`

| 에러 코드 | 상황 |
|-----------|------|
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |

---

### 4.4 프로젝트 수정

```
PATCH /api/v1/games/{project_id}
```

**Request Body** (부분 업데이트 가능)
```json
{
  "name": "New Name",
  "description": "New description"
}
```

**Response `200 OK`** — 수정된 `ProjectResponse`

| 에러 코드 | 상황 |
|-----------|------|
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |

---

### 4.5 프로젝트 삭제

```
DELETE /api/v1/games/{project_id}
```

**Response `204 No Content`**

**동작**: DB 레코드 삭제 (ConversationLog cascade 삭제) + 게임 폴더 삭제

| 에러 코드 | 상황 |
|-----------|------|
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |

---

### 4.6 게임 플레이 (정적 파일 서빙)

RPG Maker MZ 게임은 `index.html`을 진입점으로 로드되며, 게임 내부에서 필요한 리소스(JSON, 이미지, 오디오 등)를 자동으로 요청합니다.

```
GET /game/{game_id}/index.html
```

**예시**: `GET /game/game_001/index.html` → 게임 실행

> `STORAGE_PATH` 아래의 파일을 FastAPI `StaticFiles`로 서빙합니다.
> 개별 데이터 파일을 API로 따로 서빙하지 않으며, 게임 엔진이 상대경로로 리소스를 로드합니다.
> 이 경로는 인증이 적용되지 않습니다.

---

## 5. LLM Agent (LLM)

모든 엔드포인트에 `Authorization: Bearer <token>` 필수.

prefix: `/api/v1/llm`

### 5.1 LLM 처리 요청

```
POST /api/v1/llm/process
```

**Request Body**
```json
{
  "project_id": 1,
  "message": "주인공의 레벨을 25로 설정해줘"
}
```

**Response `200 OK`**
```json
{
  "code": 201,
  "message": "주인공의 초기 레벨을 25로 설정했습니다.",
  "result": {
    "intent": "modify_level",
    "processed": true
  },
  "intent": "modify_level",
  "modifications": ["Actors"],
  "affected_files": ["Actors"],
  "changes_log": [
    {
      "step_id": 1,
      "tool_name": "modify_actor",
      "description": "주인공 레벨 변경",
      "success": true,
      "result_summary": "레벨 25로 설정 완료"
    }
  ],
  "reload_required": true,
  "success": true
}
```

**실패 시 응답 (Agent 내부 오류)**
```json
{
  "code": 500,
  "message": "처리 중 오류가 발생했습니다: ...",
  "result": {},
  "intent": "error",
  "modifications": [],
  "affected_files": [],
  "changes_log": [],
  "reload_required": false,
  "success": false
}
```

**타임아웃 시 응답**
```json
{
  "code": 504,
  "message": "요청 처리 시간이 초과되었습니다.",
  "intent": "timeout",
  "success": false
}
```

| 필드 | 프론트엔드 활용 |
|------|----------------|
| `success` | 성공/실패 판단 |
| `reload_required` | `true`이면 게임 뷰어를 리로드 |
| `message` | 사용자에게 보여줄 자연어 응답 |
| `changes_log` | 변경 이력 UI 렌더링 |
| `affected_files` | 어떤 게임 파일이 수정되었는지 |

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 인증 없음 |
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |
| `422` | message가 빈 문자열 |
| `500` | 서버 내부 오류 |

**처리 흐름 (내부)**:
```
소유권 확인 → Game-Level Lock 획득 → (S3 다운로드) → LangGraph Agent 호출
→ (S3 업로드 + 로컬 삭제) → ConversationLog DB 저장 → 응답 반환
```

---

### 5.2 대화 이력 조회

```
GET /api/v1/llm/history/{project_id}?limit=20&offset=0
```

| 파라미터 | 기본값 | 범위 |
|---------|--------|------|
| `limit` | 20 | 1~100 |
| `offset` | 0 | 0~ |

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "user_input": "레벨을 25로 설정해줘",
    "agent_response": "주인공의 초기 레벨을 25로 설정했습니다.",
    "intent": "modify_level",
    "success": true,
    "processing_time": 2.34,
    "timestamp": "2026-03-31T12:05:00+00:00"
  }
]
```

> 최신 순으로 정렬 (timestamp DESC)

| 에러 코드 | 상황 |
|-----------|------|
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |

---

## 6. 헬스체크

인증 불필요.

| 엔드포인트 | 용도 | 응답 예시 |
|-----------|------|----------|
| `GET /health` | 서버 기본 상태 | `{"status": "healthy", "message": "Re:Verse Backend is running"}` |
| `GET /health/db` | RDS 연결 확인 | `{"ok": true, "detail": "ok"}` |
| `GET /health/s3` | S3 버킷 접근 확인 | `{"ok": true, "detail": "ok"}` |
| `GET /` | 루트 (API 안내) | `{"message": "Welcome to Re:Verse API", "docs": "/docs"}` |

> `health/db`: `DATABASE_URL` 미설정 시 `{"ok": true, "detail": "skipped"}`
> `health/s3`: `STORAGE_BACKEND=local` 시 `{"ok": true, "detail": "skipped"}`

---

## 7. 인프라 (RDS / S3)

### 7.1 RDS (PostgreSQL)

| 항목 | 값 |
|------|-----|
| 접속 | `DATABASE_URL` 환경 변수 (예: `postgresql+psycopg://user:pass@host:5432/dbname`) |
| 로컬 개발 | `sqlite+aiosqlite:///./storage/reverse.db` |
| ORM | SQLAlchemy 2.x (async) |
| 드라이버 | psycopg (PostgreSQL) / aiosqlite (로컬) |

**DB 테이블**

| 테이블 | 설명 | 주요 컬럼 |
|--------|------|-----------|
| `users` | 사용자 | id, username, email, hashed_password, created_at, updated_at |
| `projects` | 게임 프로젝트 | id, user_id(FK), name, description, game_id(unique), status, created_at, updated_at |
| `conversation_logs` | 대화 이력 | id, project_id(FK), user_input, agent_response, intent, success, processing_time, timestamp |
| `refresh_tokens` | 리프레시 토큰 | id, token(unique), user_id(FK), expires_at, revoked, created_at |

**관계**
```
User (1) ──< Project (N)  ──< ConversationLog (N)
User (1) ──< RefreshToken (N)
```

- `projects` 삭제 시 `conversation_logs` cascade 삭제
- `users` 삭제 시 `projects` cascade 삭제, `refresh_tokens` cascade 삭제

**테이블 자동 생성**: 서버 시작 시 `Base.metadata.create_all(checkfirst=True)` 실행 (기존 데이터 보존)

---

### 7.2 S3

| 항목 | 값 |
|------|-----|
| 버킷 | `upstage-sesac-31-reverse-project-s3` |
| 리전 | `ap-northeast-2` |
| 인증 | EC2 IAM Role (ACCESS_KEY 불필요) |
| prefix | `games/` |

**S3 키 구조**
```
games/
├── base_game/           ← 프로젝트 생성 시 복사 원본
│   └── data/
│       ├── Actors.json
│       ├── Items.json
│       └── ...
├── game_001/            ← 프로젝트별 게임 데이터
│   └── data/
│       ├── Actors.json
│       └── ...
└── game_002/
    └── ...
```

**S3 접근이 발생하는 시점**

| 시점 | 동작 | 코드 위치 |
|------|------|-----------|
| 프로젝트 생성 | `base_game/` → `game_00x/` S3 복사 | `GameService._s3_copy_base_game()` |
| 프로젝트 삭제 | `game_00x/` S3 객체 전체 삭제 | `GameService._s3_delete_game()` |
| LLM 호출 전 | S3 → 로컬 다운로드 | `sync_game_from_s3()` |
| LLM 호출 후 (성공) | 로컬 → S3 업로드 | `sync_game_to_s3()` |
| 헬스체크 | `HeadBucket` 접근 확인 | `check_s3_bucket_access()` |

> `STORAGE_BACKEND=local` (로컬 개발) 시 S3 관련 동작은 모두 skip됩니다.

---

## 8. 에러 응답 형식

### FastAPI 기본 에러 (422 등)
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "input": "1234567"
    }
  ]
}
```

### 비즈니스 에러 (401, 403, 404, 409 등)
```json
{
  "detail": "이미 등록된 이메일입니다."
}
```

### 서버 내부 에러 (500, 글로벌 핸들러)
```json
{
  "error": "Internal Server Error",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

> 모든 응답에 `X-Request-ID` 헤더가 포함됩니다 (디버깅용).

---

## 9. 환경 변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `DATABASE_URL` | O | - | DB 접속 문자열 |
| `JWT_SECRET_KEY` | O | - | 비어 있으면 서버 시작 차단 |
| `JWT_ALGORITHM` | - | `HS256` | JWT 알고리즘 |
| `JWT_EXPIRATION_MINUTES` | - | `30` | Access Token 유효기간 (분) |
| `REFRESH_TOKEN_EXPIRATION_HOURS` | - | `24` | Refresh Token 유효기간 (시간) |
| `ENVIRONMENT` | - | `development` | `development` / `production` |
| `DEBUG` | - | `true` | 디버그 모드 |
| `CORS_ORIGINS` | - | localhost + re-verse.ai.kr | 허용 Origin (쉼표 구분) |
| `STORAGE_PATH` | - | `./storage/games` | 게임 파일 로컬 경로 |
| `BASE_GAME_PATH` | - | `./storage/games/base_game` | 기본 게임 템플릿 경로 |
| `STORAGE_BACKEND` | - | `local` | `local` / `s3` |
| `MAX_PROJECTS_PER_USER` | - | `3` | 사용자당 프로젝트 수 제한 |
| `AWS_REGION` | - | `ap-northeast-2` | S3 리전 |
| `S3_BUCKET_NAME` | - | `upstage-sesac-31-reverse-project-s3` | S3 버킷명 |
| `S3_PREFIX` | - | `games` | S3 prefix |

---

## 게임 정적 파일 서빙

```
GET /game/{game_id}/index.html
```

`STORAGE_PATH` 아래의 게임 폴더를 FastAPI `StaticFiles`로 서빙합니다.
RPG Maker MZ 게임은 `index.html`을 진입점으로 로드되며, 게임 엔진이 필요한 리소스(data/, img/, audio/ 등)를 상대경로로 자동 요청합니다.

> 이 경로는 인증이 적용되지 않습니다.
