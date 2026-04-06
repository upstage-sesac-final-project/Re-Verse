# 스프린트 구현 계획 — Full Generation

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 목표

Phase 2(에셋) → Phase 3(맵) → Phase 4(이벤트) 순서로
8~9 스프린트(주 단위)에 걸쳐 Full Generation 시스템을 구현한다.

각 스프린트는 **완료 기준(Acceptance Criteria)** 이 있어야 다음 스프린트로 넘어갈 수 있다.
중간 결과물은 항상 실행 가능해야 한다 — "미완성이지만 실행됨" > "완성이지만 실행 불가".

---

## Phase 2 — 에셋 생성 (4 스프린트)

### Sprint 1 — 기반 구조 (Week 1)

**목표**: LLM 없이 전체 골격이 실행된다.

#### 구현 대상

```
agent/generation/
├── state.py                 # GenerationState TypedDict
├── registry/
│   ├── id_table.py          # IdTable 모델 + build_id_table()
│   └── switch_table.py      # SwitchTable 모델 + build_switch_table()
└── nodes/
    └── asset_planner.py     # B. 설계사 (LLM 없음)
```

**`state.py`** — GenerationState 전체 필드 정의
```python
class GenerationState(TypedDict):
    user_input: str
    game_id: str
    generation_id: str
    game_spec: GameSpec | None
    id_table: IdTable | None
    switch_table: SwitchTable | None
    generation_order: list[str]
    generated_assets: dict[str, Any]
    map_specs: list[MapSpec]
    map_tiles: dict[int, list[int]]
    connection_info: dict[int, MapConnectionInfo]
    event_dsl: dict[int, list]
    compiled_events: dict[int, list]
    final_project: dict[str, Any]
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    completed_phases: list[str]
    error_phase: str | None
    error_message: str | None
    retry_count: int
    phase_limit: str | None  # "assets" | "maps" | None
```

**`id_table.py`** — IdTable 모델
```python
class IdTable(BaseModel):
    actors:  dict[str, int]   # {"해럴드": 1}
    classes: dict[str, int]
    skills:  dict[str, int]
    items:   dict[str, int]
    weapons: dict[str, int]
    armors:  dict[str, int]
    enemies: dict[str, int]
    troops:  dict[str, int]
    maps:    dict[str, int]   # {"출발 마을": 1}

    def get_id(self, category: str, name: str) -> int:
        """이름으로 ID 조회. KeyError면 즉시 예외 (참조 오류 조기 발견)."""
        return getattr(self, category)[name]
```

**`asset_planner.py`** — 입력: GameSpec, 출력: IdTable + SwitchTable + generation_order
```python
async def run_asset_planner(state: GenerationState) -> dict:
    spec = state["game_spec"]
    id_table = _build_id_table(spec)
    switch_table = _build_switch_table(spec)
    order = _decide_order(spec)
    return {
        "id_table": id_table,
        "switch_table": switch_table,
        "generation_order": order,
    }

def _build_id_table(spec: GameSpec) -> IdTable:
    """이름 → 1부터 시작하는 연속 정수. 순서는 GameSpec 나열 순서."""
    actors  = {c.name: i+1 for i, c in enumerate(spec.characters)}
    classes = {c.class_name: i+1 for i, c in enumerate(spec.characters)}
    # 중복 class_name이 있으면 첫 번째 ID 유지
    classes = dict(zip(classes.keys(), range(1, len(classes)+1)))
    enemies = {e.name: i+1 for i, e in enumerate(spec.enemies)}
    troops  = {e.name: i+1 for i, e in enumerate(spec.enemies)}
    maps    = {m.name: i+1 for i, m in enumerate(spec.maps)}
    # skills/items/weapons/armors: 플레이스홀더 (LLM이 채움)
    # asset_planner는 이름 목록을 미리 모르므로 빈 dict로 시작
    # → asset_generator가 생성 후 id_table에 병합
    return IdTable(
        actors=actors, classes=classes,
        skills={}, items={}, weapons={}, armors={},
        enemies=enemies, troops=troops, maps=maps,
    )
```

> **설계 결정**: Skills/Items/Weapons/Armors는 이름을 미리 모르므로
> asset_planner에서는 빈 dict로 초기화하고,
> asset_generator가 각 파일을 생성한 뒤 id_table에 병합한다.
> 이 순서는 `generation_order` 필드가 보장한다 (skills → items → weapons → armors → actors → enemies → troops 순).

#### 테스트 목표

```python
# agent/tests/generation/test_asset_planner.py

def test_id_starts_at_one():
    spec = make_minimal_spec()  # fixture: 캐릭터 2, 적 3, 맵 2
    result = _build_id_table(spec)
    assert result.actors["해럴드"] == 1
    assert result.actors["세라"] == 2
    assert result.maps["출발 마을"] == 1

def test_no_id_duplicates():
    spec = make_minimal_spec()
    result = _build_id_table(spec)
    all_ids = list(result.actors.values()) + list(result.enemies.values())
    # 같은 카테고리 내 중복 없음
    assert len(set(result.actors.values())) == len(result.actors)
    assert len(set(result.enemies.values())) == len(result.enemies)

def test_switch_table_no_conflicts():
    spec = make_minimal_spec()
    result = _build_switch_table(spec)
    all_ids = list(result.switches.values())
    assert len(set(all_ids)) == len(all_ids)  # 중복 없음
    assert min(all_ids) >= 1

def test_generation_order_dependencies():
    spec = make_minimal_spec()
    order = _decide_order(spec)
    # actors는 classes 뒤에 와야 함
    assert order.index("actors") > order.index("classes")
    # enemies는 skills 뒤에 와야 함 (action 참조)
    assert order.index("enemies") > order.index("skills")
```

#### 완료 기준

- [ ] `python -c "from agent.generation.nodes.asset_planner import run_asset_planner"` 에러 없음
- [ ] test_asset_planner.py 4개 테스트 전부 통과
- [ ] `IdTable.get_id("actors", "없는이름")` → `KeyError` 발생 확인

---

### Sprint 2 — 기획자 + 에셋 생성 (Week 2)

**목표**: 자연어 입력 → GameSpec → RPG Maker MZ JSON (맵 없음)

#### 구현 대상

```
agent/generation/
├── nodes/
│   ├── game_designer.py     # A. 기획자
│   └── asset_generator.py   # C. 에셋 생성
└── prompts/
    ├── game_designer_prompt.py
    └── asset_generator_prompt.py
```

**`game_designer.py`** — LLM 1회 → GameSpec
```python
async def run_game_designer(state: GenerationState) -> dict:
    prompt = build_game_designer_prompt(state["user_input"])
    raw = await invoke_llm(prompt, temperature=0.8)
    spec = _parse_game_spec(raw)
    return {"game_spec": spec}

def _parse_game_spec(raw: str) -> GameSpec:
    data = _extract_json(raw)
    _validate_map_connections(data)  # connects_to BFS 연결성 확인
    return GameSpec.model_validate(data)
```

**`asset_generator.py`** — asyncio.gather() 병렬 LLM 호출
```python
async def run_asset_generator(state: GenerationState) -> dict:
    spec = state["game_spec"]
    id_table = state["id_table"]
    order = state["generation_order"]

    results: dict[str, Any] = {}
    # 순서대로 실행 (의존성 때문에 완전 병렬 불가)
    for asset_type in order:
        result = await _generate_asset(asset_type, spec, id_table, results)
        results[asset_type] = result
        # skills/items/weapons/armors 생성 직후 id_table 병합
        if asset_type in ("skills", "items", "weapons", "armors"):
            id_table = _merge_ids(id_table, asset_type, result)

    return {"generated_assets": results, "id_table": id_table}

async def _generate_asset(
    asset_type: str,
    spec: GameSpec,
    id_table: IdTable,
    already_generated: dict,
) -> list[dict]:
    prompt = build_asset_prompt(asset_type, spec, id_table, already_generated)
    raw = await invoke_llm(prompt, temperature=0.3)
    data = _extract_json(raw)
    schema = ASSET_SCHEMA_MAP[asset_type]
    validated = [schema.model_validate(item) for item in data]
    return [item.model_dump() for item in validated]
```

> **주의**: `asyncio.gather()` 대신 순차 실행을 쓰는 이유:
> - actors는 classId(=classes에서 생성된 ID)를 참조한다
> - enemies의 actions은 skillId를 참조한다
> - `generation_order`가 이 의존성 순서를 보장한다
> 단, classes와 skills는 서로 독립적이므로 이 두 개만 gather() 가능.

**`asset_generator_prompt.py`** 핵심 규칙:
```python
ASSET_PROMPT_RULES = {
    "actors": """
- id는 반드시 id_table.actors[이름] 값 사용
- classId는 반드시 id_table.classes[클래스명] 값 사용
- equips 배열: [weaponId, shieldId, headId, bodyId, accessoryId] (5개 고정)
- level: 1~5 (시작 레벨)
""",
    "skills": """
- id는 1부터 순서대로 (id_table에 없으므로 직접 부여)
- scope: 0~14 정수만 허용 (문자열 금지)
- damage.formula: "a.atk * 2 - b.def" 형식 (JavaScript 표현식)
- mpCost: 0 이상 정수
""",
    "enemies": """
- id는 반드시 id_table.enemies[이름] 값 사용
- params: 8개 정수 배열 [maxHP, maxMP, atk, def, matk, mdef, agi, luck]
- dropItems: 정확히 3개 원소 (부족하면 {"kind":0,"dataId":0,"denominator":1}로 채움)
- actions[].skillId: id_table.skills에서 반드시 참조
""",
}
```

#### 테스트 목표

```python
# agent/tests/generation/test_asset_generator.py

@pytest.mark.asyncio
async def test_actors_reference_classes(mock_llm):
    """생성된 Actor.classId가 id_table.classes에 존재해야 함."""
    state = make_state_after_planner()
    result = await run_asset_generator(state)
    id_table = result["id_table"]
    for actor in result["generated_assets"]["actors"]:
        assert actor["classId"] in id_table.classes.values()

@pytest.mark.asyncio
async def test_enemy_drop_items_always_three(mock_llm):
    state = make_state_after_planner()
    result = await run_asset_generator(state)
    for enemy in result["generated_assets"]["enemies"]:
        assert len(enemy["dropItems"]) == 3

@pytest.mark.asyncio
async def test_skill_scope_is_integer(mock_llm):
    state = make_state_after_planner()
    result = await run_asset_generator(state)
    for skill in result["generated_assets"]["skills"]:
        assert isinstance(skill["scope"], int)
        assert 0 <= skill["scope"] <= 14

@pytest.mark.asyncio
async def test_id_table_merged_after_skills(mock_llm):
    """skills 생성 후 id_table.skills가 채워져야 함."""
    state = make_state_after_planner()
    result = await run_asset_generator(state)
    assert len(result["id_table"].skills) > 0
```

#### 완료 기준

- [ ] `mock_llm` fixture가 유효한 JSON 반환 시 모든 Pydantic 검증 통과
- [ ] 4개 테스트 통과
- [ ] 생성된 Actors.json의 classId가 Classes.json의 실제 ID와 일치

---

### Sprint 3 — 통합기 + 검증기 (Week 3)

**목표**: Phase 2 완전 실행 — "에셋만" 파이프라인이 유효한 RPG Maker MZ 파일 생성

#### 구현 대상

```
agent/generation/
└── nodes/
    ├── integrator.py            # H. 통합기 (에셋 부분)
    └── generation_validator.py  # I. 검증기
```

**`integrator.py`** — Phase 2 (에셋 조립)
```python
async def run_integrator(state: GenerationState) -> dict:
    assets = state["generated_assets"]
    id_table = state["id_table"]
    final: dict[str, Any] = {}

    # 1. 에셋 파일 조립 (index-0 null 규칙 적용)
    for asset_type, data in assets.items():
        filename = ASSET_TO_FILENAME[asset_type]  # "actors" → "Actors.json"
        final[filename] = ensure_null_at_index_0(data)

    # 2. System.json (제목, 시작 위치 등)
    final["System.json"] = _build_system_json(state)

    # 3. 빈 맵 (Phase 2에서는 맵 없음 → 검은 화면)
    final["Map001.json"] = _build_empty_map()

    return {"final_project": final}

def ensure_null_at_index_0(data: list[dict]) -> list[dict | None]:
    """RPG Maker MZ 규칙: index 0은 반드시 null."""
    if not data or data[0] is not None:
        return [None] + data
    return data
```

**`generation_validator.py`** — Phase 2 검증
```python
async def run_generation_validator(state: GenerationState) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    project = state["final_project"]
    id_table = state["id_table"]

    # 1. ID 참조 무결성
    errors += check_id_references(project, id_table)

    # 2. index-0 null 규칙
    errors += check_null_at_index_0(project)

    # 3. 배열 길이 (params 8개, dropItems 3개 등)
    errors += check_array_lengths(project)

    # 4. 밸런스 (경고만 — 에러로 처리하지 않음)
    warnings += check_balance(project)

    passed = len(errors) == 0
    return {
        "validation_passed": passed,
        "validation_errors": errors,
        "validation_warnings": warnings,
    }

def check_id_references(project: dict, id_table: IdTable) -> list[str]:
    errors = []
    actors = project.get("Actors.json", [])[1:]  # null 제거
    for actor in actors:
        cid = actor.get("classId")
        if cid not in id_table.classes.values():
            errors.append(f"Actor '{actor['name']}' classId={cid} not in Classes")
    # enemies.actions[].skillId 검증
    for enemy in project.get("Enemies.json", [])[1:]:
        for action in enemy.get("actions", []):
            sid = action.get("skillId")
            if sid and sid not in id_table.skills.values():
                errors.append(f"Enemy '{enemy['name']}' action skillId={sid} not found")
    return errors
```

#### 테스트 목표

```python
# agent/tests/generation/test_generation_validator.py

def test_valid_project_passes():
    project = build_valid_project()
    id_table = build_matching_id_table()
    errors, warnings = run_sync(run_generation_validator, {
        "final_project": project, "id_table": id_table
    })
    assert errors == []

def test_invalid_class_id_fails():
    project = build_project_with_bad_class_id()
    id_table = build_matching_id_table()
    result = run_sync(run_generation_validator, {...})
    assert any("classId" in e for e in result["validation_errors"])

def test_null_at_index_0_enforced():
    data = [{"id": 1, "name": "검사"}]  # null 없음
    fixed = ensure_null_at_index_0(data)
    assert fixed[0] is None
    assert fixed[1]["id"] == 1

def test_balance_boss_warning():
    """보스 HP가 너무 낮으면 경고."""
    project = build_project_with_weak_boss()
    result = run_sync(run_generation_validator, {...})
    assert any("boss" in w.lower() for w in result["validation_warnings"])
```

#### 완료 기준

- [ ] Phase 2 파이프라인 end-to-end 실행 (mock LLM 사용)
- [ ] 출력된 Actors.json index-0 null, ID 1부터 시작 확인
- [ ] 검증기 4개 테스트 통과
- [ ] `uv run ruff check .` 에러 없음

---

### Sprint 4 — DB + API + WebSocket (Week 4)

**목표**: HTTP API로 생성 요청 가능, WebSocket으로 진행률 실시간 스트리밍

#### 구현 대상

```
app/backend/
├── models/
│   └── generation.py        # GenerationRecord ORM 모델
├── api/v1/
│   └── generation.py        # FastAPI 라우터
└── db/
    └── migrations/
        └── 003_add_generations.sql

agent/generation/
├── workflow.py              # LangGraph 그래프 (Phase 2 sub-graph)
└── progress.py              # WebSocket 진행률 발행
```

**`003_add_generations.sql`**:
```sql
CREATE TABLE generations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id     UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','running','completed','failed','cancelled')),
    phase       TEXT,
    progress    INTEGER DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    error       TEXT,
    result_path TEXT,  -- S3 키 또는 로컬 경로
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE games ADD COLUMN IF NOT EXISTS last_generation_id UUID
    REFERENCES generations(id);
```

**`generation.py`** (API 라우터):
```python
router = APIRouter(prefix="/api/v1/generate", tags=["generation"])

@router.post("", status_code=202)
async def start_generation(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    # 동시 생성 제한
    active = await db.fetch_one(
        "SELECT id FROM generations WHERE game_id=$1 AND status='running'",
        request.game_id,
    )
    if active:
        raise HTTPException(409, "이미 진행 중인 생성이 있습니다")

    gen = await db.fetch_one(
        "INSERT INTO generations(game_id) VALUES($1) RETURNING id",
        request.game_id,
    )
    background_tasks.add_task(
        run_generation_in_background,
        str(gen["id"]), str(request.game_id), request.user_input,
    )
    return {"generation_id": str(gen["id"]), "status": "pending"}

@router.websocket("/{generation_id}/ws")
async def generation_websocket(
    websocket: WebSocket,
    generation_id: str,
    token: str = Query(...),
):
    user = verify_token(token)
    await websocket.accept()
    async for event in subscribe_generation_events(generation_id):
        await websocket.send_json(event)
        if event["type"] in ("completed", "error"):
            break
    await websocket.close()
```

**`progress.py`** — pub/sub (in-memory, Phase 2용):
```python
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

async def publish_progress(generation_id: str, event: dict) -> None:
    for q in _subscribers.get(generation_id, []):
        await q.put(event)

async def subscribe_generation_events(generation_id: str):
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[generation_id].append(q)
    try:
        while True:
            event = await q.get()
            yield event
            if event["type"] in ("completed", "error"):
                break
    finally:
        _subscribers[generation_id].remove(q)
```

> **참고**: Phase 2는 단일 서버이므로 in-memory pub/sub이 안전하다.
> Phase 4(Celery)로 전환 시 Redis Pub/Sub으로 교체 (`deployment_and_ops.md` 참조).

#### 테스트 목표

```python
# app/backend/tests/test_generation_api.py

@pytest.mark.asyncio
async def test_start_generation_returns_202(client, mock_workflow):
    response = await client.post("/api/v1/generate", json={
        "game_id": "...", "user_input": "판타지 게임 만들어줘"
    })
    assert response.status_code == 202
    assert "generation_id" in response.json()

@pytest.mark.asyncio
async def test_concurrent_generation_rejected(client, mock_workflow):
    # 첫 번째 요청 → 202
    r1 = await client.post("/api/v1/generate", json={...})
    assert r1.status_code == 202
    # 두 번째 요청 (같은 game_id) → 409
    r2 = await client.post("/api/v1/generate", json={...})
    assert r2.status_code == 409

@pytest.mark.asyncio
async def test_websocket_receives_progress(client, mock_workflow):
    gen_id = (await client.post("/api/v1/generate", json={...})).json()["generation_id"]
    async with client.websocket_connect(f"/api/v1/generate/{gen_id}/ws?token=...") as ws:
        msgs = []
        for _ in range(5):
            msgs.append(await ws.receive_json())
        assert any(m["type"] == "progress" for m in msgs)
        assert any(m["type"] == "completed" for m in msgs)
```

#### 완료 기준

- [ ] `POST /api/v1/generate` → 202, generation_id 반환
- [ ] WebSocket 연결 → 7개 메시지 타입 중 progress + completed 수신
- [ ] 동시 생성 요청 → 409
- [ ] DB migrations 적용 후 `generations` 테이블 존재 확인

---

## Phase 3 — 맵 생성 (2 스프린트)

### Sprint 5 — 맵 생성기 (Week 5)

**목표**: 알고리즘으로 마을/던전 타일 배열 생성 (LLM 없음)

#### 구현 대상

```
agent/generation/mapgen/
├── __init__.py          # generate_map() 진입점
├── tile_constants.py    # 타일셋 ID 매핑
├── town_generator.py    # 격자형 마을
└── dungeon_generator.py # BSP 던전
```

**`tile_constants.py`**:
```python
# 타일셋 1 (마을)
TOWN_TILES = {
    "floor":     0x0000,   # 평지 (walkable)
    "wall":      0x0400,   # 벽
    "road":      0x0002,   # 도로
    "building":  0x0c00,   # 건물 외벽 (non-walkable)
    "door":      0x0001,   # 문 (walkable)
    "water":     0x0600,   # 물 (non-walkable)
    "tree":      0x0800,   # 나무 (non-walkable)
}

# 타일셋 2 (던전)
DUNGEON_TILES = {
    "floor":    0x0000,
    "wall":     0x0400,
    "corridor": 0x0001,
    "entrance": 0x0003,
    "exit":     0x0004,
    "chest":    0x0005,   # 장식용 (실제 상자는 이벤트)
}

# map_type → tilesetId 고정 매핑
MAP_TYPE_TO_TILESET: dict[str, int] = {
    "town":    1,
    "dungeon": 2,
    "boss":    2,
    "field":   3,
}
```

**`dungeon_generator.py`** — BSP 핵심 구조:
```python
@dataclass
class Rect:
    x: int; y: int; w: int; h: int

    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def intersects(self, other: "Rect") -> bool:
        return (self.x < other.x + other.w and self.x + self.w > other.x and
                self.y < other.y + other.h and self.y + self.h > other.y)

class BSPNode:
    MIN_SIZE = 6

    def __init__(self, rect: Rect, rng: random.Random):
        self.rect = rect
        self.rng = rng
        self.left: BSPNode | None = None
        self.right: BSPNode | None = None
        self.room: Rect | None = None

    def split(self) -> bool:
        if self.left or self.right:
            return False
        # 가로/세로 중 랜덤 분할
        horizontal = self.rng.choice([True, False])
        if horizontal:
            if self.rect.h < self.MIN_SIZE * 2:
                return False
            split_at = self.rng.randint(self.MIN_SIZE, self.rect.h - self.MIN_SIZE)
            self.left  = BSPNode(Rect(self.rect.x, self.rect.y, self.rect.w, split_at), self.rng)
            self.right = BSPNode(Rect(self.rect.x, self.rect.y + split_at, self.rect.w, self.rect.h - split_at), self.rng)
        else:
            if self.rect.w < self.MIN_SIZE * 2:
                return False
            split_at = self.rng.randint(self.MIN_SIZE, self.rect.w - self.MIN_SIZE)
            self.left  = BSPNode(Rect(self.rect.x, self.rect.y, split_at, self.rect.h), self.rng)
            self.right = BSPNode(Rect(self.rect.x + split_at, self.rect.y, self.rect.w - split_at, self.rect.h), self.rng)
        return True

    def create_room(self) -> None:
        if self.left or self.right:
            if self.left:  self.left.create_room()
            if self.right: self.right.create_room()
        else:
            w = self.rng.randint(4, self.rect.w - 2)
            h = self.rng.randint(4, self.rect.h - 2)
            x = self.rect.x + self.rng.randint(1, self.rect.w - w - 1)
            y = self.rect.y + self.rng.randint(1, self.rect.h - h - 1)
            self.room = Rect(x, y, w, h)

    def get_rooms(self) -> list[Rect]:
        if self.room:
            return [self.room]
        rooms = []
        if self.left:  rooms += self.left.get_rooms()
        if self.right: rooms += self.right.get_rooms()
        return rooms


def generate_dungeon(width: int, height: int, seed: int) -> list[int]:
    """RPG Maker MZ data 배열 반환. 길이 = width * height * 6 (6레이어)."""
    rng = random.Random(seed)
    root = BSPNode(Rect(0, 0, width, height), rng)
    # 4회 분할
    nodes = [root]
    for _ in range(4):
        nodes = [n for node in nodes for n in ([node.left, node.right] if node.split() else [node])]
    root.create_room()
    rooms = root.get_rooms()
    # 타일 배열 초기화 (모두 벽)
    tiles = [DUNGEON_TILES["wall"]] * (width * height)
    # 방 그리기
    for room in rooms:
        for ry in range(room.y, room.y + room.h):
            for rx in range(room.x, room.x + room.w):
                tiles[ry * width + rx] = DUNGEON_TILES["floor"]
    # 방 연결 (L자 복도)
    for i in range(len(rooms) - 1):
        c1 = rooms[i].center()
        c2 = rooms[i + 1].center()
        _carve_corridor(tiles, c1, c2, width, DUNGEON_TILES["corridor"])
    # 6레이어로 확장 (레이어 0만 타일, 나머지 0)
    return tiles + [0] * (width * height * 5)
```

#### 테스트 목표

```python
# agent/tests/generation/test_dungeon_generator.py

@pytest.mark.parametrize("seed", range(10))
def test_dungeon_is_connected(seed):
    """BFS로 모든 floor/corridor 셀이 연결되어 있어야 함."""
    tiles = generate_dungeon(40, 30, seed)
    floor_ids = {DUNGEON_TILES["floor"], DUNGEON_TILES["corridor"]}
    walkable = {(i % 40, i // 40) for i, t in enumerate(tiles[:40*30]) if t in floor_ids}
    start = next(iter(walkable))
    visited = bfs(start, walkable)
    assert visited == walkable, f"seed={seed}: {len(walkable - visited)} disconnected cells"

@pytest.mark.parametrize("seed", range(10))
def test_town_has_road_network(seed):
    tiles = generate_town(30, 30, seed)
    road_id = TOWN_TILES["road"]
    roads = {(i % 30, i // 30) for i, t in enumerate(tiles[:30*30]) if t == road_id}
    assert len(roads) > 20, f"seed={seed}: too few road tiles ({len(roads)})"

def test_spawn_point_found():
    tiles = generate_dungeon(40, 30, seed=0)
    spawn = calculate_spawn_point(tiles, 40, 30)
    assert spawn is not None
    x, y = spawn
    idx = y * 40 + x
    assert tiles[idx] in {DUNGEON_TILES["floor"], DUNGEON_TILES["corridor"]}
```

#### 완료 기준

- [ ] seed 0~9 모두 연결성 BFS 통과 (던전 + 마을)
- [ ] generate_map() 진입점이 MapSpec 받아 `list[int]` 반환
- [ ] `MAP_TYPE_TO_TILESET` 사용으로 타일셋 ID 하드코딩 없음

---

### Sprint 6 — 맵 설계사 + 맵 통합 (Week 6)

**목표**: "걸어다닐 수 있는 맵 3개" — 맵 간 이동 가능

#### 구현 대상

```
agent/generation/
├── nodes/
│   └── map_designer.py      # D. 맵 설계사
└── prompts/
    └── map_designer_prompt.py
```

**`map_designer.py`** — LLM 1회 → 상세 MapSpec 목록
```python
async def run_map_designer(state: GenerationState) -> dict:
    spec = state["game_spec"]
    id_table = state["id_table"]

    prompt = build_map_designer_prompt(spec, id_table)
    raw = await invoke_llm(prompt, temperature=0.6)
    map_specs = _parse_map_specs(raw)

    # 맵 타일 생성 (알고리즘, LLM 없음)
    map_tiles: dict[int, list[int]] = {}
    connection_info: dict[int, MapConnectionInfo] = {}

    for map_spec in map_specs:
        map_id = id_table.get_id("maps", map_spec.name)
        seed = hash(f"{state['generation_id']}:{map_spec.name}") % (2**32)
        tiles = generate_map(map_spec, seed)
        map_tiles[map_id] = tiles

    # 연결 좌표 계산 (R4 방지)
    connection_info = _calculate_connection_info(map_specs, id_table, map_tiles)

    return {
        "map_specs": map_specs,
        "map_tiles": map_tiles,
        "connection_info": connection_info,
    }

def _calculate_connection_info(
    specs: list[MapSpec],
    id_table: IdTable,
    tiles: dict[int, list[int]],
) -> dict[int, MapConnectionInfo]:
    """각 맵의 출구/입구 좌표를 미리 계산해 event_planner에 주입."""
    info = {}
    for spec in specs:
        map_id = id_table.get_id("maps", spec.name)
        # 출구 위치: 맵 하단 중앙 (던전) 또는 경계 (마을)
        exits = []
        for target_name in spec.connects_to:
            target_id = id_table.get_id("maps", target_name)
            exit_coord = _find_exit_coord(tiles[map_id], spec)
            entry_coord = _find_entry_coord(tiles[target_id], spec)
            exits.append(ExitInfo(
                target_map_id=target_id,
                exit_x=exit_coord[0], exit_y=exit_coord[1],
                entry_x=entry_coord[0], entry_y=entry_coord[1],
            ))
        info[map_id] = MapConnectionInfo(map_id=map_id, exits=exits)
    return info
```

**Integrator 업데이트** — Map*.json 조립 추가:
```python
# integrator.py에 추가
for map_spec in state["map_specs"]:
    map_id = id_table.get_id("maps", map_spec.name)
    filename = f"Map{map_id:03d}.json"
    final[filename] = _build_map_json(
        map_spec=map_spec,
        tiles=state["map_tiles"][map_id],
        events=state["compiled_events"].get(map_id, []),
        tileset_id=MAP_TYPE_TO_TILESET[map_spec.type],
    )
```

#### 완료 기준

- [ ] Phase 3 파이프라인 실행 → Map001.json, Map002.json, Map003.json 생성
- [ ] 각 맵의 data 배열 길이 = width * height * 6
- [ ] `connection_info`에 모든 맵의 출구 좌표 포함
- [ ] RPG Maker MZ에서 프로젝트 열었을 때 맵 3개가 보임 (수동 확인)

---

## Phase 4 — 이벤트 생성 (2 스프린트)

### Sprint 7 — DSL 컴파일러 (Week 7)

**목표**: YAML DSL → RPG Maker MZ 커맨드 코드 변환

#### 구현 대상

```
agent/generation/compilers/
├── dsl_models.py        # DSL Pydantic 모델
└── event_compiler.py    # DSL → RPG Maker 커맨드
```

**`dsl_models.py`**:
```python
class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str
    x: int; y: int
    lines: list[str]                     # 대화 줄 목록
    face_name: str = "Actor1"
    face_index: int = 0
    condition_switch: int | None = None  # 조건부 표시

class TransferEvent(BaseModel):
    type: Literal["transfer"]
    name: str
    x: int; y: int
    target_map_id: int
    target_x: int
    target_y: int
    trigger: Literal["touch", "interact"] = "touch"

class ChestEvent(BaseModel):
    type: Literal["chest"]
    name: str
    x: int; y: int
    item_type: Literal["item", "weapon", "armor"]
    item_id: int
    amount: int = 1
    switch_id: int        # 열림 여부 추적 스위치

class BattleEvent(BaseModel):
    type: Literal["battle"]
    name: str
    x: int; y: int
    troop_id: int
    can_escape: bool = True
    defeat_switch_id: int  # 처치 후 스위치 ON

class ShopEvent(BaseModel):
    type: Literal["shop"]
    name: str
    x: int; y: int
    items: list[dict]  # [{"type": "item", "id": 3, "price": 100}]

DslEvent = NpcEvent | TransferEvent | ChestEvent | BattleEvent | ShopEvent | EndingEvent
# EndingEvent: game_ending_design.md 참조
```

**`event_compiler.py`** — NPC 컴파일 예시:
```python
def compile_npc(event: NpcEvent) -> dict:
    """DSL NpcEvent → RPG Maker MZ Map Event JSON."""
    pages = [{
        "conditions": _make_conditions(event.condition_switch),
        "directionFix": False,
        "image": {
            "characterName": "Actor1",
            "characterIndex": 0,
            "direction": 2,
            "pattern": 1,
        },
        "list": _compile_npc_commands(event),
        "moveType": 0,
        "trigger": 0,  # 0=interact
        "walkAnime": True,
    }]
    return {
        "id": 0,  # 통합기가 실제 ID 부여
        "name": event.name,
        "note": "",
        "pages": pages,
        "x": event.x,
        "y": event.y,
    }

def _compile_npc_commands(event: NpcEvent) -> list[dict]:
    cmds = []
    for line in event.lines:
        cmds.append({
            "code": 101,  # ShowText
            "indent": 0,
            "parameters": [event.face_name, event.face_index, 0, 2, event.name],
        })
        cmds.append({
            "code": 401,  # ShowText (continuation)
            "indent": 0,
            "parameters": [line],
        })
    cmds.append({"code": 0, "indent": 0, "parameters": []})  # end
    return cmds

def compile_transfer(event: TransferEvent) -> dict:
    trigger = 1 if event.trigger == "interact" else 2  # 1=interact, 2=touch
    commands = [
        {
            "code": 201,  # Transfer Player
            "indent": 0,
            "parameters": [0, event.target_map_id, event.target_x, event.target_y, 0, 0],
        },
        {"code": 0, "indent": 0, "parameters": []},
    ]
    return _wrap_event(event.name, event.x, event.y, trigger, commands)
```

#### 테스트 목표

```python
# agent/tests/generation/test_event_compiler.py

def test_npc_compile_produces_code_101():
    event = NpcEvent(type="npc", name="마을 사람", x=5, y=3,
                     lines=["안녕하세요!", "오늘도 좋은 날이네요."])
    result = compile_npc(event)
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 101 in codes
    assert 401 in codes
    assert codes[-1] == 0  # end

def test_transfer_compile_code_201():
    event = TransferEvent(type="transfer", name="던전 입구", x=10, y=5,
                          target_map_id=2, target_x=3, target_y=4)
    result = compile_transfer(event)
    cmds = result["pages"][0]["list"]
    assert cmds[0]["code"] == 201
    assert cmds[0]["parameters"][1] == 2  # target_map_id

def test_chest_compile_sets_switch():
    event = ChestEvent(type="chest", name="보물상자", x=7, y=3,
                       item_type="item", item_id=5, switch_id=1)
    result = compile_chest(event)
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 126 in codes  # ChangeItem
    assert 121 in codes  # ControlSwitches

def test_battle_compile_code_301():
    event = BattleEvent(type="battle", name="보스전", x=15, y=8,
                        troop_id=3, defeat_switch_id=5)
    result = compile_battle(event)
    cmds = result["pages"][0]["list"]
    assert cmds[0]["code"] == 301  # Battle Processing

def test_npc_with_condition_switch():
    event = NpcEvent(..., condition_switch=3)
    result = compile_npc(event)
    cond = result["pages"][0]["conditions"]
    assert cond["switch1Valid"] is True
    assert cond["switch1Id"] == 3
```

#### 완료 기준

- [ ] 12개 컴파일러 테스트 전부 통과
- [ ] `compile_event(dsl_event)` 단일 진입점이 DslEvent 유니온 처리
- [ ] 알 수 없는 DSL 타입 → `ValueError` (조용히 무시 금지)

---

### Sprint 8 — 이벤트 기획자 + 전체 파이프라인 (Week 8)

**목표**: "중세 판타지 게임 만들어줘" → 27초 내 플레이 가능한 RPG Maker MZ 프로젝트

#### 구현 대상

```
agent/generation/
├── nodes/
│   └── event_planner.py     # F. 이벤트 기획자
├── prompts/
│   └── event_planner_prompt.py
└── workflow.py               # 전체 LangGraph 그래프 완성
```

**`event_planner.py`** — LLM 맵당 1회 → YAML DSL
```python
async def run_event_planner(state: GenerationState) -> dict:
    map_specs = state["map_specs"]
    id_table = state["id_table"]
    switch_table = state["switch_table"]
    connection_info = state["connection_info"]

    # 맵별 병렬 처리 (각 맵은 독립적)
    tasks = [
        _plan_single_map(spec, id_table, switch_table, connection_info)
        for spec in map_specs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    event_dsl: dict[int, list] = {}
    for spec, result in zip(map_specs, results):
        map_id = id_table.get_id("maps", spec.name)
        if isinstance(result, Exception):
            event_dsl[map_id] = _build_fallback_events(spec, connection_info[map_id])
        else:
            event_dsl[map_id] = result

    return {"event_dsl": event_dsl}

async def _plan_single_map(
    spec: MapSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: dict[int, MapConnectionInfo],
) -> list:
    map_id = id_table.get_id("maps", spec.name)
    conn = connection_info[map_id]

    for attempt in range(3):
        prompt = build_event_planner_prompt(spec, id_table, switch_table, conn)
        raw = await invoke_llm(prompt, temperature=0.7)
        dsl = _parse_yaml_dsl(raw)
        if _validate_dsl_coords(dsl, spec) and _validate_dsl_names(dsl, id_table):
            return dsl
        # 재시도 시 오류 내용을 프롬프트에 포함
    raise ValueError(f"event_planner: {spec.name} failed after 3 attempts")
```

**`workflow.py`** — 전체 그래프:
```python
def build_generation_graph() -> StateGraph:
    graph = StateGraph(GenerationState)

    graph.add_node("game_designer",  run_game_designer)
    graph.add_node("asset_planner",  run_asset_planner)
    graph.add_node("asset_generator", run_asset_generator)
    graph.add_node("map_designer",   run_map_designer)
    graph.add_node("event_planner",  run_event_planner)
    graph.add_node("event_compiler", run_event_compiler)
    graph.add_node("integrator",     run_integrator)
    graph.add_node("validator",      run_generation_validator)
    graph.add_node("responder",      run_responder)

    graph.set_entry_point("game_designer")
    graph.add_edge("game_designer",  "asset_planner")
    graph.add_edge("asset_planner",  "asset_generator")
    graph.add_conditional_edges(
        "asset_generator",
        _route_after_assets,
        {"maps": "map_designer", "skip": "integrator"},
    )
    graph.add_edge("map_designer",   "event_planner")
    graph.add_edge("event_planner",  "event_compiler")
    graph.add_edge("event_compiler", "integrator")
    graph.add_edge("integrator",     "validator")
    graph.add_conditional_edges(
        "validator",
        _route_after_validation,
        {"ok": "responder", "retry_assets": "asset_generator",
         "retry_events": "event_planner", "give_up": "responder"},
    )
    graph.set_finish_point("responder")
    return graph.compile(checkpointer=MemorySaver())

def _route_after_assets(state: GenerationState) -> str:
    if state.get("phase_limit") == "assets":
        return "skip"
    return "maps"

def _route_after_validation(state: GenerationState) -> str:
    errors = state.get("validation_errors", [])
    if not errors:
        return "ok"
    if state.get("retry_count", 0) >= 2:
        return "give_up"
    # 에러 종류에 따라 재시도 지점 선택
    if any("classId" in e or "skillId" in e for e in errors):
        return "retry_assets"
    return "retry_events"
```

#### 테스트 목표

```python
# agent/tests/generation/test_full_pipeline.py

@pytest.mark.asyncio
async def test_full_pipeline_assets_only(mock_llm_fixture):
    """Phase 2: phase_limit='assets'로 맵 없이 실행."""
    result = await run_generation_workflow(
        user_input="판타지 게임 만들어줘",
        game_id="test-game-id",
        generation_id="test-gen-id",
        phase_limit="assets",
    )
    assert result["validation_passed"] is True
    assert "Actors.json" in result["final_project"]
    assert result["final_project"]["Actors.json"][0] is None  # null at index 0

@pytest.mark.asyncio
async def test_full_pipeline_with_maps(mock_llm_fixture):
    """Phase 3+4: 전체 실행."""
    result = await run_generation_workflow(
        user_input="중세 판타지 게임 만들어줘",
        game_id="test-game-id",
        generation_id="test-gen-id",
    )
    assert result["validation_passed"] is True
    assert "Map001.json" in result["final_project"]
    map_data = result["final_project"]["Map001.json"]
    w, h = map_data["width"], map_data["height"]
    assert len(map_data["data"]) == w * h * 6  # 6레이어

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_real_llm():
    """실제 LLM 호출 (CI에서는 skip)."""
    import time
    start = time.time()
    result = await run_generation_workflow(
        user_input="중세 판타지 게임 만들어줘",
        game_id="real-test-game",
        generation_id="real-test-gen",
    )
    elapsed = time.time() - start
    assert result["validation_passed"] is True
    assert elapsed < 60, f"너무 느림: {elapsed:.1f}초"
```

#### 완료 기준

- [ ] `pytest -m "not integration"` — 전체 통과
- [ ] mock LLM으로 end-to-end 실행 시 `validation_passed=True`
- [ ] 출력 프로젝트가 RPG Maker MZ에서 오류 없이 열림 (수동 확인)
- [ ] WebSocket으로 progress 0%→100% 스트리밍 확인

---

## Phase 5 — 품질 개선 (Sprint 9)

### Sprint 9 — 밸런스 + 프론트엔드 (Week 9)

**목표**: 플레이어가 실제로 플레이할 수 있는 수준의 밸런스 + 프론트엔드 UI

#### 구현 대상

```
agent/generation/
└── balance.py               # simulate_battle() + validators

app/frontend/src/
├── store/generationSlice.ts
├── store/generationMiddleware.ts
├── components/generation/
│   ├── GenerationForm.tsx
│   ├── GenerationProgress.tsx
│   └── GenerationResult.tsx
└── pages/GeneratePage.tsx
```

**`balance.py`** 핵심:
```python
def simulate_battle(
    player_hp: int, player_atk: int, player_def: int,
    enemy_hp: int, enemy_atk: int, enemy_def: int,
    max_turns: int = 50,
) -> BattleResult:
    p_hp, e_hp = player_hp, enemy_hp
    turns = 0
    while p_hp > 0 and e_hp > 0 and turns < max_turns:
        e_hp -= max(1, player_atk - enemy_def)
        if e_hp <= 0: break
        p_hp -= max(1, enemy_atk - player_def)
        turns += 1
    return BattleResult(
        player_survived=p_hp > 0,
        turns=turns,
        player_hp_remaining=p_hp,
        enemy_hp_remaining=max(0, e_hp),
    )

def check_balance(project: dict) -> list[str]:
    warnings = []
    # 플레이어 스탯 추정 (Class params 기반)
    player_hp = _estimate_player_hp(project)
    player_atk = _estimate_player_atk(project)

    for enemy in project.get("Enemies.json", [])[1:]:
        if enemy is None: continue
        result = simulate_battle(
            player_hp, player_atk, 5,
            enemy["params"][0], enemy["params"][2], enemy["params"][3],
        )
        if not result.player_survived:
            warnings.append(f"적 '{enemy['name']}': 플레이어가 1대1에서 지는 밸런스")
        if result.turns > 20:
            warnings.append(f"적 '{enemy['name']}': 전투가 너무 김 ({result.turns}턴)")
    return warnings
```

#### 완료 기준

- [ ] `simulate_battle()` 유닛 테스트 5개 통과
- [ ] 프론트엔드 생성 UI: `GeneratePage` 진입 → 폼 → 진행률 → 결과 표시
- [ ] WebSocket 연결 실패 시 폴링 fallback 동작 확인
- [ ] `npm run build` 에러 없음

---

## 스프린트 요약표

| Sprint | 주차 | 노드 | LLM? | 핵심 산출물 |
|--------|------|------|------|------------|
| 1 | 1 | asset_planner | 없음 | IdTable, SwitchTable |
| 2 | 2 | game_designer + asset_generator | 있음 | Actors/Skills/Enemies JSON |
| 3 | 3 | integrator + validator | 없음 | 완전한 에셋 파이프라인 |
| 4 | 4 | API + WebSocket + DB | 없음 | HTTP 202, WS 스트리밍 |
| 5 | 5 | dungeon/town generator | 없음 | 연결된 타일 배열 |
| 6 | 6 | map_designer + 맵 통합 | 있음 | Map001~003.json |
| 7 | 7 | event_compiler | 없음 | DSL → 커맨드 코드 |
| 8 | 8 | event_planner + workflow | 있음 | 플레이 가능한 게임 |
| 9 | 9 | balance + frontend | 없음 | 완성 UI + 밸런스 검증 |

---

## 병렬 작업 가능 영역

스프린트 내에서 다음은 동시에 진행 가능:

- Sprint 5~6: 맵 생성기 구현 ↔ API 안정화 (Sprint 4 follow-up)
- Sprint 7: DSL 컴파일러 ↔ 프론트엔드 Redux 슬라이스 초안
- Sprint 9: balance.py ↔ GenerationProgress 컴포넌트

---

## Definition of Done (공통)

모든 스프린트는 다음을 만족해야 완료:

1. `uv run pytest agent/tests/generation/ -v --tb=short` 새 테스트 전부 통과
2. `uv run ruff check agent/generation/` 에러 없음
3. 해당 스프린트 노드의 `run_*()` 함수가 `GenerationState` → `dict` 시그니처 준수
4. 스킵 패턴 동작: `completed_phases`에 이미 포함된 단계는 재실행 없음
5. 진행률 `publish_progress()` 호출로 WebSocket에 발행됨
