# Full Generation API 설계

> FastAPI 엔드포인트, WebSocket 프로토콜, DB 스키마, 프론트엔드 연동

---

## 개요

Full Generation은 **비동기 처리** 방식이다.
요청 → 즉시 `generation_id` 반환 → 백그라운드에서 생성 → 결과 폴링/WebSocket으로 수신.

```
클라이언트                          서버
  │                                  │
  ├─ POST /api/v1/generate ─────────►│
  │◄─ {generation_id: "gen_abc"} ────┤  (즉시 반환)
  │                                  │
  │  ←── WebSocket 연결 ────────────►│
  │                                  │
  │◄─ {type: "progress", phase: ..} ─┤  (실시간)
  │◄─ {type: "phase_complete"} ──────┤
  │◄─ {type: "completed"} ───────────┤
```

---

## REST API 엔드포인트

### POST /api/v1/generate — 생성 시작

```
POST /api/v1/generate
Authorization: Bearer {access_token}
Content-Type: application/json
```

**요청 바디:**

```json
{
  "project_id": 3,
  "prompt": "중세 판타지 게임 만들어줘, 기사 주인공으로",
  "options": {
    "playtime_minutes": 7,
    "seed": 42
  }
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `project_id` | int | ✅ | 게임 프로젝트 ID |
| `prompt` | str | ✅ | 사용자 자연어 입력 |
| `options.playtime_minutes` | int | ❌ | 목표 플레이타임 (기본: 7) |
| `options.seed` | int | ❌ | 랜덤 시드 (재현 가능한 생성) |

**응답 (202 Accepted):**

```json
{
  "generation_id": "gen_abc123",
  "status": "started",
  "estimated_seconds": 60,
  "ws_url": "ws://api/ws/generate/gen_abc123"
}
```

**에러 응답:**

```json
{
  "detail": "project_id 3을 찾을 수 없습니다.",
  "error_code": "PROJECT_NOT_FOUND"
}
```

---

### GET /api/v1/generate/{generation_id}/status — 진행 상황 폴링

WebSocket을 사용하지 않는 클라이언트를 위한 폴링 엔드포인트.

```
GET /api/v1/generate/gen_abc123/status
Authorization: Bearer {access_token}
```

**응답 — 진행 중:**

```json
{
  "generation_id": "gen_abc123",
  "status": "in_progress",
  "phase": "asset_generation",
  "progress": 40,
  "message": "캐릭터·스킬·아이템 생성 중...",
  "completed_phases": ["spec", "planning"],
  "started_at": "2026-04-02T10:00:00Z",
  "estimated_remaining_seconds": 36
}
```

**응답 — 완료:**

```json
{
  "generation_id": "gen_abc123",
  "status": "completed",
  "progress": 100,
  "result": {
    "title": "기사와 마왕",
    "assets_summary": {
      "actors": 3,
      "skills": 12,
      "items": 8,
      "weapons": 5,
      "armors": 5,
      "enemies": 8,
      "maps": 3,
      "events": 18
    },
    "play_url": "/games/3/play",
    "download_url": "/api/v1/games/3/download"
  },
  "completed_at": "2026-04-02T10:01:02Z"
}
```

**응답 — 실패:**

```json
{
  "generation_id": "gen_abc123",
  "status": "failed",
  "error_phase": "map_generation",
  "error_message": "맵 설계사 LLM 응답 파싱 실패 (3회 재시도 후)",
  "completed_phases": ["spec", "planning", "asset_generation"],
  "can_retry": true,
  "retry_from": "map_generation"
}
```

**status 값 목록:**

| status | 설명 |
|--------|------|
| `started` | 생성 작업 큐에 등록됨 |
| `in_progress` | 생성 중 (phase, progress 포함) |
| `completed` | 완전 성공 (result 포함) |
| `completed_with_warnings` | 부분 성공 — 검증 오류가 남았지만 파일은 저장됨 (responder_node.md 참조) |
| `failed` | 실패 (error_phase, error_message 포함) |
| `cancelled` | 사용자가 취소함 |

---

### POST /api/v1/generate/{generation_id}/retry — 재시도

```
POST /api/v1/generate/gen_abc123/retry
Authorization: Bearer {access_token}

{
  "from_phase": "map_generation"
}
```

**응답:**

```json
{
  "generation_id": "gen_abc123",
  "status": "in_progress",
  "message": "map_generation 단계부터 재시작합니다."
}
```

---

### POST /api/v1/generate/{generation_id}/regenerate — 부분 재생성

```
POST /api/v1/generate/gen_abc123/regenerate
Authorization: Bearer {access_token}

{
  "scope": "events",
  "target_map_id": 2
}
```

**scope 값:**

| scope | 재실행되는 Phase |
|-------|--------------|
| `"spec"` | A부터 전체 재생성 |
| `"assets"` | C+H+I 재실행 |
| `"maps"` | D+E+F+G+H+I 재실행 |
| `"events"` | F+G+H+I 재실행 |

`target_map_id`가 있으면 해당 맵의 이벤트만 재생성.

---

### DELETE /api/v1/generate/{generation_id} — 취소

```
DELETE /api/v1/generate/gen_abc123
Authorization: Bearer {access_token}
```

**응답 (204 No Content)** — 성공 시 본문 없음.

---

## WebSocket 프로토콜

### 연결

```
ws://api/ws/generate/{generation_id}
Authorization: 쿼리 파라미터로 전달
ws://api/ws/generate/gen_abc123?token={access_token}
```

### 서버 → 클라이언트 메시지 타입

#### `progress` — 단계별 진행 상황

```json
{
  "type": "progress",
  "generation_id": "gen_abc123",
  "phase": "asset_generation",
  "phase_label": "캐릭터·스킬 생성",
  "progress": 40,
  "message": "스킬 12개 생성 중..."
}
```

#### `phase_complete` — 한 단계 완료

```json
{
  "type": "phase_complete",
  "phase": "asset_generation",
  "phase_label": "캐릭터·스킬 생성",
  "summary": "캐릭터 3명, 스킬 12개, 아이템 18개 생성 완료",
  "duration_seconds": 8.2
}
```

#### `completed` — 전체 완료 (완전 성공)

```json
{
  "type": "completed",
  "generation_id": "gen_abc123",
  "title": "기사와 마왕",
  "message": "게임이 완성됐습니다!",
  "assets_summary": {
    "actors": 3, "skills": 12, "enemies": 8, "maps": 3, "events": 18
  },
  "total_duration_seconds": 28.5
}
```

#### `completed_with_warnings` — 부분 성공 (파일 저장됨, 검증 오류 존재)

> 재시도 한계 도달 후 일부 검증 오류가 남아있지만 파일은 저장된 경우.
> 프론트엔드는 다운로드 링크 활성화 + 경고 메시지 표시.

```json
{
  "type": "completed_with_warnings",
  "generation_id": "gen_abc123",
  "progress": 100,
  "message": "게임이 생성되었지만 일부 문제가 있습니다. RPG Maker MZ에서 직접 확인해주세요."
}
```

#### `error` — 오류 발생

```json
{
  "type": "error",
  "phase": "map_generation",
  "message": "맵 생성에 실패했습니다. 다시 시도하시겠어요?",
  "can_retry": true,
  "completed_phases": ["spec", "planning", "asset_generation"]
}
```

#### `warning` — 밸런스 경고 (생성은 완료됨)

```json
{
  "type": "warning",
  "category": "balance",
  "warnings": [
    "슬라임(weak) ATK=50이 너무 높습니다. 플레이어가 2번 맞으면 사망할 수 있습니다.",
    "파이어볼 MP소비=80이 주인공 MaxMP=50 초과입니다."
  ]
}
```

### Phase 이름 및 진행률 매핑

| Phase | phase 값 | 진행률 범위 |
|-------|---------|-----------|
| 기획자 | `spec` | 0~10% |
| 설계사 | `planning` | 10~15% |
| 에셋 생성 | `asset_generation` | 15~50% |
| 맵 설계 | `map_design` | 50~60% |
| 타일 생성 | `tile_generation` | 60~70% |
| 이벤트 기획 | `event_planning` | 70~85% |
| 이벤트 컴파일 | `event_compilation` | 85~90% |
| 통합 | `integration` | 90~95% |
| 검증 | `validation` | 95~100% |

---

## FastAPI 라우터 구현

```python
# app/backend/api/v1/generation.py
from fastapi import APIRouter, BackgroundTasks, Depends, WebSocket
from agent.generation.workflow import run_generation_workflow

router = APIRouter(prefix="/api/v1/generate", tags=["generation"])


@router.post("", status_code=202)
async def start_generation(
    req: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerationStartResponse:
    # generation 레코드 생성
    generation_id = f"gen_{uuid4().hex[:8]}"
    await db.execute(
        insert(Generation).values(
            id=generation_id,
            project_id=req.project_id,
            user_id=current_user.id,
            status="started",
            prompt=req.prompt,
        )
    )
    await db.commit()

    # 백그라운드 실행
    background_tasks.add_task(
        run_generation_in_background,
        generation_id=generation_id,
        prompt=req.prompt,
        options=req.options,
    )

    return GenerationStartResponse(
        generation_id=generation_id,
        status="started",
        estimated_seconds=60,
        ws_url=f"ws://api/ws/generate/{generation_id}",
    )


@router.get("/{generation_id}/status")
async def get_generation_status(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerationStatusResponse:
    gen = await db.get(Generation, generation_id)
    if not gen or gen.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.")
    return build_status_response(gen)


@router.websocket("/ws/generate/{generation_id}")
async def generation_websocket(
    websocket: WebSocket,
    generation_id: str,
    token: str,
):
    await websocket.accept()
    user = await verify_token(token)
    if not user:
        await websocket.close(code=4001, reason="인증 실패")
        return

    async for event in subscribe_generation_events(generation_id):
        await websocket.send_json(event)
        if event["type"] in ("completed", "error"):
            break

    await websocket.close()
```

---

## 이벤트 브로드캐스팅 (내부)

워크플로우에서 진행 상황을 브로드캐스트하는 방법.

```python
# agent/generation/progress.py
from asyncio import Queue
from typing import AsyncIterator

_generation_queues: dict[str, Queue] = {}


async def publish_progress(generation_id: str, event: dict) -> None:
    """워크플로우 노드에서 호출해서 진행 상황 발행."""
    if generation_id in _generation_queues:
        await _generation_queues[generation_id].put(event)


async def subscribe_generation_events(generation_id: str) -> AsyncIterator[dict]:
    """WebSocket 핸들러에서 구독."""
    q: Queue = Queue()
    _generation_queues[generation_id] = q
    try:
        while True:
            event = await q.get()
            yield event
            if event.get("type") in ("completed", "error"):
                break
    finally:
        _generation_queues.pop(generation_id, None)


# 각 노드에서 사용 예시
async def game_designer(state: GenerationState) -> GenerationState:
    await publish_progress(state["generation_id"], {
        "type": "progress",
        "phase": "spec",
        "progress": 5,
        "message": "게임 기획 중...",
    })
    # ... LLM 호출 ...
    await publish_progress(state["generation_id"], {
        "type": "phase_complete",
        "phase": "spec",
        "summary": "기사와 마왕 - 3맵, 3캐릭터 기획 완료",
    })
    return state
```

---

## DB 스키마

### generations 테이블

```sql
CREATE TABLE generations (
    id              VARCHAR(36) PRIMARY KEY,           -- "gen_abc123"
    project_id      INT NOT NULL REFERENCES projects(id),
    user_id         INT NOT NULL REFERENCES users(id),

    -- 상태
    status          VARCHAR(20) DEFAULT 'started',     -- started/in_progress/completed/failed/cancelled
    current_phase   VARCHAR(30),                       -- 현재 실행 중인 Phase
    progress        INT DEFAULT 0,                     -- 0~100

    -- 생성 입력
    prompt          TEXT NOT NULL,
    options         JSONB DEFAULT '{}',

    -- 중간 결과 (체크포인트용)
    game_spec       JSONB,                             -- A 기획자 출력
    id_table        JSONB,                             -- B 설계사 출력
    switch_table    JSONB,
    completed_phases TEXT[] DEFAULT '{}',

    -- 오류 정보
    error_phase     VARCHAR(30),
    error_message   TEXT,
    retry_count     INT DEFAULT 0,

    -- 최종 결과 요약
    result_summary  JSONB,                             -- assets_summary 등

    -- 메타
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_generations_project_id ON generations(project_id);
CREATE INDEX idx_generations_user_id    ON generations(user_id);
CREATE INDEX idx_generations_status     ON generations(status);
```

### S3 저장 구조

```
s3://re-verse-bucket/
└── games/{game_id}/
    └── generations/{generation_id}/
        ├── checkpoint.json          # completed_phases + 중간 결과
        ├── spec.json               # GameSpec (A 출력)
        ├── id_table.json           # IdTable (B 출력)
        ├── switch_table.json       # SwitchTable (B 출력)
        ├── assets/
        │   ├── Actors.json
        │   ├── Classes.json
        │   ├── Skills.json
        │   ├── Items.json
        │   ├── Weapons.json
        │   ├── Armors.json
        │   ├── Enemies.json
        │   ├── Troops.json
        │   └── System.json
        ├── maps/
        │   ├── Map001.json
        │   ├── Map002.json
        │   └── Map003.json
        └── validation_report.json  # 검증 결과
```

체크포인트 파일 구조:

```json
{
  "generation_id": "gen_abc123",
  "completed_phases": ["spec", "planning", "asset_generation"],
  "timestamp": "2026-04-02T10:00:30Z",
  "assets_completed": {
    "Actors.json": true,
    "Skills.json": true,
    "Enemies.json": false
  }
}
```

---

## Pydantic 스키마

```python
# app/backend/schemas/generation.py
from pydantic import BaseModel

class GenerationOptions(BaseModel):
    playtime_minutes: int = 7
    seed: int | None = None

class GenerationRequest(BaseModel):
    project_id: int
    prompt: str
    options: GenerationOptions = GenerationOptions()

class GenerationStartResponse(BaseModel):
    generation_id: str
    status: str
    estimated_seconds: int
    ws_url: str

class AssetsSummary(BaseModel):
    actors:  int = 0
    skills:  int = 0
    items:   int = 0
    weapons: int = 0
    armors:  int = 0
    enemies: int = 0
    maps:    int = 0
    events:  int = 0

class GenerationResult(BaseModel):
    title: str
    assets_summary: AssetsSummary
    play_url: str
    download_url: str

class GenerationStatusResponse(BaseModel):
    generation_id: str
    status: str
    phase: str | None = None
    progress: int = 0
    message: str | None = None
    completed_phases: list[str] = []
    result: GenerationResult | None = None
    error_phase: str | None = None
    error_message: str | None = None
    can_retry: bool = False
    started_at: str
    completed_at: str | None = None
```

---

## 프론트엔드 연동 가이드

### React 훅 (useGeneration)

```typescript
// src/hooks/useGeneration.ts
import { useState, useEffect, useRef } from 'react';

interface GenerationState {
  generationId: string | null;
  status: 'idle' | 'started' | 'in_progress' | 'completed' | 'failed';
  progress: number;
  phase: string | null;
  message: string | null;
  result: GenerationResult | null;
  error: string | null;
}

export function useGeneration() {
  const [state, setState] = useState<GenerationState>({
    generationId: null,
    status: 'idle',
    progress: 0,
    phase: null,
    message: null,
    result: null,
    error: null,
  });
  const wsRef = useRef<WebSocket | null>(null);

  const startGeneration = async (prompt: string, projectId: number) => {
    // 1. 생성 시작 요청
    const response = await fetch('/api/v1/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ project_id: projectId, prompt }),
    });
    const { generation_id, ws_url } = await response.json();

    setState(s => ({ ...s, generationId: generation_id, status: 'started' }));

    // 2. WebSocket 연결
    const ws = new WebSocket(`${ws_url}?token=${getToken()}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      switch (event.type) {
        case 'progress':
          setState(s => ({
            ...s,
            status: 'in_progress',
            progress: event.progress,
            phase: event.phase,
            message: event.message,
          }));
          break;
        case 'completed':
          setState(s => ({
            ...s,
            status: 'completed',
            progress: 100,
            result: event,
          }));
          ws.close();
          break;
        case 'error':
          setState(s => ({
            ...s,
            status: 'failed',
            error: event.message,
          }));
          ws.close();
          break;
      }
    };
  };

  const cancelGeneration = async () => {
    if (!state.generationId) return;
    wsRef.current?.close();
    await fetch(`/api/v1/generate/${state.generationId}`, { method: 'DELETE' });
    setState(s => ({ ...s, status: 'idle' }));
  };

  return { state, startGeneration, cancelGeneration };
}
```

### 생성 UI 컴포넌트

```
생성 중 화면:
┌─────────────────────────────────────────────────┐
│  게임 생성 중...                                   │
│                                                   │
│  ✅ 게임 기획 완료                     (3.2s)      │
│  ✅ ID 테이블 구성 완료                 (0.5s)     │
│  ✅ 캐릭터·스킬·아이템 생성 완료        (8.1s)     │
│  ⏳ 맵 생성 중... (2/3)                            │
│     ████████████░░░░░░░░  60%                     │
│  ⬜ 이벤트 생성 대기                              │
│  ⬜ 최종 검증 대기                                │
│                                                   │
│  예상 완료: 약 20초 후           [취소]            │
└─────────────────────────────────────────────────┘

완료 화면:
┌─────────────────────────────────────────────────┐
│  🎮 "기사와 마왕" 생성 완료!                       │
│                                                   │
│  캐릭터 3명 · 스킬 12개 · 아이템 18개             │
│  맵 3개 · 이벤트 18개                             │
│  생성 시간: 28.5초                                │
│                                                   │
│  [지금 플레이]  [편집하기]  [다운로드]             │
└─────────────────────────────────────────────────┘
```

---

## 보안 고려사항

### Rate Limiting

```python
# 사용자당 동시 생성 제한
MAX_CONCURRENT_GENERATIONS_PER_USER = 1

# 일일 생성 횟수 제한
MAX_GENERATIONS_PER_DAY_PER_USER = 10

@router.post("")
async def start_generation(req, current_user, db):
    # 현재 실행 중인 생성 확인
    active = await db.scalar(
        select(count(Generation.id))
        .where(Generation.user_id == current_user.id)
        .where(Generation.status.in_(["started", "in_progress"]))
    )
    if active >= MAX_CONCURRENT_GENERATIONS_PER_USER:
        raise HTTPException(status_code=429, detail="이미 생성 중인 작업이 있습니다.")
```

### 리소스 보호

- 생성 중 최대 LLM 호출: 12회 (Phase 4 기준)
- 타임아웃: 생성 작업 최대 5분 (300초) 후 강제 종료
- 파일 크기 제한: 최종 프로젝트 ZIP 최대 50MB

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- 리스크 분석: `docs/The_world/risks_and_mitigations.md`
- DSL 명세: `docs/The_world/dsl_specification.md`
- 맵 생성 알고리즘: `docs/The_world/map_generation.md`
