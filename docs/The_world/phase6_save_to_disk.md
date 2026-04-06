# Phase 6 — 생성 결과 디스크 저장 + 인게임 플레이 연결

> 상태: 미구현
> 우선순위: **긴급** — 없으면 생성된 게임을 플레이할 수 없음

---

## 현재 문제

`run_generation_workflow()` 완료 후 `final_project` dict가 메모리에만 있음.
기존 플레이 환경(`RPGMakerFrame` → `/game/{game_id}/index.html`)은 이미 동작하지만
`storage/games/{game_id}/data/`에 파일이 쓰이지 않아서 생성 결과가 반영되지 않음.

---

## 저장 구조 (기존 인프라 활용)

```
storage/games/{game_id}/
├── index.html                  ← RPG Maker MZ 엔진 (base_game에서 복사됨)
├── js/ fonts/ audio/ img/ ...  ← 게임 엔진 리소스
└── data/                       ← ← ← 여기에 저장
    ├── Actors.json
    ├── Classes.json
    ├── Skills.json
    ├── Items.json
    ├── Weapons.json
    ├── Armors.json
    ├── Enemies.json
    ├── Troops.json
    ├── System.json
    ├── MapInfos.json
    ├── Map001.json
    ├── Map002.json
    └── ...
```

`app/backend/core/game_paths.get_game_data_path(game_id)` 가 이 경로를 반환함.

---

## 구현 대상

### 1. `agent/generation/writer.py` (신규)

```python
from app.backend.core.game_paths import get_game_data_path
import json, logging
from pathlib import Path

logger = logging.getLogger(__name__)

async def write_project_to_disk(game_id: str, final_project: dict) -> None:
    """final_project dict → storage/games/{game_id}/data/ JSON 파일 저장."""
    data_path = get_game_data_path(game_id)
    data_path.mkdir(parents=True, exist_ok=True)

    for fname, content in final_project.items():
        dest = data_path / fname
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=None)
        logger.info("written: %s (%d bytes)", dest, dest.stat().st_size)
```

> **주의**: `indent=None`으로 compact JSON 출력 (RPG Maker MZ 호환, 파일 크기 감소)

### 2. `app/backend/api/v1/endpoints/generation.py` 수정

```python
# _run_generation_in_background 내부, 워크플로우 완료 직후
if final_state.get("final_project"):
    from agent.generation.writer import write_project_to_disk
    await write_project_to_disk(game_id, final_state["final_project"])
```

S3 환경에서는 `sync_game_to_s3(game_id)` 추가 호출 필요.

### 3. `GenerationResult.jsx` — "게임 플레이" 버튼 추가

```jsx
<button onClick={() => navigate(`/editor/${projectId}`)}>
  게임 플레이 →
</button>
```

기존 `GameEditor` → `RPGMakerFrame`이 `/game/{game_id}/index.html`을 로드하므로
그냥 에디터 페이지로 이동하면 새 게임이 바로 플레이됨.

---

## 프론트엔드 플로우

```
GeneratePage
  → Form 입력 → 생성 시작
  → Progress (5~10분)
  → Result: "게임 플레이 →" 클릭
  → GameEditor 페이지 → RPGMakerFrame 로드
  → 브라우저에서 바로 플레이 ✓
```

---

## 완료 기준

- [ ] `write_project_to_disk()` 실행 후 `storage/games/{game_id}/data/Actors.json` 존재
- [ ] `RPGMakerFrame`에서 생성된 게임이 정상 로드 (타이틀 화면 표시)
- [ ] `GenerationResult`에 "게임 플레이 →" 버튼 동작
- [ ] S3 환경에서도 `sync_game_to_s3` 호출 확인

---

## 주의사항

- `base_game`이 `storage/games/{game_id}/`에 이미 복사된 상태여야 함 (프로젝트 생성 시 자동 처리)
- `MapInfos.json`은 배열이 아닌 dict임 (기존 코드 확인 필요)
- S3 배포 환경: write 후 `sync_game_to_s3(game_id)` 호출 필수
