# 기존 파이프라인과의 통합 전략

> Full Generation이 기존 Incremental Edit 파이프라인과 어떻게 공존하는가
> 새로 만들어야 할 것 / 재사용할 수 있는 것 / 충돌 가능 지점

---

## 두 파이프라인 비교

```
현재 (Incremental Edit)            신규 (Full Generation)
──────────────────────────         ──────────────────────────────────
입력: "슬라임 HP 200으로 올려줘"    입력: "중세 판타지 게임 만들어줘"
처리: Router→Definition→           처리: Designer→Planner→Assets→
      Planner→Executor→            Maps→Events→Integrator→Validator
      Validator→Synthesizer
출력: 변경된 파일 1~2개            출력: RPG Maker 프로젝트 전체 (10+파일)
소요: ~10초                        소요: ~40초
LLM: 3~5회                         LLM: 11~12회
```

---

## 코드 재사용 지도

### 재사용 가능한 기존 코드

```
agent/schemas/          ← 전부 재사용
  actors.py, skills.py, enemies.py, maps.py, ...
  → Full Generation의 에셋 검증에 그대로 사용

agent/core/
  llm_client.py         ← invoke_llm() 함수 그대로 사용 (실제 파일명)
  settings.py

agent/rag/              ← 부분 재사용 (에셋 컨텍스트 참조용)

app/backend/
  core/security.py      ← 인증 미들웨어 재사용
  db/                   ← Supabase 세션 재사용
```

### 새로 만들어야 하는 코드

```
agent/generation/       ← 전부 신규
  workflow.py
  nodes/
  mapgen/
  compilers/
  registry/
  prompts/

app/backend/api/v1/
  generation.py         ← 신규 (기존 game.py와 별개 라우터)

app/backend/models/
  generation.py         ← 신규 DB 모델
```

---

## 분류기 (Router) 수정

기존 Router는 `조회 / 수정 / 생성` 3종만 분류했다.
Full Generation을 위한 `전체_게임_생성` 의도를 추가해야 한다.

### 기존 의도 분류

```python
# agent/graph/nodes/router.py (현재)
class Intent(str, Enum):
    QUERY  = "게임_요소_조회"
    MODIFY = "게임_요소_수정"
    CREATE = "게임_요소_생성"
```

### 수정 후

```python
# agent/graph/nodes/router.py (수정)
class Intent(str, Enum):
    QUERY        = "게임_요소_조회"
    MODIFY       = "게임_요소_수정"
    CREATE       = "게임_요소_생성"
    FULL_GENERATE = "전체_게임_생성"   # ← 신규 추가
```

### 분류 기준 추가 (LLM 프롬프트)

```python
# agent/prompts/router_prompt.py에 추가
"""
## 전체_게임_생성 판단 기준

다음과 같은 요청은 "전체_게임_생성"으로 분류:
- "게임 만들어줘"
- "RPG 만들어줘"
- "새 게임 생성해줘"
- "[장르/테마] 게임 만들어줘"
- "처음부터 게임을 다시 만들어줘"

단순 요소 추가(적 1마리, 스킬 1개)는 "게임_요소_생성"으로 분류.
게임 전체를 새로 생성하는 요청만 "전체_게임_생성".
"""
```

### FastAPI 진입점 분기

```python
# app/backend/api/v1/game.py (기존 파일 수정)
@router.post("/process")
async def process_request(req: ProcessRequest, ...):
    intent = await classify_intent(req.user_input)

    if intent == Intent.FULL_GENERATE:
        # Full Generation 파이프라인으로 리디렉트
        return RedirectResponse(
            url=f"/api/v1/generate",
            status_code=307,
        )
    else:
        # 기존 Incremental Edit 파이프라인 실행
        result = await run_incremental_workflow(req)
        return result
```

---

## DB 스키마 변경

### 기존 테이블 (변경 없음)

```sql
-- 현재 있는 테이블
games        (id, user_id, title, ...)
game_files   (id, game_id, file_name, content, ...)
```

### 신규 테이블 추가

```sql
-- Full Generation 전용
CREATE TABLE generations (
    id              VARCHAR(36) PRIMARY KEY,
    project_id      INT NOT NULL REFERENCES games(id),
    user_id         INT NOT NULL,
    status          VARCHAR(20) DEFAULT 'started',
    current_phase   VARCHAR(30),
    progress        INT DEFAULT 0,
    prompt          TEXT NOT NULL,
    options         JSONB DEFAULT '{}',
    game_spec       JSONB,
    id_table        JSONB,
    switch_table    JSONB,
    completed_phases TEXT[] DEFAULT '{}',
    error_phase     VARCHAR(30),
    error_message   TEXT,
    retry_count     INT DEFAULT 0,
    result_summary  JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_gen_project ON generations(project_id);
CREATE INDEX idx_gen_status  ON generations(status);
```

### 마이그레이션 파일

```sql
-- migrations/0007_add_generations_table.sql
BEGIN;

CREATE TABLE IF NOT EXISTS generations (
    -- (위 DDL 동일)
);

-- 기존 games 테이블에 last_generation_id 추가
ALTER TABLE games
    ADD COLUMN IF NOT EXISTS last_generation_id VARCHAR(36)
        REFERENCES generations(id) ON DELETE SET NULL;

COMMIT;
```

---

## API 라우터 구조 변경

### 현재 라우터 구조

```
app/backend/api/v1/
├── auth.py         GET/POST /auth/*
├── game.py         POST /game/process
└── llm.py          POST /llm/*
```

### 변경 후

```
app/backend/api/v1/
├── auth.py         변경 없음
├── game.py         기존 + Intent.FULL_GENERATE 분기 추가
├── generation.py   신규: POST /generate, GET /generate/{id}/status
└── llm.py          변경 없음
```

```python
# app/backend/main.py
from app.backend.api.v1 import auth, game, generation

app.include_router(auth.router)
app.include_router(game.router)
app.include_router(generation.router)   # 신규 추가
```

---

## 파일 저장 전략 통합

### 현재 Incremental Edit의 파일 저장

```python
# 현재: game_files 테이블에 JSON 문자열로 저장
await db.execute(
    update(GameFile)
    .where(GameFile.game_id == game_id, GameFile.file_name == "Enemies.json")
    .values(content=json.dumps(updated_enemies))
)
```

### Full Generation의 파일 저장

Full Generation 완료 후 동일한 `game_files` 테이블에 저장한다.
이렇게 하면 Incremental Edit이 Full Generation 결과를 수정할 수 있다.

```python
# agent/generation/nodes/integrator.py
async def integrator(state: GenerationState) -> GenerationState:
    final_project = state["final_project"]

    for file_name, content in final_project.items():
        # game_files 테이블에 upsert
        await db.execute(
            insert(GameFile)
            .values(
                game_id=state["game_id"],
                file_name=file_name,
                content=json.dumps(content, ensure_ascii=False),
            )
            .on_conflict_do_update(
                index_elements=["game_id", "file_name"],
                set_={"content": json.dumps(content, ensure_ascii=False)},
            )
        )
```

→ 이 구조 덕분에 Full Generation으로 게임을 만들고,
  이후 Incremental Edit으로 "슬라임 HP 올려줘" 같은 세부 수정이 자연스럽게 연결된다.

---

## 공유 코드 리팩터링 필요 항목

### invoke_llm() 공통 유틸

현재 여러 곳에 분산된 LLM 호출을 단일 함수로 통일.

```python
# agent/core/llm_utils.py (신규)
async def invoke_llm(
    messages: list[BaseMessage],
    timeout: float = 30.0,
    model: str = "solar-pro-2",
) -> str:
    """
    LLM 호출 공통 함수.
    Incremental Edit + Full Generation 모두 사용.
    """
    # 실제 구현: agent/core/llm_client.py의 invoke_llm() 사용
    # structured_output 지원 버전 (llm_structured_output.md 참조)
    return await invoke_llm(messages, structured_output=None)
```

### 스키마 검증 공통 유틸

```python
# agent/schemas/validator.py (신규)
from agent.schemas.actors  import ActorsFile
# ... 기타 스키마 import

SCHEMA_MAP: dict[str, type] = {
    "Actors.json":  ActorsFile,
    "Skills.json":  SkillsFile,
    # ...
}

def validate_asset(file_name: str, data: list) -> list[str]:
    """파일명으로 스키마를 자동 선택해서 검증. 오류 목록 반환."""
    schema_cls = SCHEMA_MAP.get(file_name)
    if schema_cls is None:
        return []
    try:
        schema_cls.model_validate(data)
        return []
    except ValidationError as e:
        return [f"{file_name}[{err['loc']}]: {err['msg']}" for err in e.errors()]
```

이 함수는 기존 Validator 노드와 Full Generation의 generation_validator 모두에서 사용한다.

---

## 멀티턴 피드백 연결

Full Generation 완료 후, 사용자의 후속 수정 요청을 처리하는 흐름.

```
사용자: "중세 판타지 게임 만들어줘"
→ Full Generation 완료
→ game_files 테이블에 전체 파일 저장

사용자: "슬라임 HP 200으로 올려줘"
→ Router: 게임_요소_수정 (Intent.MODIFY)
→ 기존 Incremental Edit 파이프라인
→ game_files의 Enemies.json만 업데이트

사용자: "던전 구조 바꿔줘"
→ Router: 전체_게임_생성 또는 부분_재생성
→ Full Generation의 partial_regeneration (scope="maps")
```

### 부분 재생성 분류 로직

```python
# agent/graph/nodes/router.py 추가
PARTIAL_REGEN_KEYWORDS = [
    "맵 다시", "던전 다시", "맵 바꿔", "이벤트 다시",
    "처음부터", "완전히 다시", "스토리 바꿔",
]

def classify_intent_with_context(user_input: str, has_generation: bool) -> Intent:
    """
    기존 생성물이 있으면 부분 재생성 가능성 체크.
    """
    if has_generation and any(kw in user_input for kw in PARTIAL_REGEN_KEYWORDS):
        return Intent.PARTIAL_REGEN

    # 기본 분류 (LLM 호출)
    return llm_classify(user_input)
```

---

## 환경변수 추가 필요 항목

```bash
# .env 추가 항목

# Full Generation 관련
GENERATION_MAX_CONCURRENT=3          # 동시 생성 최대 수
GENERATION_TIMEOUT_SECONDS=300       # 최대 생성 시간
GENERATION_RETRY_MAX=2               # 검증 실패 시 최대 재시도 수

# 체크포인트 저장 (S3 또는 로컬)
CHECKPOINT_BACKEND=memory             # memory | s3 | redis
AWS_S3_GENERATION_BUCKET=re-verse-gen # S3 사용 시

# 비용 제한 (옵션)
GENERATION_DAILY_LIMIT_PER_USER=10   # 사용자당 일일 생성 횟수
```

---

## 개발 순서 (권장)

```
1단계: 기반 작업 (충돌 없음)
  □ agent/generation/ 폴더 구조 생성
  □ GenerationState TypedDict 정의
  □ 기존 invoke_llm() 공통 유틸 분리
  □ 스키마 검증 공통 유틸 (validate_asset) 작성

2단계: 결정론적 노드 먼저 (LLM 없음, 테스트 용이)
  □ asset_planner.py (ID 테이블 생성)
  □ mapgen/ (BSP 던전, 격자형 마을)
  □ event_compiler.py (DSL → RPG Maker 커맨드)
  □ integrator.py
  □ generation_validator.py

3단계: DB + API (기존 코드 영향 최소화)
  □ DB 마이그레이션 (generations 테이블)
  □ generation.py 라우터 (신규 파일)
  □ 기존 game.py에 Intent.FULL_GENERATE 분기만 추가

4단계: LLM 노드
  □ game_designer.py
  □ asset_generator.py
  □ map_designer.py
  □ event_planner.py

5단계: 워크플로우 연결 + 테스트
  □ workflow.py (LangGraph 그래프)
  □ 단위 테스트 (Mock LLM)
  □ 통합 테스트 (실제 LLM)
  □ 프론트엔드 연동 (WebSocket)
```

---

## 기존 코드 영향 범위 요약

| 파일 | 변경 | 내용 |
|------|------|------|
| `agent/graph/nodes/router.py` | **수정** | `Intent.FULL_GENERATE` 추가 |
| `agent/prompts/router_prompt.py` | **수정** | 분류 기준 추가 (~5줄) |
| `app/backend/main.py` | **수정** | generation 라우터 등록 (~3줄) |
| `app/backend/api/v1/game.py` | **수정** | Intent 분기 추가 (~10줄) |
| `agent/schemas/` | **변경 없음** | 재사용만 |
| `agent/core/llm_client.py` | **변경 없음** | 재사용만 (실제 파일명) |
| `app/backend/db/` | **마이그레이션** | generations 테이블 추가 |

**기존 Incremental Edit 동작에 영향 없음.**

---

## 리스크: 기존 파이프라인과의 충돌 지점

| 리스크 | 발생 조건 | 완화책 |
|--------|---------|--------|
| game_files 동시 쓰기 | Full Generation 완료 중 Incremental Edit 요청 | game_id 단위 분산락 (Redis) |
| Intent 분류 오탐 | "캐릭터 2명 만들어줘"가 FULL_GENERATE로 분류 | 프롬프트에 경계 명확히 정의 |
| 스키마 버전 불일치 | Full Gen이 다른 형식으로 저장 | 동일 game_files 테이블 + 동일 schema 사용 |
| 부분 재생성 후 Incremental 수정 | 스위치 번호 재할당으로 기존 이벤트 동작 이상 | 재생성 시 switch_table 유지 |

---

## 참고 링크

- Full Generation 계획 인덱스: `docs/The_world/full_generation_plan.md`
- API 설계: `docs/The_world/generation_api.md`
- 리스크 분석: `docs/The_world/risks_and_mitigations.md`
- 워크플로우 구현: `docs/The_world/workflow_implementation.md`
- 기존 Incremental Edit 워크플로우: `agent/graph/workflow.py`
