# Phase 8 — RAG 통합

> 상태: 미구현
> 우선순위: **중간** — 게임 품질 향상, 없어도 동작은 함

---

## 목표

RPG Maker MZ 도메인 지식(타일셋, 커맨드, 에셋 제약 등)을 RAG로 LLM에 주입하여
게임 생성 품질을 높인다.

---

## 현재 상태

- `agent/rag/` 디렉토리 존재 (기존 Incremental Edit용)
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
async def get_event_planner_context(map_type: str) -> str:
    """이벤트 기획자 프롬프트에 주입할 RAG 컨텍스트."""
    query = f"RPG Maker MZ {map_type} map events DSL examples"
    docs = await retriever.ainvoke(query)
    return "\n".join(d.page_content for d in docs[:3])
```

### `agent/generation/nodes/event_planner.py` 수정

```python
# 기존: 프롬프트만 사용
# 변경: RAG 컨텍스트 주입
rag_context = await get_event_planner_context(spec.map_type)
prompt = build_event_planner_prompt(..., rag_context=rag_context)
```

### 인덱싱 대상 문서

- `docs/The_world/completed/dsl_specification.md`
- `docs/The_world/completed/event_command_complete.md`
- `docs/The_world/completed/npc_conditional_and_shop.md`
- `docs/The_world/completed/game_ending_design.md`
- `docs/rpgmaker/` 디렉토리

---

## 완료 기준

- [ ] RAG 없는 경우 vs 있는 경우 이벤트 품질 비교 (수동)
- [ ] `get_event_planner_context()` 단위 테스트
- [ ] F 노드 평균 재시도 횟수 감소 확인
