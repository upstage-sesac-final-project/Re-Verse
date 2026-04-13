# Re:Verse Backend API 명세서

## 목차
1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [인증 보안 패턴](#3-인증-보안-패턴)
4. [Auth API](#4-auth-api)
5. [게임 프로젝트 (Games)](#5-게임-프로젝트-games)
6. [LLM Agent (LLM)](#6-llm-agent-llm)
7. [에디터 (Editor)](#7-에디터-editor)
8. [게임 생성 (Generation)](#8-게임-생성-generation)
9. [헬스체크](#9-헬스체크)
10. [인프라 (RDS / S3)](#10-인프라-rds--s3)
11. [에러 응답 형식](#11-에러-응답-형식)
12. [환경 변수](#12-환경-변수)

---

## 1. 개요

| 항목 | 내용 |
|------|------|
| Base URL | `https://api.re-verse.ai.kr` (프로덕션) / `http://localhost:8000` (로컬) |
| API Prefix | `/api/v1` |
| 인증 방식 | JWT Bearer Token (`Authorization: Bearer <token>`) |
| Swagger | `{Base URL}/docs` |
| 프론트엔드 | `https://re-verse.ai.kr` (Vite Dev Server → `/api` 프록시) |

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

### 2.2 전체 요청 흐름

```
Client
  │
  ├── REST (HTTP)  →  FastAPI Router  →  Endpoint  →  Service  →  Repository  →  DB
  │
  └── WebSocket   →  FastAPI Router  →  Endpoint  →  progress queue  →  Agent 이벤트
```

### 2.3 게임 파일 처리 흐름 (S3 모드)

```
[프로젝트 생성]
  GameService → S3의 base_game/ 폴더를 복사 → S3에 game_00x/ 생성

[LLM 호출 (증분 편집)]
  ① Backend: S3에서 game_00x/ → 로컬 storage/games/game_00x/ 다운로드
  ② Agent: 로컬 파일을 직접 읽기/수정 (일반 파일 I/O)
  ③ Backend: 로컬 → S3 업로드
  ④ Backend: 로컬 폴더 삭제

[게임 생성 (풀 생성)]
  ① Agent: LangGraph 워크플로우 실행 (LLM 8~10회 호출, 60~120초)
  ② Agent: write_project_to_disk() → 로컬 storage/games/{game_id}/data/에 전체 JSON 작성
  ③ Backend: 로컬 → S3 업로드 (S3 모드 시)
```

> Agent가 S3에 직접 접근하지 않고 로컬 파일을 사용하는 이유:
> - 파일 반복 접근 시 S3 HTTP 호출 대비 성능 우위
> - 실패 시 로컬 폴더만 삭제하면 S3 원본이 보존됨 (트랜잭션 안전성)
> - Agent 코드가 인프라에 비종속 (로컬 개발 시 S3 없이 동작)

---

## 3. 인증 보안 패턴

### 3.1 인증 의존성

모든 인증 필요 엔드포인트는 `get_current_user` 의존성을 사용합니다.

```python
current_user: User = Depends(get_current_user)
```

`get_current_user` 내부 동작:
1. `Authorization: Bearer <token>` 헤더에서 토큰 추출
2. JWT 서명 검증 및 만료 확인
3. payload의 `sub` (user_id)로 DB에서 사용자 조회
4. 실패 시 `401 Unauthorized` 반환

### 3.2 소유권 확인 패턴

리소스 접근 시 **존재하지 않는 경우와 권한이 없는 경우 모두 `404`로 통일**합니다.
`403`을 반환하면 리소스가 존재한다는 사실이 노출되어 정보 열거 공격에 취약해집니다.

```python
# 올바른 패턴 (기존 API 및 Generation API 공통)
project = await project_repository.find_by_id(project_id, db)
if not project or project.user_id != current_user.id:
    raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
```

> **예외**: `GET /api/v1/games/{project_id}`는 `403`을 반환합니다 (game_service 내부 구현 차이).

### 3.3 WebSocket 인증

브라우저의 WebSocket API는 `Authorization` 헤더를 지원하지 않으므로, JWT를 **쿼리 파라미터**로 전달합니다.

```
wss://api.re-verse.ai.kr/api/v1/generate/ws/{generation_id}?token=<access_token>
```

서버 처리 순서:
1. `?token=` 파라미터에서 JWT 추출
2. `decode_access_token()` 으로 서명 검증
3. payload의 `sub`로 DB에서 사용자 조회
4. `_generation_owners`에서 소유권 확인
5. 검증 실패 시 `websocket.accept()` 호출 없이 `1008 Policy Violation`으로 연결 거부

### 3.4 엔드포인트별 인증 현황

| 엔드포인트 | JWT 인증 | 소유권 확인 | 비고 |
|-----------|---------|-----------|------|
| `POST /auth/*` | ❌ | — | 공개 |
| `GET /health/*` | ❌ | — | 공개 |
| `GET /game/*` | ❌ | — | 정적 파일 공개 서빙 |
| `GET/POST/PATCH/DELETE /games/*` | ✅ | ✅ | |
| `POST /llm/process` | ✅ | ✅ | |
| `GET /llm/history/{id}` | ✅ | ✅ | |
| `POST /editor/{id}/enter` | ✅ | ✅ | |
| `POST /editor/{id}/exit` | ✅ | ✅ | |
| `POST /generate` | ✅ | ✅ | |
| `GET /generate/{id}/status` | ✅ | ✅ (404 통일) | |
| `DELETE /generate/{id}` | ✅ | ✅ (404 통일) | |
| `WS /generate/ws/{id}` | ✅ (쿼리 파라미터) | ✅ | accept 전 거부 |

---

## 4. Auth API

prefix: `/api/v1/auth` | 인증 불필요

### 4.1 회원가입

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
| `422` | 유효성 검증 실패 |

### 4.2 로그인

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

### 4.3 토큰 갱신

```
POST /api/v1/auth/refresh
```

**Request Body**
```json
{ "refresh_token": "abc123..." }
```

**Response `200 OK`** — 새로운 `TokenResponse` (Refresh Token Rotation 적용)

> Rotation: 갱신 시 기존 refresh token은 폐기(revoked)되고 새 token 발급

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 유효하지 않거나 폐기/만료된 refresh token |

### 4.4 로그아웃

```
POST /api/v1/auth/logout
```

**Response `204 No Content`** — 존재하지 않는 token으로 요청해도 에러 없이 204 반환

### 4.5 내 정보 조회

```
GET /api/v1/auth/me
```

**Headers**: `Authorization: Bearer <access_token>` 필수

**Response `200 OK`**
```json
{
  "id": 1,
  "username": "testuser",
  "email": "user@example.com",
  "created_at": "2026-03-31T12:00:00+00:00"
}
```

### 4.6 토큰 사양

| 항목 | 값 |
|------|-----|
| Access Token 유효기간 | 30분 (`JWT_EXPIRATION_MINUTES`) |
| Refresh Token 유효기간 | 24시간 (`REFRESH_TOKEN_EXPIRATION_HOURS`) |
| 알고리즘 | HS256 |
| Payload | `{ "sub": "user_id", "email": "...", "exp": ... }` |
| 저장 위치 (프론트) | Access → `sessionStorage`, Refresh → `localStorage` |

---

## 5. 게임 프로젝트 (Games)

prefix: `/api/v1/games` | `Authorization: Bearer <token>` 필수

### 5.1 목록 조회

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
      "description": "설명",
      "game_id": "game_001",
      "status": "draft",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 1
}
```

> 로그인한 사용자의 프로젝트만 반환

### 5.2 생성

```
POST /api/v1/games
```

**Request Body**
```json
{ "name": "My RPG (1~200자, 필수)", "description": "선택" }
```

**Response `201 Created`** — `ProjectResponse`

| 에러 코드 | 상황 |
|-----------|------|
| `400` | 프로젝트 수 제한 초과 (기본 3개) |
| `422` | name이 빈 문자열 |
| `500` | base_game 복사 실패 |

### 5.3 상세 조회

```
GET /api/v1/games/{project_id}
```

| 에러 코드 | 상황 |
|-----------|------|
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |

### 5.4 수정

```
PATCH /api/v1/games/{project_id}
```

**Request Body** (부분 업데이트 가능)
```json
{ "name": "New Name", "description": "New description" }
```

### 5.5 삭제

```
DELETE /api/v1/games/{project_id}
```

**Response `204 No Content`**
DB 레코드 + ConversationLog(cascade) + 게임 폴더 삭제

---

## 6. LLM Agent (LLM)

prefix: `/api/v1/llm` | `Authorization: Bearer <token>` 필수
기존 게임을 **증분 편집**하는 채팅 기반 API

### 6.1 LLM 처리 요청

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
  "intent": "게임_요소_수정",
  "success": true,
  "affected_files": ["Actors.json"],
  "reload_required": true,
  "changes_log": [
    {
      "step_id": 1,
      "tool_name": "modify_actor",
      "description": "주인공 레벨 변경",
      "success": true,
      "result_summary": "레벨 25로 설정 완료"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `code` | HTTP 상태코드 (성공 201, 실패 400/500/504) |
| `message` | Synthesizer 노드가 생성한 자연어 응답 |
| `intent` | Router 노드 분류 결과 |
| `success` | Validator 노드 통과 여부 |
| `affected_files` | 수정된 게임 JSON 파일 목록 |
| `reload_required` | 수정된 파일이 있으면 `true` |
| `changes_log` | Executor 노드 단계별 변경 이력 |

**처리 흐름**:
```
소유권 확인 → Game-Level Lock → (S3 다운로드) → LangGraph Agent
  → Router → Reader → Executor → Validator → Synthesizer
  → (S3 업로드 + 로컬 삭제) → ConversationLog DB 저장 → 응답
```

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 인증 없음 |
| `403` | 다른 사용자의 프로젝트 |
| `404` | 존재하지 않는 프로젝트 |
| `422` | message가 빈 문자열 |

### 6.2 대화 이력 조회

```
GET /api/v1/llm/history/{project_id}?limit=20&offset=0
```

**Response `200 OK`**
```json
[
  {
    "id": 1,
    "user_input": "레벨을 25로 설정해줘",
    "agent_response": "완료했습니다.",
    "intent": "modify_level",
    "success": true,
    "processing_time": 2.34,
    "timestamp": "2026-03-31T12:05:00+00:00"
  }
]
```

> 최신 순 정렬 (timestamp DESC)

---

## 7. 에디터 (Editor)

prefix: `/api/v1/editor` | `Authorization: Bearer <token>` 필수
프론트엔드 에디터 세션의 S3 ↔ 로컬 동기화를 담당

### 7.1 에디터 진입

```
POST /api/v1/editor/{project_id}/enter
```

**동작**:
1. 소유권 확인
2. 이미 같은 사용자의 활성 세션이면 재진입 허용 (새로고침 등)
3. 다른 사용자의 활성 세션이면 `409`
4. S3 모드: S3 → 로컬 다운로드
5. 세션 등록 (`session_manager`)

**Response `200 OK`**
```json
{ "status": "ok", "game_id": "game_001" }
```

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 인증 없음 |
| `404` | 존재하지 않는 프로젝트 또는 소유권 없음 |
| `409` | 다른 사용자가 편집 중 |

### 7.2 에디터 퇴장

```
POST /api/v1/editor/{project_id}/exit
```

**동작**:
1. 소유권 확인
2. S3 모드: 로컬 → S3 업로드 후 로컬 폴더 삭제
3. 세션 해제

**Response `200 OK`**
```json
{ "status": "ok" }
```

---

## 8. 게임 생성 (Generation)

prefix: `/api/v1/generate` | `Authorization: Bearer <token>` 필수
프롬프트 한 번으로 전체 RPG 게임을 생성하는 비동기 API
LangGraph 워크플로우를 백그라운드 태스크로 실행하며 WebSocket으로 진행률을 실시간 스트리밍

### 8.1 생성 시작

```
POST /api/v1/generate
```

**Request Body**
```json
{
  "project_id": 1,
  "prompt": "마법사가 주인공인 판타지 RPG (5~1000자)",
  "options": {
    "playtime_minutes": 7,
    "seed": null,
    "phase_limit": null,
    "map_source": null
  }
}
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `playtime_minutes` | `7` | 목표 플레이타임 (5~15분, 맵 수 결정) |
| `seed` | `null` | 재현 가능한 생성을 위한 시드 |
| `phase_limit` | `null` | `"assets"` \| `"maps"` \| `null` (전체) — 디버그용 |
| `map_source` | `null` | `"samples"` \| `null` (알고리즘 생성) |

**Response `202 Accepted`**
```json
{
  "generation_id": "gen_a1b2c3d4",
  "status": "started",
  "estimated_seconds": 60,
  "ws_url": "/api/v1/generate/ws/gen_a1b2c3d4"
}
```

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 인증 없음 |
| `404` | 존재하지 않는 프로젝트 또는 소유권 없음 |
| `422` | prompt가 5자 미만 또는 1000자 초과 |

### 8.2 진행 상태 폴링

```
GET /api/v1/generate/{generation_id}/status
```

WebSocket 연결이 불가능할 때 폴링 폴백으로 사용

**Response `200 OK`**
```json
{
  "generation_id": "gen_a1b2c3d4",
  "status": "in_progress",
  "progress": 45,
  "phase": "map_design",
  "message": "맵을 설계하고 있습니다...",
  "completed_phases": ["spec", "planning", "assets"],
  "is_success": null,
  "final_message": null,
  "validation_errors": [],
  "error_message": null
}
```

| `status` 값 | 의미 |
|------------|------|
| `in_progress` | 생성 중 |
| `completed` | 성공적으로 완료 |
| `completed_with_warnings` | 완료 (검증 경고 있음) |
| `failed` | 실패 |
| `cancelled` | 취소됨 |

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 인증 없음 |
| `404` | 존재하지 않거나 소유권 없음 (두 경우 모두 404 — 존재 여부 비노출) |

### 8.3 생성 취소

```
DELETE /api/v1/generate/{generation_id}
```

**Response `204 No Content`**
현재 구현: 상태를 `cancelled`로 변경 (실행 중인 워크플로우 강제 중단 미지원)

| 에러 코드 | 상황 |
|-----------|------|
| `401` | 인증 없음 |
| `404` | 존재하지 않거나 소유권 없음 |

### 8.4 WebSocket 실시간 스트리밍

```
WS /api/v1/generate/ws/{generation_id}?token=<access_token>
```

> 브라우저 WebSocket API는 커스텀 헤더를 지원하지 않으므로 JWT를 쿼리 파라미터로 전달

**인증 실패 시**: `accept()` 호출 없이 `1008 Policy Violation` 코드로 연결 거부

**이벤트 메시지 형식** (JSON)

```json
{ "type": "phase_complete", "phase": "assets", "progress": 40, "message": "에셋 생성 완료" }
{ "type": "completed", "progress": 100, "message": "게임이 완성됐습니다!" }
{ "type": "completed_with_warnings", "progress": 100, "warnings": ["..."] }
{ "type": "error", "message": "생성 실패: ..." }
```

| `type` 값 | 의미 |
|----------|------|
| `phase_complete` | 단일 노드 완료 |
| `completed` | 전체 생성 성공 |
| `completed_with_warnings` | 생성 성공 (검증 경고 포함) |
| `error` | 실패 또는 취소 |

**프론트엔드 연동 예시**
```javascript
const { generation_id, ws_url } = await startGenerationResponse.json()
const token = sessionStorage.getItem('access_token')
const ws = new WebSocket(`${WS_BASE}${ws_url}?token=${encodeURIComponent(token)}`)

ws.onmessage = (e) => {
  const event = JSON.parse(e.data)
  dispatch(wsEventReceived(event))
  if (['completed', 'completed_with_warnings', 'error'].includes(event.type)) {
    ws.close()
  }
}
ws.onerror = () => startPollingFallback()  // GET /status 폴링으로 전환
```

### 8.5 생성 워크플로우 단계

| 단계 | 노드 | LLM 호출 | 출력 |
|------|------|---------|------|
| A | `game_designer` | ✅ 1회 | GameSpec (제목, 스토리, 에셋 목록) |
| B | `asset_planner` | ❌ | IdTable, SwitchTable |
| C | `asset_generator` | ✅ 5~6회 (병렬) | Actors/Skills/Items/Enemies JSON |
| D | `map_designer` | ✅ 1회 | MapSpec 목록 |
| E | `tile_generator` | ❌ | 타일 배열 (BSP/그리드 알고리즘) |
| F | `event_planner` | ✅ 맵 수×1회 | 이벤트 DSL (YAML) |
| G | `event_compiler` | ❌ | RPG Maker MZ 이벤트 커맨드 |
| H | `integrator` | ❌ | System.json, MapInfos.json |
| I | `validator` | ❌ | 검증 오류, 재시도 여부 결정 |
| J | `responder` | ❌ | 최종 메시지, WebSocket 브로드캐스트 |

**총 소요 시간**: 60~120초 | **LLM 호출 수**: 8~10회

### 8.6 상태 저장 방식

Generation API는 현재 **인메모리 딕셔너리**로 상태를 관리합니다.

```python
_generation_states: dict[str, GenerationStatusResponse]  # 진행 상태
_generation_owners: dict[str, int]                        # generation_id → user_id
```

> **제한사항**: 서버 재시작 시 진행 중인 generation 상태가 초기화됩니다.
> Phase 2 개선 계획: `Generation` DB 테이블로 영속화

---

## 9. 헬스체크

인증 불필요

| 엔드포인트 | 용도 | 응답 예시 |
|-----------|------|----------|
| `GET /health` | 서버 기본 상태 | `{"status": "healthy", "message": "Re:Verse Backend is running"}` |
| `GET /health/db` | RDS 연결 확인 | `{"ok": true, "detail": "ok"}` |
| `GET /health/s3` | S3 버킷 접근 확인 | `{"ok": true, "detail": "ok"}` |
| `GET /` | 루트 | `{"message": "Welcome to Re:Verse API", "docs": "/docs"}` |

> `health/db`: `DATABASE_URL` 미설정 시 `{"ok": true, "detail": "skipped"}`
> `health/s3`: `STORAGE_BACKEND=local` 시 `{"ok": true, "detail": "skipped"}`

---

## 10. 인프라 (RDS / S3)

### 10.1 RDS (PostgreSQL)

| 항목 | 값 |
|------|-----|
| 접속 | `DATABASE_URL` 환경 변수 |
| 로컬 개발 | `sqlite+aiosqlite:///./storage/reverse.db` |
| ORM | SQLAlchemy 2.x (async) |

**DB 테이블**

| 테이블 | 설명 | 주요 컬럼 |
|--------|------|-----------|
| `users` | 사용자 | id, username, email, hashed_password |
| `projects` | 게임 프로젝트 | id, user_id(FK), name, game_id(unique), status |
| `conversation_logs` | LLM 대화 이력 | id, project_id(FK), user_input, agent_response, intent, success, processing_time |
| `refresh_tokens` | 리프레시 토큰 | id, token(unique), user_id(FK), expires_at, revoked |

**관계**
```
User (1) ──< Project (N) ──< ConversationLog (N)
User (1) ──< RefreshToken (N)
```

- `projects` 삭제 시 `conversation_logs` cascade 삭제
- `users` 삭제 시 `projects`, `refresh_tokens` cascade 삭제

### 10.2 S3

| 항목 | 값 |
|------|-----|
| 버킷 | `upstage-sesac-31-reverse-project-s3` |
| 리전 | `ap-northeast-2` |
| 인증 | EC2 IAM Role |

**S3 키 구조**
```
games/
├── base_game/           ← 프로젝트 생성 시 복사 원본
│   └── data/
├── game_001/            ← 프로젝트별 게임 데이터
│   └── data/
└── game_002/
    └── data/
```

| S3 접근 시점 | 동작 |
|------------|------|
| 프로젝트 생성 | `base_game/` → `game_00x/` 복사 |
| 프로젝트 삭제 | `game_00x/` 전체 삭제 |
| LLM 호출 전 | S3 → 로컬 다운로드 |
| LLM 호출 후 | 로컬 → S3 업로드 |
| 게임 생성 완료 | 로컬 → S3 업로드 |

---

## 11. 에러 응답 형식

### 유효성 검증 에러 (422)
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "input": "1234"
    }
  ]
}
```

### 비즈니스 에러 (401, 403, 404, 409 등)
```json
{ "detail": "이미 등록된 이메일입니다." }
```

### 서버 내부 에러 (500, 글로벌 핸들러)
```json
{
  "error": "Internal Server Error",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

> 모든 응답에 `X-Request-ID` 헤더가 포함됩니다 (디버깅용)

---

## 12. 환경 변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `DATABASE_URL` | ✅ | — | DB 접속 문자열 |
| `JWT_SECRET_KEY` | ✅ | — | 비어 있으면 서버 시작 차단 |
| `JWT_ALGORITHM` | — | `HS256` | JWT 알고리즘 |
| `JWT_EXPIRATION_MINUTES` | — | `30` | Access Token 유효기간 (분) |
| `REFRESH_TOKEN_EXPIRATION_HOURS` | — | `24` | Refresh Token 유효기간 (시간) |
| `ENVIRONMENT` | — | `development` | `development` / `production` |
| `DEBUG` | — | `true` | 디버그 모드 |
| `CORS_ORIGINS` | — | localhost + re-verse.ai.kr | 허용 Origin (쉼표 구분) |
| `STORAGE_PATH` | — | `./storage/games` | 게임 파일 로컬 경로 |
| `BASE_GAME_PATH` | — | `./storage/games/base_game` | 기본 게임 템플릿 경로 |
| `STORAGE_BACKEND` | — | `local` | `local` / `s3` |
| `MAX_PROJECTS_PER_USER` | — | `3` | 사용자당 프로젝트 수 제한 |
| `AWS_REGION` | — | `ap-northeast-2` | S3 리전 |
| `S3_BUCKET_NAME` | — | `upstage-sesac-31-reverse-project-s3` | S3 버킷명 |
| `S3_PREFIX` | — | `games` | S3 prefix |
| `LOG_LEVEL` | — | 자동 결정 | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_DIR` | — | `./logs` | 로그 파일 저장 경로 |
