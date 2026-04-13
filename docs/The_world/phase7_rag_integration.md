# Phase 7 — RAG 통합

> 상태: 미구현
> 우선순위: **중간** — 게임 품질 향상, 없어도 동작은 함

---

## 목표

RPG Maker MZ 도메인 지식(타일셋, 커맨드, 에셋 제약 등)을 RAG로 LLM에 주입하여
게임 생성 품질을 높인다.

---

## 현재 상태

- `agent/rag/knowledge_retriever.py` — `KnowledgeRetriever` 클래스 존재
  - `retrieve_knowledge(query: str, k: int = 3) -> str` (동기 메서드, 문자열 반환)
  - 모듈 레벨 인스턴스: `knowledge_retriever = KnowledgeRetriever()`
  - RAG 데이터: `agent/rag/data/rpgmaker-mz-data-schema.md`, `rpgmaker-mz-data-schema2.md`
- Full Generation 노드에서 RAG 미사용 — 순수 LLM 프롬프트 의존

---

## 적용 범위 (canonical: `rag_for_generation.md`)

| 노드 | RAG 사용 여부 | 이유 |
|------|-------------|------|
| A game_designer | ❌ 불필요 | 창의적 생성, 제약 없음 |
| C asset_generator | ⚠️ 선택적 | RPG Maker 필드명 검증용 |
| D map_designer | ❌ 불필요 | 맵 설계는 창의적 |
| F event_planner | ✅ **필요** | 커맨드 코드, DSL 예시 주입 |

---

## 구현 대상

### `agent/generation/rag_context.py` (신규)

```python
"""이벤트 기획자 프롬프트용 RAG 컨텍스트 조회."""
from agent.rag.knowledge_retriever import knowledge_retriever


def get_event_planner_context(map_type: str) -> str:
    """이벤트 기획자 프롬프트에 주입할 RAG 컨텍스트 반환."""
    query = f"RPG Maker MZ {map_type} map events DSL examples"
    return knowledge_retriever.retrieve_knowledge(query, k=3)
```

> `retrieve_knowledge()`는 동기 함수이며 `str`을 반환한다.
> `retriever.ainvoke()` 같은 메서드는 존재하지 않으므로 사용 금지.

### `agent/generation/prompts/event_planner_prompt.py` 수정

`build_event_planner_prompt`에 `rag_context` 파라미터 추가:

```python
# 현재 시그니처 (수정 전)
def build_event_planner_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
) -> list[BaseMessage]:

# 수정 후
def build_event_planner_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    connection_info: MapConnectionInfo,
    rag_context: str = "",          # ← 추가
) -> list[BaseMessage]:
    # 프롬프트 내 rag_context 주입 (빈 문자열이면 블록 생략)
```

### `agent/generation/nodes/event_planner.py` 수정

```python
from agent.generation.rag_context import get_event_planner_context

# event_planner_node 내부
rag_context = get_event_planner_context(spec.map_type)
prompt = build_event_planner_prompt(
    map_spec=spec,
    game_spec=game_spec,
    id_table=id_table,
    switch_table=switch_table,
    connection_info=connection_info,
    rag_context=rag_context,       # ← 추가
)
```

### 인덱싱 대상 문서

현재 `KnowledgeRetriever`는 다음 두 파일만 인덱싱:
- `agent/rag/data/rpgmaker-mz-data-schema.md`
- `agent/rag/data/rpgmaker-mz-data-schema2.md`

추가 인덱싱 고려 대상 (필요 시 `source_files`에 추가):
- `docs/The_world/completed/dsl_specification.md`
- `docs/The_world/completed/event_command_complete.md`
- `docs/The_world/completed/npc_conditional_and_shop.md`

---

## 완료 기준

- [ ] `get_event_planner_context()` 단위 테스트 (mock vector_store)
- [ ] `build_event_planner_prompt` `rag_context` 파라미터 추가 + 프롬프트 내 주입
- [ ] F 노드 평균 재시도 횟수 감소 확인 (수동 비교)
- [ ] RAG 없는 경우 vs 있는 경우 이벤트 품질 비교 (수동)
