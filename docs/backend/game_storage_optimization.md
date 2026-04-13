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
