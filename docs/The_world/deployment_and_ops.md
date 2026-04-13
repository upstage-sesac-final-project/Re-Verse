# 배포 및 운영 가이드

> Full Generation 시스템의 프로덕션 운영: 태스크 큐, 모니터링, 스케일링, 비용 관리

---

## 현재 인프라와의 관계

```
현재 인프라 (Incremental Edit):
  EC2 + Docker → FastAPI → Solar Pro 2 API → Supabase

Full Generation 추가 후:
  EC2 + Docker → FastAPI → [BackgroundTasks/Celery] → Solar Pro 2 API × 12회
                                                     → Supabase (generations 테이블)
                                                     → S3 (체크포인트)
                                  ↓
                             WebSocket (실시간 진행 상황)
```

---

## Phase 2 배포 전략 (BackgroundTasks 단계)

Phase 2~3는 FastAPI `BackgroundTasks`로 충분하다.
규모가 작고 동시 생성 요청이 적을 때 적합.

### 제약 조건

```
BackgroundTasks 한계:
  - 같은 uvicorn 프로세스 안에서 실행
  - 서버 재시작 시 진행 중인 태스크 손실
  - 동시 생성이 많아지면 서버 응답 지연

→ Phase 2~3에서는 허용 (동시 생성 ≤ 3)
→ Phase 4 이후 Celery로 전환 권장
```

### docker-compose 설정 (Phase 2)

```yaml
# docker-compose.yml (기존 파일에 추가)
services:
  backend:
    # 기존 설정 그대로
    environment:
      - GENERATION_MAX_CONCURRENT=2
      - GENERATION_TIMEOUT_SECONDS=180
      - CHECKPOINT_BACKEND=memory    # 재시작 시 체크포인트 손실 허용
```

---

## Phase 4+ 배포 전략 (Celery 전환)

동시 생성 요청이 늘어나면 Celery + Redis로 전환한다.

### 아키텍처

```
클라이언트
    │
    ▼
FastAPI (EC2-A)        ← HTTP + WebSocket
    │  POST /generate
    ▼
Redis (태스크 큐)
    │
    ├─ Worker-1 (EC2-B)  ← 생성 전담 프로세스 (CPU intensive)
    ├─ Worker-2 (EC2-B)
    └─ Worker-3 (EC2-B)

결과 → Supabase (상태 업데이트)
     → S3 (체크포인트, 최종 파일)
```

### Celery 태스크 정의

```python
# agent/generation/tasks.py
from celery import Celery
import asyncio

celery_app = Celery(
    "generation",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

celery_app.conf.update(
    task_serializer="json",
    result_expires=3600,    # 결과 1시간 보관
    task_soft_time_limit=240,   # 4분 후 경고
    task_time_limit=300,        # 5분 후 강제 종료
)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def run_generation_task(self, generation_id: str, prompt: str, game_id: str):
    """백그라운드에서 실행되는 Full Generation 태스크."""
    try:
        asyncio.run(_run_generation(generation_id, prompt, game_id))
    except Exception as exc:
        raise self.retry(exc=exc)
```

### docker-compose (Phase 4+)

```yaml
# docker-compose.yml
services:
  backend:
    build: .
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery-worker:
    build: .
    command: celery -A agent.generation.tasks worker --loglevel=info --concurrency=2
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - UPSTAGE_API_KEY=${UPSTAGE_API_KEY}
    deploy:
      replicas: 2     # 워커 2개 (동시 생성 최대 4개)
    depends_on:
      - redis
      - backend

  celery-flower:
    image: mher/flower
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    command: celery flower --broker=redis://redis:6379/0
```

---

## 체크포인트 백엔드 전환

```python
# agent/generation/checkpoint.py

class CheckpointBackend(Protocol):
    async def save(self, generation_id: str, state: dict) -> None: ...
    async def load(self, generation_id: str) -> dict | None: ...


class MemoryCheckpoint:
    """Phase 2용: 메모리 체크포인트 (재시작 시 손실)"""
    _store: dict[str, dict] = {}

    async def save(self, generation_id: str, state: dict) -> None:
        self._store[generation_id] = state

    async def load(self, generation_id: str) -> dict | None:
        return self._store.get(generation_id)


class S3Checkpoint:
    """Phase 4+용: S3 체크포인트 (영구 보존)"""
    def __init__(self, bucket: str):
        self.bucket = bucket

    async def save(self, generation_id: str, state: dict) -> None:
        import aioboto3, json
        async with aioboto3.Session().client("s3") as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=f"checkpoints/{generation_id}.json",
                Body=json.dumps(state, ensure_ascii=False),
            )

    async def load(self, generation_id: str) -> dict | None:
        import aioboto3, json
        try:
            async with aioboto3.Session().client("s3") as s3:
                resp = await s3.get_object(
                    Bucket=self.bucket,
                    Key=f"checkpoints/{generation_id}.json",
                )
                return json.loads(await resp["Body"].read())
        except Exception:
            return None


def get_checkpoint_backend() -> CheckpointBackend:
    backend = os.getenv("CHECKPOINT_BACKEND", "memory")
    if backend == "s3":
        return S3Checkpoint(bucket=os.getenv("AWS_S3_GENERATION_BUCKET"))
    return MemoryCheckpoint()
```

---

## LangSmith 모니터링 연동

기존 프로젝트에 이미 LangSmith가 설정되어 있다면 Full Generation도 자동 추적된다.
그러나 생성 작업에 특화된 트레이싱을 추가한다.

### 추가 설정

```python
# agent/generation/workflow.py
from langsmith import traceable

@traceable(
    name="full_generation",
    tags=["generation", "v1"],
    metadata={"component": "full_generation"},
)
async def run_generation_workflow(
    user_input: str,
    game_id: str,
    generation_id: str,
) -> GenerationState:
    ...
```

### LangSmith에서 추적할 메트릭

```python
# 각 노드에서 run_metadata 추가
from langsmith import get_current_run_tree

async def asset_generator(state: GenerationState) -> GenerationState:
    run = get_current_run_tree()
    if run:
        run.add_metadata({
            "generation_id": state["generation_id"],
            "asset_count":   len(state.get("generated_assets", {})),
            "phase":         "asset_generation",
        })
    ...
```

### LangSmith 대시보드 확인 항목

```
Full Generation 전용 필터:
  tags: ["generation"]
  → 게임 1개 생성당 평균 토큰, 평균 소요 시간 확인

주요 메트릭:
  - game_designer 실패율 (파싱 오류)
  - event_planner 재시도율 (DSL 파싱)
  - 전체 성공률
  - 단계별 p95 응답 시간
```

---

## 비용 모니터링

### Solar Pro 2 API 비용 추적

```python
# agent/generation/cost_tracker.py
from dataclasses import dataclass, field

@dataclass
class GenerationCost:
    generation_id: str
    input_tokens:  int = 0
    output_tokens: int = 0
    llm_calls:     int = 0

    # Solar Pro 2 가격 (추정, 2026년 기준)
    PRICE_PER_1K_INPUT  = 0.003   # USD
    PRICE_PER_1K_OUTPUT = 0.015   # USD

    @property
    def total_usd(self) -> float:
        return (
            self.input_tokens  / 1000 * self.PRICE_PER_1K_INPUT +
            self.output_tokens / 1000 * self.PRICE_PER_1K_OUTPUT
        )


async def track_llm_cost(state: GenerationState, response) -> None:
    """LLM 응답에서 토큰 수 추출 + Supabase 기록."""
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return

    await db.execute(
        update(Generation)
        .where(Generation.id == state["generation_id"])
        .values(
            input_tokens  = Generation.input_tokens  + usage.input_tokens,
            output_tokens = Generation.output_tokens + usage.output_tokens,
            llm_calls     = Generation.llm_calls + 1,
        )
    )
```

### 비용 임계값 알림

```python
# 게임 1개 생성 비용이 예상을 초과하면 Slack 알림
MAX_COST_PER_GAME_USD = 0.50   # 50센트 초과 시 경고

async def check_cost_alert(generation_id: str) -> None:
    cost = await get_generation_cost(generation_id)
    if cost.total_usd > MAX_COST_PER_GAME_USD:
        await send_slack_alert(
            f"⚠️ 생성 비용 초과: generation_id={generation_id}, "
            f"비용=${cost.total_usd:.3f} (LLM {cost.llm_calls}회)"
        )
```

---

## 리소스 요구사항

### EC2 인스턴스 권장

| 단계 | 인스턴스 타입 | 메모리 | 이유 |
|------|------------|--------|------|
| Phase 2~3 | t3.medium (현재) | 4 GB | 동시 생성 ≤ 2 |
| Phase 4 (BackgroundTasks) | t3.large | 8 GB | 동시 생성 ≤ 4 |
| Phase 4+ (Celery) | 분리: API t3.medium + Worker c5.large | 별도 | CPU 집약적 작업 분리 |

### 메모리 사용 추정

```
단일 생성 작업의 메모리 사용:
  game_spec JSON:      ~10 KB
  id_table:            ~5 KB
  generated_assets:    ~200~500 KB (JSON 파일들)
  map_tiles:           ~100 KB (타일 배열)
  compiled_events:     ~50 KB
  LangGraph 상태:      ~100 KB

합계:                  ~500 KB ~ 1 MB per generation
동시 4개:             ~4 MB (안전)
```

---

## 타임아웃 & 헬스체크

### 생성 작업 타임아웃

```python
# app/backend/core/config.py
class GenerationSettings(BaseModel):
    max_concurrent: int = 3
    timeout_seconds: int = 300        # 5분 타임아웃
    soft_timeout_seconds: int = 240   # 4분 후 경고
    retry_max: int = 2

# 타임아웃 강제 종료
import asyncio

async def run_with_timeout(coro, timeout: int, generation_id: str):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        await publish_progress(generation_id, {
            "type": "error",
            "phase": "timeout",
            "message": f"생성 시간 {timeout}초 초과. 일부 에셋은 저장됐을 수 있습니다.",
            "can_retry": True,
        })
        raise
```

### 헬스체크 엔드포인트

```python
# app/backend/api/v1/health.py (기존에 추가)

@router.get("/health/generation")
async def generation_health(db: AsyncSession = Depends(get_db)):
    """Full Generation 시스템 상태 확인."""
    # 최근 10분 생성 현황
    recent = await db.execute(
        select(Generation.status, func.count())
        .where(Generation.created_at > datetime.utcnow() - timedelta(minutes=10))
        .group_by(Generation.status)
    )
    stats = dict(recent.all())

    # 오래된 in_progress 탐지 (5분 이상 멈춘 작업)
    stuck = await db.scalar(
        select(func.count(Generation.id))
        .where(Generation.status == "in_progress")
        .where(Generation.created_at < datetime.utcnow() - timedelta(minutes=6))
    )

    return {
        "status": "healthy" if stuck == 0 else "degraded",
        "recent_10min": stats,
        "stuck_generations": stuck,
    }
```

---

## 장애 대응 플레이북

### 시나리오 1: LLM API 타임아웃 급증

```
증상: generation_validator 통과 전에 timeout 오류 다발
원인: Upstage API 불안정

대응:
  1. LangSmith에서 특정 노드의 응답 시간 급증 확인
  2. event_planner timeout → 해당 맵 fallback_events로 대체 (자동)
  3. 전체 실패 시 사용자에게 "현재 AI 서비스가 불안정합니다" 안내
  4. 30분 후 재시도 권장
```

### 시나리오 2: S3 체크포인트 저장 실패

```
증상: 재시작 후 completed_phases가 비어있음 (처음부터 재실행)
원인: S3 접근 불가 또는 권한 오류

대응:
  1. CHECKPOINT_BACKEND=memory로 임시 전환 (재시작 시 손실 허용)
  2. S3 버킷 권한 및 네트워크 확인
  3. 영향받은 생성 작업은 수동 재시도 안내
```

### 시나리오 3: DB generations 테이블 쿼리 지연

```
증상: /api/v1/generate/{id}/status 응답 느림
원인: generations 테이블 인덱스 누락 또는 급격한 데이터 증가

대응:
  1. EXPLAIN ANALYZE로 쿼리 플랜 확인
  2. status + created_at 복합 인덱스 추가:
     CREATE INDEX idx_gen_status_created ON generations(status, created_at);
  3. 30일 이상 완료된 레코드 아카이빙
```

### 시나리오 4: 동시 생성 급증 (트래픽 스파이크)

```
증상: generation 완료 시간이 5분 초과
원인: 동시 생성 요청 초과

대응:
  Phase 2~3: GENERATION_MAX_CONCURRENT 값으로 큐잉 (429 반환)
  Phase 4+:  Celery 워커 수평 확장 (docker scale celery-worker=4)
```

---

## 배포 전 체크리스트

```
□ 환경변수 설정 확인
  □ UPSTAGE_API_KEY
  □ CHECKPOINT_BACKEND (memory|s3)
  □ GENERATION_MAX_CONCURRENT
  □ GENERATION_TIMEOUT_SECONDS

□ DB 마이그레이션 실행
  □ migrations/0007_add_generations_table.sql

□ API 엔드포인트 연기 테스트
  □ POST /api/v1/generate → 202 반환
  □ GET /api/v1/generate/{id}/status → 진행 상황 반환
  □ WebSocket 연결 및 메시지 수신

□ 동시 생성 테스트
  □ 3개 동시 요청 → 모두 완료
  □ 한계 초과 요청 → 429 반환

□ 타임아웃 테스트
  □ 의도적 LLM 지연으로 타임아웃 발생 확인
  □ 타임아웃 후 error 메시지 WebSocket 수신

□ 헬스체크 엔드포인트 동작 확인
  □ GET /health/generation → {"status": "healthy", ...}
```

---

## 참고 링크

- API 설계: `docs/The_world/generation_api.md`
- 리스크 분석: `docs/The_world/risks_and_mitigations.md`
- 워크플로우 구현: `docs/The_world/workflow_implementation.md`
- 기존 배포 설정: `docker-compose.yml`, `.github/workflows/deploy.yml`
