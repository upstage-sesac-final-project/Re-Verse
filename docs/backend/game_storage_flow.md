# 게임 파일 저장 흐름 (Local / S3)

## 설정

`.env`의 `STORAGE_BACKEND` 값으로 모드 결정:
- `local` — 로컬 디스크만 사용 (개발용)
- `s3` — S3 + EC2 로컬 캐시 (프로덕션)

```
STORAGE_BACKEND=local   # 또는 s3
STORAGE_PATH=./storage/games
BASE_GAME_PATH=./storage/games/base_game
S3_BUCKET_NAME=upstage-sesac-31-reverse-project-s3
S3_PREFIX=games
```

---

## 저장 구조

### 프로젝트별 저장 대상
- `data/` (JSON 15개, ~556KB) — 프로젝트마다 다름 (편집 대상)
- `img/`, `audio/`, `js/`, `css/`, `fonts/`, `index.html` 등 — 모든 프로젝트가 공유 (base_game)

### Local 모드
```
storage/games/
├── base_game/              ← 전체 파일 (img, js, data 등 100MB)
│   ├── index.html
│   ├── js/
│   ├── img/                ← 53MB
│   ├── audio/
│   └── data/               ← 556KB (복사 원본)
├── game_abc123/
│   └── data/               ← base_game/data에서 복사된 JSON
└── game_def456/
    └── data/
```

### S3 모드
```
[S3 버킷]
games/
├── base_game/              ← 전체 파일 (공유 에셋 서빙 + data 복사 원본)
│   ├── index.html
│   ├── img/
│   └── data/
├── game_abc123/
│   └── data/               ← 프로젝트별 JSON만 저장
└── game_def456/
    └── data/

[EC2 로컬 (편집 세션 중에만 존재)]
/app/storage/games/
├── game_abc123/
│   └── data/               ← 세션 진입 시 S3에서 다운로드, 이탈 시 삭제
```

---

## 1. 게임 생성

> 사용자가 "새 프로젝트" 만들기를 클릭했을 때

### Local 모드
```
POST /api/v1/games

1. DB에 Project 레코드 생성 (game_id = game_{uuid8자리})
2. 로컬 base_game/data/ → 로컬 game_xxx/data/ 복사 (shutil.copytree)
3. 완료
```

### S3 모드
```
POST /api/v1/games

1. DB에 Project 레코드 생성
2. S3 base_game/data/ → S3 game_xxx/data/ 복사 (copy_object × 15회)
   ※ S3 서버 사이드 복사 — EC2를 거치지 않음
3. 완료 (1~2초)
```

**관련 코드:** `app/backend/services/game_service.py` → `_copy_base_game()`, `_s3_copy_base_game()`

---

## 2. 편집 세션 진입

> 사용자가 편집 페이지(/editor/:projectId)로 이동했을 때

### Local 모드
```
POST /api/v1/editor/{project_id}/enter

1. 소유권 확인
2. 세션 레지스트리에 등록 (이미 활성이면 409)
3. 로컬에 game_xxx/data/ 이미 있으므로 추가 작업 없음
4. 응답: { status: "ok", game_id: "game_xxx" }
```

### S3 모드
```
POST /api/v1/editor/{project_id}/enter

1. 소유권 확인
2. 세션 레지스트리에 등록 (이미 활성이면 409)
3. S3 game_xxx/data/ → EC2 로컬 game_xxx/data/ 다운로드 (15개 JSON)
4. 응답: { status: "ok", game_id: "game_xxx" }
```

**관련 코드:** `app/backend/api/v1/endpoints/editor.py` → `enter_editor()`

---

## 3. 편집 중 명령 수행

> 사용자가 채팅으로 "슬라임 HP를 500으로 수정해줘" 같은 명령을 보냈을 때

### Local 모드
```
POST /api/v1/llm/process

1. 세션 검증 (S3 모드만)
2. Game lock 획득
3. Agent(LangGraph) 실행 → 로컬 game_xxx/data/*.json 직접 수정
4. 완료 — S3 동기화 없음
```

### S3 모드
```
POST /api/v1/llm/process

1. 세션 활성 검증 (비활성이면 400 에러)
2. Game lock 획득
3. Agent(LangGraph) 실행 → EC2 로컬 game_xxx/data/*.json 직접 수정
4. 성공 시: 백그라운드 S3 업로드 (fire-and-forget, 안전장치)
   - 실패해도 사용자에게 알리지 않음
   - 다음 명령 성공 시 다시 시도
5. 완료
```

**핵심:** 명령마다 S3 다운로드/업로드를 하지 않음. 로컬에서 직접 수정.

**관련 코드:** `app/backend/services/llm_service.py` → `process_chat()`, `_background_s3_upload()`

---

## 4. 편집 세션 종료

> 사용자가 편집 페이지에서 나갔을 때 (뒤로가기, 로그아웃, 탭 닫기)

### Local 모드
```
POST /api/v1/editor/{project_id}/exit

1. 세션 레지스트리에서 해제
2. 로컬 game_xxx/data/ 유지 (삭제하지 않음)
3. 완료
```

### S3 모드
```
POST /api/v1/editor/{project_id}/exit

1. EC2 로컬 game_xxx/data/ → S3 game_xxx/data/ 최종 업로드
2. EC2 로컬 game_xxx/ 폴더 삭제 (디스크 절약)
3. 세션 레지스트리에서 해제
4. 완료
```

**프론트엔드 호출 방식:**
- React cleanup (라우팅 이동): `exitEditor(projectId)` (일반 fetch)
- 탭 닫기/새로고침: `exitEditorBeacon(projectId)` (keepalive fetch)

**관련 코드:**
- Backend: `app/backend/api/v1/endpoints/editor.py` → `exit_editor()`
- Frontend: `app/frontend/src/pages/GameEditor.jsx`, `app/frontend/src/services/editorApi.js`

---

## 5. 게임 파일 서빙 (프리뷰)

> 프론트엔드 iframe이 `/game/{game_id}/index.html`을 로드할 때

### 우선순위 (Local / S3 공통)
```
GET /game/{game_id}/{path}

1순위: EC2 로컬 storage/games/{game_id}/{path}    ← data/ JSON
2순위: EC2 로컬 storage/games/base_game/{path}     ← img, js, css 등
3순위 (S3 모드만): S3 redirect
   - data/ 요청 → S3 games/{game_id}/{path}
   - 그 외      → S3 games/base_game/{path}
```

### 예시

| 요청 | Local 모드 | S3 모드 (base_game 로컬에 없을 때) |
|------|-----------|----------------------------------|
| `data/Actors.json` | `game_xxx/data/Actors.json` | `game_xxx/data/Actors.json` (세션 중) |
| `img/World_A1.png` | `base_game/img/World_A1.png` | S3 redirect → `games/base_game/img/World_A1.png` |
| `index.html` | `base_game/index.html` | S3 redirect → `games/base_game/index.html` |
| `js/main.js` | `base_game/js/main.js` | S3 redirect → `games/base_game/js/main.js` |

**관련 코드:** `app/backend/main.py` → `serve_game_file()`

---

## 6. 안전장치

### 비정상 종료 대비

| 시나리오 | 안전장치 | 데이터 손실 |
|---------|---------|-----------|
| 정상 이탈 (뒤로가기/로그아웃) | `/exit` → S3 최종 업로드 | 없음 |
| 탭 강제 닫기 / 브라우저 크래시 | 명령 성공 시 백그라운드 S3 업로드 | 마지막 명령까지 보존 |
| 서버 재시작 / 배포 | shutdown hook → 활성 세션 일괄 S3 업로드 | 없음 |
| 서버 크래시 | 다음 startup 시 orphan 폴더 S3 업로드 후 삭제 | 없음 |
| S3 업로드 실패 | 로컬 유지, 다음 시도 시 재시도 | 없음 |
| 동일 게임 다중 탭 열기 | `/enter` 시 409 반환 → 차단 | 없음 |

### 관련 코드
- 세션 관리: `app/backend/services/session_manager.py`
- Startup orphan 정리 / Shutdown hook: `app/backend/main.py` → `lifespan()`
- Docker 종료 대기: `docker-compose.prod.yml` → `stop_grace_period: 30s`

---

## 7. 게임 삭제

### Local 모드
```
DELETE /api/v1/games/{project_id}

1. DB 레코드 삭제 (cascade: conversation_logs도 삭제)
2. 세션 해제 + game lock 정리
3. 로컬 game_xxx/ 폴더 삭제
```

### S3 모드
```
DELETE /api/v1/games/{project_id}

1. DB 레코드 삭제
2. 세션 해제 + game lock 정리
3. S3 games/{game_id}/ prefix 전체 삭제
4. EC2 로컬 game_xxx/ 폴더 삭제 (있으면)
```

**관련 코드:** `app/backend/services/game_service.py` → `delete_project()`

---

## 전체 흐름 다이어그램

### Local 모드
```
[생성] base_game/data/ → game_xxx/data/ (로컬 복사)
  ↓
[편집 진입] 세션 등록
  ↓
[명령 N회] 로컬 data/ 직접 수정
  ↓
[편집 이탈] 세션 해제 (로컬 데이터 유지)
  ↓
[게임 플레이] data/ → game_xxx, img/js/css → base_game fallback
```

### S3 모드
```
[생성] S3 base_game/data/ → S3 game_xxx/data/ (S3 내부 복사)
  ↓
[편집 진입] S3 → EC2 다운로드 (data/ 15개 JSON) + 세션 등록
  ↓
[명령 N회] EC2 로컬 data/ 직접 수정 + 백그라운드 S3 업로드
  ↓
[편집 이탈] EC2 → S3 최종 업로드 + EC2 로컬 삭제 + 세션 해제
  ↓
[게임 플레이] data/ → S3 redirect, img/js/css → S3 base_game redirect
```
