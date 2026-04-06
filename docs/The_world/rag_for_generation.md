# Full Generation에서 RAG 활용 전략

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 현황

프로젝트에는 이미 `agent/rag/knowledge_retriever.py`의 `KnowledgeRetriever`가 있다.
이 RAG는 현재 **Incremental Edit 파이프라인**에서 RPG Maker MZ 스키마 참조 용도로만 사용된다.

Full Generation 파이프라인에서도 이 RAG를 활용할 수 있다.
단, 모든 노드에 RAG를 넣는 것은 **컨텍스트 낭비**이므로 선택적으로 사용한다.

---

## RAG 지식 베이스 내용

```
agent/rag/data/
├── rpgmaker-mz-data-schema.md   # 전체 JSON 필드 정의 (실제 게임 데이터 기반)
└── rpgmaker-mz-data-schema2.md  # 추가 스키마 (CommonEvents, Animations 등)
```

`knowledge_retriever.retrieve_knowledge(query, k=3)` 호출 시:
- 쿼리를 Upstage 임베딩으로 벡터화
- SQLite3 기반 벡터스토어에서 유사도 상위 k개 섹션 반환
- 반환값: 마크다운 형식의 스키마 설명 문자열

---

## 노드별 RAG 사용 여부 결정

| 노드 | RAG? | 이유 |
|------|------|------|
| A. game_designer | ❌ | 창의적 기획 단계 — 스키마 지식 불필요 |
| B. asset_planner | ❌ | LLM 없음, 완전 알고리즘 |
| C. asset_generator | ✅ **선택적** | damage.formula 구문, params 배열 구조 확인 |
| D. map_designer | ❌ | MapSpec 생성 시 RPG Maker 내부 필드 불필요 |
| E. tile_generator | ❌ | LLM 없음, 완전 알고리즘 |
| F. event_planner | ✅ **선택적** | 이벤트 커맨드 코드 참조 (101, 201, 301 등) |
| G. event_compiler | ❌ | LLM 없음, DSL → JSON 변환 |
| H. integrator | ❌ | LLM 없음 |
| I. validator | ❌ | LLM 없음 |

---

## asset_generator에서 RAG 활용

### 어떤 쿼리를 사용하나

```python
RAG_QUERIES_BY_ASSET: dict[str, str | None] = {
    "actors":   None,         # 필드 단순, RAG 불필요
    "classes":  "Classes.json params 배열 구조 expParams",
    "skills":   "Skills.json damage formula scope occasion",
    "items":    "Items.json effects code 힐 상태이상",
    "weapons":  None,         # 필드 단순
    "armors":   None,         # 필드 단순
    "enemies":  "Enemies.json params dropItems actions conditionType",
    "troops":   None,         # 알고리즘 생성, LLM 없음
}
```

### 구현 패턴

```python
from agent.rag.knowledge_retriever import knowledge_retriever

async def _generate_asset(
    asset_type: str,
    spec: GameSpec,
    id_table: IdTable,
    already_generated: dict,
) -> list[dict]:
    # RAG 컨텍스트 준비
    rag_query = RAG_QUERIES_BY_ASSET.get(asset_type)
    rag_context = ""
    if rag_query:
        rag_context = knowledge_retriever.retrieve_knowledge(rag_query, k=2)
        # k=2: 컨텍스트를 최소화 (k=3은 토큰 낭비 위험)

    messages = build_asset_messages(
        asset_type=asset_type,
        spec=spec,
        id_table=id_table,
        already_generated=already_generated,
        rag_context=rag_context,  # 프롬프트에 선택적 주입
    )
    schema = ASSET_OUTPUT_SCHEMAS[asset_type]
    result = cast(schema, await invoke_with_retry(messages, schema))
    return [item.model_dump() for item in result.items]
```

### 프롬프트 주입 위치

```python
def build_asset_messages(
    asset_type: str,
    spec: GameSpec,
    id_table: IdTable,
    already_generated: dict,
    rag_context: str = "",
) -> list[BaseMessage]:
    system_parts = [BASE_ASSET_SYSTEM_PROMPT]
    # RAG 컨텍스트가 있으면 시스템 프롬프트 끝에 추가
    if rag_context:
        system_parts.append(
            f"\n\n## RPG Maker MZ 기술 참조\n{rag_context}\n\n"
            "위 참조 내용을 바탕으로 정확한 필드 구조를 사용하세요."
        )
    return [
        SystemMessage(content="\n".join(system_parts)),
        HumanMessage(content=build_asset_user_prompt(asset_type, spec, id_table)),
    ]
```

---

## event_planner에서 RAG 활용

이벤트 기획자는 RPG Maker MZ 커맨드 코드를 직접 YAML DSL로 기술하지 않지만,
DSL 타입명과 커맨드 코드의 대응 관계를 LLM이 알아야 정확한 DSL을 생성할 수 있다.

### 어떤 쿼리를 사용하나

```python
EVENT_PLANNER_RAG_QUERY = "MapXXX.json 이벤트 list 커맨드 code 101 201 301 401"
```

### 구현 패턴

```python
async def _plan_single_map(
    spec: MapSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
) -> list:
    # 맵 타입에 따라 이벤트 커맨드 코드 참조가 필요한지 판단
    # boss/dungeon: 전투 이벤트 커맨드 중요 → RAG 활용
    # town: NPC 대화 중심 → RAG 선택적
    rag_context = ""
    if spec.type in ("dungeon", "boss"):
        rag_context = knowledge_retriever.retrieve_knowledge(
            "Map 이벤트 battle processing troop switch", k=2
        )

    messages = build_event_planner_messages(spec, id_table, switch_table, connection_info, rag_context)
    # event_planner는 구조화 출력 미사용 (자유 텍스트 + YAML)
    raw: str = cast(str, await invoke_llm(messages))
    ...
```

---

## RAG 비활성화 옵션

RAG 호출은 SQLite 벡터 검색 + Upstage 임베딩 API 호출을 포함한다.
테스트 환경이나 오프라인 실행에서는 RAG를 비활성화할 수 있어야 한다.

```python
# agent/generation/config.py
class GenerationConfig(BaseSettings):
    GENERATION_USE_RAG: bool = True  # False → RAG 완전 비활성화
```

```python
# _generate_asset() 내부
if rag_query and generation_config.GENERATION_USE_RAG:
    rag_context = knowledge_retriever.retrieve_knowledge(rag_query, k=2)
```

테스트 픽스처:
```python
@pytest.fixture
def no_rag(monkeypatch):
    monkeypatch.setenv("GENERATION_USE_RAG", "false")
```

---

## RAG vs 하드코딩 프롬프트 트레이드오프

Full Generation에서는 **하드코딩 프롬프트**를 선호하는 경우가 많다.

| 방식 | 장점 | 단점 |
|------|------|------|
| RAG (동적 검색) | 스키마 변경 시 자동 반영 | 추가 API 호출, 컨텍스트 소비, 검색 실패 위험 |
| 하드코딩 프롬프트 | 예측 가능, 빠름, 오프라인 가능 | 스키마 변경 시 수동 업데이트 필요 |

**결론**: 정적이고 잘 알려진 규칙(damage.formula 구문, scope 값 범위)은
프롬프트에 하드코딩한다. RAG는 **복잡하거나 자주 변경되는 규칙**에만 사용한다.

현재 RPG Maker MZ 스키마는 고정되어 있으므로, Full Generation에서 RAG는
`Optional`이다 — 없어도 작동하지만, 있으면 LLM 오류율을 낮출 수 있다.

---

## 컨텍스트 예산 영향

RAG k=2 반환 시 예상 토큰:
- 섹션 1개 평균 ~200 토큰
- k=2 → ~400 토큰 추가

```
asset_generator (skills without RAG):  ~1,200 토큰
asset_generator (skills with RAG):     ~1,600 토큰 (+400)
event_planner (dungeon, without RAG):  ~1,300 토큰
event_planner (dungeon, with RAG):     ~1,700 토큰 (+400)
```

Total 추가 토큰 (RAG 활성 시): ~1,200 토큰/게임
Solar Pro 2 가격 기준 증가분: < $0.002/게임 — 무시 가능한 수준.

---

## 초기화 주의사항

`knowledge_retriever`는 싱글톤이며, 첫 호출 시 자동으로 인덱싱한다.
Full Generation이 처음 실행될 때 인덱싱이 발생하면 수 초의 지연이 생긴다.

**대응**: 애플리케이션 시작 시 미리 인덱싱:
```python
# app/backend/main.py (lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 RAG 인덱싱 (없으면 자동 처리됨)
    from agent.rag.knowledge_retriever import knowledge_retriever
    if generation_config.GENERATION_USE_RAG:
        knowledge_retriever.retrieve_knowledge("RPG Maker MZ", k=1)  # warm-up
    yield
```

또는 별도 startup 이벤트로 처리:
```python
@app.on_event("startup")
async def warmup_rag():
    if settings.GENERATION_USE_RAG:
        knowledge_retriever.retrieve_knowledge("actors classes", k=1)
```
