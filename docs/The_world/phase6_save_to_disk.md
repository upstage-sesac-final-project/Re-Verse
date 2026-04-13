# Phase 6 — 생성 결과 디스크 저장 + 인게임 플레이 연결

> 상태: 미구현
> 우선순위: **긴급** — 없으면 생성된 게임을 플레이할 수 없음

---

## 현재 문제

### 1. `final_project`가 메모리에만 존재

`run_generation_workflow()` 완료 후 `final_project` dict가 메모리에만 있음.
`storage/games/{game_id}/data/`에 파일이 쓰이지 않아 생성 결과가 반영되지 않는다.

### 2. `game_id` 불일치 버그 (구조적 문제)

```python
# generation.py 현재 코드 — 잘못됨
game_id = str(project_id)   # → "1", "2", "3" ...
```

실제 게임 파일 경로는 `project.game_id` 필드 ("game_a1b2c3d4" 형태).
`GameEditor`도 `currentProject?.game_id`를 사용한다.
현재 코드대로면 `storage/games/1/`에 저장하려 해서 경로가 완전히 틀린다.

---

## 저장 경로 구조 (기존 인프라)

```
storage/games/{project.game_id}/     ← "game_a1b2c3d4" 형태
├── index.html                        ← RPG Maker MZ 엔진
├── js/ audio/ img/ fonts/ ...        ← 엔진 리소스
└── data/                             ← ← ← 여기에 저장
    ├── Actors.json
    ├── Classes.json
    ├── ...
    ├── System.json
    ├── MapInfos.json
    ├── Map001.json
    └── ...
```

`app/backend/core/game_paths.get_game_data_path(game_id)` → `storage/games/{game_id}/data/`
`/game/{game_id}/index.html` → FastAPI StaticFiles로 serve (`app.mount("/game", ...)`)

---

## 구현 대상

### 1. `agent/generation/writer.py` (신규)

```python
"""생성된 final_project를 디스크에 저장."""
import json
import logging
from pathlib import Path

from app.backend.core.game_paths import get_game_data_path

logger = logging.getLogger(__name__)


async def write_project_to_disk(game_id: str, final_project: dict) -> None:
    """final_project dict → storage/games/{game_id}/data/ JSON 파일 저장."""
    data_path = get_game_data_path(game_id)
    data_path.mkdir(parents=True, exist_ok=True)

    for fname, content in final_project.items():
        dest = data_path / fname
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        logger.info("written: %s", dest.name)
```

> compact JSON (`indent=None`) — RPG Maker MZ 호환, 파일 크기 감소

### 2. `app/backend/api/v1/endpoints/generation.py` 수정

**핵심 수정**: `game_id = str(project_id)` → 실제 `project.game_id` 조회

```python
async def _run_generation_in_background(
    generation_id: str,
    project_id: int,
    prompt: str,
    options: dict,
    db: AsyncSession,          # ← DB 세션 추가 필요
) -> None:
    # project.game_id 조회
    project = await project_repository.find_by_id(project_id, db)
    game_id = project.game_id  # "game_a1b2c3d4"

    final_state = await run_generation_workflow(
        prompt=prompt,
        game_id=game_id,        # 실제 game_id 사용
        generation_id=generation_id,
        phase_limit=options.get("phase_limit"),
    )

    # 디스크 저장
    if final_state.get("final_project"):
        from agent.generation.writer import write_project_to_disk
        await write_project_to_disk(game_id, final_state["final_project"])

        # S3 환경
        if settings.STORAGE_BACKEND == "s3":
            from app.backend.services.s3_game_storage import sync_game_to_s3
            sync_game_to_s3(game_id)
```

> `start_generation` 엔드포인트에서 `BackgroundTasks.add_task`에 `db` 세션 전달 방식 주의.
> FastAPI BackgroundTasks는 요청 컨텍스트가 닫힌 후 실행되므로 DB 세션을 직접 전달하면 안 됨.
> 대안: `project.game_id`를 엔드포인트에서 미리 조회 후 `game_id: str`으로 전달.

```python
@router.post("", status_code=202)
async def start_generation(
    req: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),   # ← 추가
) -> GenerationStartResponse:
    # game_id를 여기서 미리 조회
    project = await project_repository.find_by_id(req.project_id, db)
    if not project or project.user_id != current_user.id:
        raise HTTPException(404)

    generation_id = f"gen_{uuid4().hex[:8]}"
    background_tasks.add_task(
        _run_generation_in_background,
        generation_id=generation_id,
        game_id=project.game_id,   # ← str(project_id) 대신 실제 game_id
        prompt=req.prompt,
        options=req.options.model_dump(),
    )
    ...
```

### 3. `app/frontend/src/components/generation/GenerationResult.jsx` 수정

현재 버튼: `에디터에서 열기` → 기능은 맞으나 생성 완료 후에는 "게임 플레이"가 더 명확.
텍스트 수정 + 에디터 페이지 이동 유지 (에디터에 RPGMakerFrame이 있음).

```jsx
// GenerationResult.jsx - 기존 "에디터에서 열기" 버튼 텍스트 변경
<button onClick={onGoToEditor}>
  게임 플레이 →
</button>
```

---

## 플레이 플로우

```
GeneratePage
  → 폼 입력 → 생성 시작 (5~10분)
  → 완료 → "게임 플레이 →" 클릭
  → /editor/{projectId} → GameEditor
  → GamePreview (RPGMakerFrame) → /game/{game_id}/index.html
  → 브라우저에서 바로 플레이 ✓
```

---

## 완료 기준

- [ ] `storage/games/{project.game_id}/data/Actors.json` 파일 존재 확인
- [ ] `RPGMakerFrame`에서 생성된 게임 타이틀 화면 표시
- [ ] `game_id` 불일치 버그 수정 (숫자 문자열 → UUID 기반 game_id)
- [ ] S3 환경: `sync_game_to_s3` 호출 후 `/game/{game_id}/index.html` 로드 확인

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `app/backend/core/game_paths.py` | `get_game_data_path(game_id)` |
| `app/backend/services/s3_game_storage.py` | `sync_game_to_s3(game_id)` |
| `app/backend/core/config.py` | `STORAGE_BACKEND`, `STORAGE_PATH` |
| `app/backend/repositories/project_repository.py` | `get_by_id(project_id, db)` |
| `app/backend/main.py` | `app.mount("/game", StaticFiles(...))` |
