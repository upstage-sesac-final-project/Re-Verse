# Backend Storage

## 저장 흐름

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

---

## 최적화

# 게임 저장소 최적화 설계서

## 1. 현재 구조의 문제점

### 현재 흐름

```
[게임 생성]
S3 base_game/ (1,319개 파일, 101MB) → S3 copy_object × 1,319회 → games/{game_id}/

[게임 편집]
S3 games/{game_id}/ 전체 → EC2 로컬 다운로드 (1,319개)
→ data/*.json 1~2개 수정
→ EC2 로컬 전체 → S3 업로드 (1,319개)
→ EC2 로컬 폴더 삭제

[게임 플레이]
프론트엔드 iframe → /game/{game_id}/index.html → StaticFiles(STORAGE_PATH)
```

### 문제
- **게임 생성**: S3 내부 복사 1,319회 → 수십 초 소요
- **게임 편집**: 매 요청마다 1,319개 파일 다운로드/업로드 → 대부분 불필요한 전송
- **실제 수정 대상**: `data/*.json` 23개 파일 (전체의 ~2%)
- 나머지 98% (img, audio, js, effects, fonts 등)는 base_game과 동일하며 변경되지 않음

---

## 2. 개선 구조

### 핵심 아이디어
> **base_game의 정적 에셋은 공유하고, 게임별로 data/ 폴더만 분리 관리한다.**

### 저장 구조 변경

```
[AS-IS] S3
games/
├── base_game/          ← 전체 (1,319개)
├── game_abc123/        ← 전체 복사본 (1,319개) ← 대부분 base_game과 동일
└── game_def456/        ← 전체 복사본 (1,319개)

[TO-BE] S3
games/
├── base_game/
│   └── data/           ← JSON 23개만 (복사 원본)
├── game_abc123/
│   └── data/           ← JSON 23개만 (게임별 고유 데이터)
└── game_def456/
    └── data/           ← JSON 23개만
```

```
[TO-BE] EC2 로컬 (STORAGE_PATH)
storage/games/
├── base_game/          ← 전체 파일 (에셋 fallback 서빙용, 변경 없음)
├── game_abc123/
│   └── data/           ← JSON만 (S3에서 동기화)
└── game_def456/
    └── data/           ← JSON만
```

### 개선 효과

| 작업 | AS-IS | TO-BE |
|------|-------|-------|
| 게임 생성 (S3 복사) | 1,319개 파일 복사 | 23개 파일 복사 |
| 게임 편집 (S3→로컬) | 1,319개 다운로드 | 23개 다운로드 |
| 게임 편집 (로컬→S3) | 1,319개 업로드 | 변경된 1~2개만 업로드 |
| 게임 플레이 | 전체 파일 필요 | fallback 라우터로 해결 |

---

## 3. 수정 대상 파일 및 변경 내용

### 3-1. `app/backend/main.py` — StaticFiles → Fallback 라우터

**현재 코드:**
```python
# L122-127
app.mount(
    "/game",
    StaticFiles(directory=settings.STORAGE_PATH, html=True),
    name="game",
)
```

**변경 내용:**
StaticFiles 마운트를 제거하고, 커스텀 라우터로 교체한다.

```python
from fastapi.responses import FileResponse

@app.get("/game/{game_id}/{file_path:path}")
async def serve_game_file(game_id: str, file_path: str):
    """게임 파일 서빙: game_id 폴더 우선 → base_game fallback."""
    storage = Path(settings.STORAGE_PATH).resolve()

    # 1순위: 해당 게임 폴더
    game_file = storage / game_id / file_path
    if game_file.is_file():
        return FileResponse(game_file)

    # 2순위: base_game fallback (에셋, JS, HTML 등)
    base_file = storage / "base_game" / file_path
    if base_file.is_file():
        return FileResponse(base_file)

    raise HTTPException(status_code=404, detail="File not found")
```

**동작 방식:**
- `/game/game_abc123/index.html` → game_abc123에 없음 → base_game/index.html 서빙
- `/game/game_abc123/data/Actors.json` → game_abc123/data/Actors.json 서빙 (있음)
- `/game/game_abc123/img/characters/Actor1.png` → 없음 → base_game/img/... 서빙
- 브라우저 URL이 `/game/game_abc123/`이므로, index.html 내 상대 경로가 모두 이 경로 기준으로 해석됨

**프론트엔드 변경: 없음**
- `RPGMakerFrame.jsx`의 `<iframe src={/game/${gameId}/index.html}>` 그대로 유지
- RPG Maker MZ JS 파일 수정 없음

---

### 3-2. `app/backend/services/game_service.py` — 게임 생성 시 data/만 복사

**현재 코드 (`_s3_copy_base_game`, L175-193):**
base_game/ 아래 전체 1,319개 파일을 copy_object로 복사

**변경 내용:**
`data/` 하위 파일만 복사하도록 prefix 제한

```python
def _s3_copy_base_game(self, game_id: str) -> None:
    client = boto3.client("s3", region_name=settings.AWS_REGION)
    bucket = settings.S3_BUCKET_NAME
    prefix = settings.S3_PREFIX.strip("/")
    src_prefix = f"{prefix}/base_game/data/"       # ← data/만
    dst_prefix = f"{prefix}/{game_id}/data/"        # ← data/만
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=src_prefix):
        for obj in page.get("Contents", []):
            src_key = obj["Key"]
            rel = src_key[len(src_prefix):]
            if not rel:
                continue
            dst_key = f"{dst_prefix}{rel}"
            client.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": src_key},
                Key=dst_key,
            )
```

**로컬 모드 (`_copy_base_game`)도 동일하게 변경:**
```python
def _copy_base_game(self, game_id: str) -> None:
    if settings.STORAGE_BACKEND == "s3":
        self._s3_copy_base_game(game_id)
    else:
        src = Path(settings.BASE_GAME_PATH).resolve() / "data"
        dst = Path(settings.STORAGE_PATH).resolve() / game_id / "data"
        if not src.exists():
            raise FileNotFoundError(f"base_game/data 경로 없음: {src}")
        shutil.copytree(src, dst)
```

---

### 3-3. `app/backend/services/s3_game_storage.py` — 선택적 동기화

**변경 1: `sync_game_from_s3` — data/만 다운로드**

```python
def sync_game_from_s3(game_id: str) -> None:
    """S3의 games/{game_id}/data/ 아래 JSON만 로컬로 내려받는다."""
    if settings.STORAGE_BACKEND != "s3":
        return

    client = _s3_client()
    bucket = settings.S3_BUCKET_NAME
    prefix = _game_s3_prefix(game_id) + "data/"     # ← data/만
    local_root = Path(settings.STORAGE_PATH).resolve() / game_id
    local_root.mkdir(parents=True, exist_ok=True)

    paginator = client.get_paginator("list_objects_v2")
    downloaded = 0
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                rel = key[len(_game_s3_prefix(game_id)):].lstrip("/")
                if not rel:
                    continue
                dest = local_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket, key, str(dest))
                downloaded += 1
    except ClientError as e:
        logger.error("S3 download 실패 game_id=%s: %s", game_id, e)
        raise

    logger.info("S3 → 로컬 동기화 완료 game_id=%s files=%d", game_id, downloaded)
```

**변경 2: `sync_game_to_s3` — 변경된 파일만 업로드**

```python
def sync_game_to_s3(game_id: str, modified_files: list[str] | None = None) -> None:
    """변경된 파일만 S3에 업로드한다.

    Args:
        game_id: 게임 ID
        modified_files: 변경된 파일 상대 경로 목록 (예: ["data/Actors.json"])
                        None이면 data/ 전체 업로드
    """
    if settings.STORAGE_BACKEND != "s3":
        return

    local_root = Path(settings.STORAGE_PATH).resolve() / game_id
    if not local_root.is_dir():
        logger.warning("업로드할 로컬 게임 폴더 없음: %s", local_root)
        return

    client = _s3_client()
    bucket = settings.S3_BUCKET_NAME
    prefix = _game_s3_prefix(game_id)
    uploaded = 0

    try:
        if modified_files:
            # 변경된 파일만 업로드
            for rel_path in modified_files:
                local_file = local_root / rel_path
                if local_file.is_file():
                    key = f"{prefix}{rel_path}"
                    client.upload_file(str(local_file), bucket, key)
                    uploaded += 1
        else:
            # modified_files 미지정 시 data/ 전체 업로드 (fallback)
            data_dir = local_root / "data"
            if data_dir.is_dir():
                for path in data_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(local_root)
                    key = f"{prefix}{rel.as_posix()}"
                    client.upload_file(str(path), bucket, key)
                    uploaded += 1
    except ClientError as e:
        logger.error("S3 upload 실패 game_id=%s: %s", game_id, e)
        raise

    logger.info("로컬 → S3 업로드 완료 game_id=%s files=%d", game_id, uploaded)
```

---

### 3-4. `app/backend/services/llm_service.py` — 변경 파일 목록 전달

**현재 코드 (L134-142):**
```python
if settings.STORAGE_BACKEND == "s3":
    if result["success"]:
        await asyncio.to_thread(sync_game_to_s3, game_id)
    local_game_dir = Path(settings.STORAGE_PATH).resolve() / game_id
    if local_game_dir.is_dir():
        await asyncio.to_thread(shutil.rmtree, local_game_dir)
```

**변경 내용:**
Agent 결과의 `affected_files`를 활용하여 변경된 파일만 업로드

```python
if settings.STORAGE_BACKEND == "s3":
    if result["success"]:
        # affected_files: ["Actors.json", "Skills.json"] 형태
        # → S3 업로드용: ["data/Actors.json", "data/Skills.json"]
        affected = result.get("affected_files", [])
        modified_files = [f"data/{f}" for f in affected] if affected else None
        await asyncio.to_thread(sync_game_to_s3, game_id, modified_files)
    local_game_dir = Path(settings.STORAGE_PATH).resolve() / game_id
    if local_game_dir.is_dir():
        await asyncio.to_thread(shutil.rmtree, local_game_dir)
```

---

## 4. EC2에 base_game 배치 방법 (배포 담당자 확인 필요)

fallback 라우터가 동작하려면 EC2 로컬의 `STORAGE_PATH/base_game/`에 전체 에셋이 존재해야 한다.
아래 두 가지 방법 중 하나를 선택해야 한다.

### 방법 A: Docker 이미지에 포함 (추천)

```dockerfile
# Dockerfile
COPY storage/games/base_game /app/storage/games/base_game
```

- 장점: 서버 시작 즉시 사용 가능, 외부 의존 없음
- 단점: Docker 이미지 크기 +101MB 증가
- base_game 변경 시 이미지 재빌드 필요

### 방법 B: 서버 시작 시 S3에서 1회 다운로드

```python
# main.py — startup event
@app.on_event("startup")
async def ensure_base_game():
    """EC2 환경에서 base_game이 로컬에 없으면 S3에서 1회 다운로드."""
    base_path = Path(settings.BASE_GAME_PATH).resolve()
    if not base_path.exists() and settings.STORAGE_BACKEND == "s3":
        logger.info("base_game 로컬 없음 → S3에서 다운로드 시작")
        sync_game_from_s3_full("base_game")  # data/ 제한 없이 전체 다운로드
        logger.info("base_game 다운로드 완료")
```

- 장점: Docker 이미지 경량 유지
- 단점: 최초 서버 시작 시 101MB 다운로드 소요 (1회만), S3에 base_game 전체 유지 필요
- 이 방법을 선택할 경우 S3에는 base_game 전체를 유지해야 함

### 비교

| | 방법 A (Docker) | 방법 B (S3 다운로드) |
|---|---|---|
| Docker 이미지 크기 | +101MB | 변화 없음 |
| 서버 시작 시간 | 즉시 | +수십 초 (1회만) |
| S3 base_game | data/만 있으면 됨 | 전체 필요 |
| base_game 업데이트 | 이미지 재빌드 | S3만 업데이트 |

---

## 5. 전체 흐름 비교

### AS-IS (현재)

```
[게임 생성]
1. DB에 Project 레코드 생성
2. S3: base_game/ 전체 → game_{id}/ 전체 복사 (1,319개 copy_object)
   소요 시간: 수십 초

[게임 편집 (채팅)]
1. S3 → EC2: game_{id}/ 전체 다운로드 (1,319개)
2. Agent가 data/*.json 1~2개 수정
3. EC2 → S3: game_{id}/ 전체 업로드 (1,319개)
4. EC2 로컬 game_{id}/ 삭제
   소요 시간: 다운로드 + 처리 + 업로드

[게임 플레이]
프론트 iframe → /game/{game_id}/index.html → StaticFiles → 로컬 전체 파일 필요
※ 편집 후 로컬 삭제하므로, 플레이 시 다시 S3에서 전체 동기화 필요할 수 있음
```

### TO-BE (개선)

```
[서버 시작 (1회)]
EC2 로컬에 base_game/ 전체 확보 (Docker 포함 또는 S3 1회 다운로드)

[게임 생성]
1. DB에 Project 레코드 생성
2. S3: base_game/data/ → game_{id}/data/ 복사 (23개 copy_object)
3. EC2: game_{id}/data/ 로컬 동기화 (23개 다운로드)
   소요 시간: 1~2초

[게임 편집 (채팅)]
1. S3 → EC2: game_{id}/data/ 만 다운로드 (23개)
2. Agent가 data/*.json 1~2개 수정
3. EC2 → S3: 변경된 파일만 업로드 (1~2개)
4. EC2 로컬 game_{id}/data/ 유지 (플레이를 위해 삭제하지 않음)
   소요 시간: 대폭 단축

[게임 플레이]
프론트 iframe → /game/{game_id}/index.html
→ fallback 라우터:
  - data/ → game_{id}/data/ (게임별 고유 데이터)
  - 그 외 → base_game/ (공유 에셋)
```

---

## 6. 배포 담당자 확인 사항

- [ ] Docker 이미지에 base_game (101MB)을 포함할 수 있는지? (방법 A vs B 결정)
- [ ] EC2의 `STORAGE_PATH` 디렉토리가 컨테이너 재시작 시에도 유지되는지? (볼륨 마운트 여부)
  - 유지되지 않으면 게임 편집 후 로컬 data/가 사라지므로, 매 플레이 시 S3 동기화 필요
  - 유지되면 로컬 data/를 삭제하지 않아도 되어 플레이 성능 향상
- [ ] S3에서 base_game의 에셋 파일을 삭제해도 되는지? (방법 A 선택 시)

---

## 7. 추가 고려 사항

### 7-1. 로컬 data/ 삭제 정책
현재 `llm_service.py`에서 편집 완료 후 로컬 폴더 전체를 삭제하고 있다 (L139-142).
개선 후에는 data/만 존재하므로 삭제 여부를 선택할 수 있다:
- **삭제하는 경우**: 디스크 절약, 매 편집/플레이 시 S3에서 data/ 재다운로드
- **삭제하지 않는 경우**: 플레이 시 즉시 서빙 가능, 디스크 사용량 약간 증가 (게임당 ~수백KB)
- 추천: data/는 용량이 작으므로 **삭제하지 않는 것**이 성능에 유리

### 7-2. 게임 삭제
`game_service.py`의 `_s3_delete_game`은 현재와 동일하게 `games/{game_id}/` prefix 전체 삭제.
data/만 있으므로 삭제도 빠르게 완료된다.

### 7-3. 로컬 개발 환경 (STORAGE_BACKEND=local)
로컬에서는 base_game/ 전체가 이미 존재하므로 fallback 라우터만 적용하면 동일하게 동작한다.
게임 생성 시 data/만 복사하도록 `_copy_base_game`의 로컬 분기도 함께 수정한다.
