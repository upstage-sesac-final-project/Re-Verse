# Full Generation 워크플로우 구현 상세

> LangGraph 노드 연결, 조건부 엣지, 체크포인트, 진행 상황 발행
> 위치: `agent/generation/workflow.py`

---

## 전체 그래프 구조

```python
# agent/generation/workflow.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.generation.state import GenerationState
from agent.generation.nodes.game_designer       import game_designer
from agent.generation.nodes.asset_planner       import asset_planner
from agent.generation.nodes.asset_generator     import asset_generator
from agent.generation.nodes.map_designer        import map_designer
from agent.generation.nodes.tile_generator      import tile_generator
from agent.generation.nodes.event_planner       import event_planner
from agent.generation.nodes.event_compiler_node import event_compiler_node
from agent.generation.nodes.integrator          import integrator
from agent.generation.nodes.generation_validator import generation_validator
from agent.generation.nodes.generation_responder import generation_responder


def build_generation_graph() -> StateGraph:
    graph = StateGraph(GenerationState)

    # ── 노드 등록 ─────────────────────────────────────────────────
    graph.add_node("game_designer",    game_designer)
    graph.add_node("asset_planner",    asset_planner)
    graph.add_node("asset_generator",  asset_generator)
    graph.add_node("map_designer",     map_designer)
    graph.add_node("tile_generator",   tile_generator)
    graph.add_node("event_planner",    event_planner)
    graph.add_node("event_compiler",   event_compiler_node)
    graph.add_node("integrator",       integrator)
    graph.add_node("validator",        generation_validator)
    graph.add_node("responder",        generation_responder)

    # ── 진입점 ────────────────────────────────────────────────────
    graph.set_entry_point("game_designer")

    # ── 순차 엣지 ─────────────────────────────────────────────────
    graph.add_edge("game_designer",   "asset_planner")
    graph.add_edge("asset_planner",   "asset_generator")

    # asset_generator 완료 후 → 맵이 필요한지 판단
    graph.add_conditional_edges(
        "asset_generator",
        _route_after_assets,
        {
            "map_phase":    "map_designer",     # Phase 3+
            "skip_to_integrate": "integrator",  # Phase 2 (맵 생성 스킵)
        },
    )

    graph.add_edge("map_designer",  "tile_generator")
    graph.add_edge("tile_generator", "event_planner")
    graph.add_edge("event_planner", "event_compiler")
    graph.add_edge("event_compiler", "integrator")
    graph.add_edge("integrator",    "validator")

    # validator 완료 후 → 재시도 여부 판단
    graph.add_conditional_edges(
        "validator",
        _route_after_validation,
        {
            "retry_events": "event_planner",    # 이벤트 오류(R2) 있을 때
            "retry_assets": "asset_generator",  # 에셋 오류(R1) 있을 때
            "retry_maps":   "map_designer",     # 맵 오류(R4/R16) 있을 때
            "respond":      "responder",         # 성공 또는 재시도 한계 도달
        },
    )

    graph.add_edge("responder", END)

    return graph


# ── 컴파일 (체크포인트 포함) ──────────────────────────────────────────
_checkpointer = MemorySaver()

generation_graph = build_generation_graph().compile(
    checkpointer=_checkpointer,
)
```

---

## 조건부 엣지 함수

### `_route_after_assets`

```python
def _route_after_assets(state: GenerationState) -> str:
    """
    에셋 생성 완료 후 맵 생성 단계로 갈지, 통합으로 바로 갈지 결정.

    phase_limit 옵션이 "assets"면 맵 생성 건너뜀.
    나중에 "맵 추가해줘" 같은 부분 재생성 시에도 사용.
    """
    if state.get("phase_limit") == "assets":
        return "skip_to_integrate"
    if state.get("error_phase") in ("asset_generator",) and state.get("retry_count", 0) >= 3:
        return "skip_to_integrate"
    return "map_phase"
```

### `_route_after_validation`

```python
# 에러 태그 → 재시도 대상 매핑
_ERROR_TAG_ROUTING = {
    "[R1]":  "retry_assets",   # ID 참조 오류 → 에셋 재생성
    "[R2]":  "retry_events",   # DSL 파싱 실패 → 이벤트 재생성
    "[R4]":  "retry_maps",     # 맵 좌표 연결 불일치 → 맵 재생성
    "[R15]": "retry_maps",     # 타일셋 ID 불일치 → 맵 재생성
    "[R16]": "retry_maps",     # 시작 좌표 벽 타일 (P0) → 맵 재생성
    "[R22]": "retry_events",   # 이벤트 좌표 중복 → 이벤트 재생성
}

def _route_after_validation(state: GenerationState) -> str:
    """
    검증 결과에 따라 재시도 대상 노드를 결정.

    재시도 우선순위: retry_maps > retry_assets > retry_events
    (맵이 변경되면 이벤트도 재생성 필요하므로 맵 우선)
    """
    errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)
    MAX_RETRY = 2

    if not errors or retry_count >= MAX_RETRY:
        return "respond"

    # 에러 태그별 재시도 대상 수집
    targets = set()
    for e in errors:
        for tag, route in _ERROR_TAG_ROUTING.items():
            if e.startswith(tag):
                targets.add(route)
                break

    if not targets:
        # 매핑되지 않은 에러 (밸런스 경고 등) → 응답 생성
        return "respond"

    # 우선순위: 맵 > 에셋 > 이벤트
    if "retry_maps" in targets:
        return "retry_maps"
    if "retry_assets" in targets:
        return "retry_assets"
    return "retry_events"
```

---

## 상태(State) 전환 흐름

```
초기 상태:
  user_input: "중세 판타지 게임 만들어줘"
  game_id:    "game_003"
  generation_id: "gen_abc123"
  completed_phases: []

game_designer 완료 후:
  game_spec: { title: "기사와 마왕", maps: [...], ... }
  completed_phases: ["spec"]

asset_planner 완료 후:
  id_table:     { actors: {"해럴드": 1}, ... }
  switch_table: { switches: {"boss_defeated": 1}, ... }
  completed_phases: ["spec", "planning"]

asset_generator 완료 후:
  generated_assets: {
    "Actors.json": [...],
    "Skills.json": [...],
    ...
  }
  completed_phases: ["spec", "planning", "assets"]

tile_generator 완료 후:
  map_tiles:       { 1: [2816, 2816, ...], 2: [...] }
  connection_info: { 1: MapConnectionInfo(...), 2: ... }
  completed_phases: [..., "maps"]

event_compiler 완료 후:
  compiled_events: {
    1: [{"id": 1, "pages": [{"list": [...]}]}],
    2: [...]
  }
  completed_phases: [..., "events"]

validator 완료 후:
  validation_passed: True
  validation_errors: []
  validation_warnings: ["슬라임 ATK 약간 높음"]
  completed_phases: [..., "validation"]
```

---

## 체크포인트 & 재시작

### LangGraph MemorySaver 활용

```python
async def run_generation_workflow(
    user_input: str,
    game_id: str,
    generation_id: str,
    phase_limit: str | None = None,
    resume_from_checkpoint: bool = False,
) -> GenerationState:
    """
    generation_id를 thread_id로 사용해서 체크포인트를 저장/복원.
    resume_from_checkpoint=True면 이전 상태에서 이어서 실행.
    """
    config = {"configurable": {"thread_id": generation_id}}

    if resume_from_checkpoint:
        # LangGraph가 저장된 체크포인트에서 자동으로 이어받음
        # (completed_phases가 이미 채워진 상태에서 시작)
        initial_state = None  # 체크포인트에서 로드
    else:
        initial_state = GenerationState(
            user_input=user_input,
            game_id=game_id,
            generation_id=generation_id,
            phase_limit=phase_limit,
            completed_phases=[],
            retry_count=0,
        )

    final_state = await generation_graph.ainvoke(
        initial_state,
        config=config,
    )
    return final_state
```

### 노드 내부에서 체크포인트 저장 시점

LangGraph는 노드 완료 시 자동으로 상태를 체크포인트에 저장한다.
별도 코드 없이 각 노드 함수가 반환한 `state`가 자동 보존된다.

```python
# asset_generator.py
async def asset_generator(state: GenerationState) -> GenerationState:
    # ... 생성 로직 ...

    # 이 return 값이 LangGraph 체크포인트로 자동 저장됨
    return {
        **state,
        "generated_assets": assets,
        "completed_phases": [*state.get("completed_phases", []), "assets"],
    }
```

재실행 시 `completed_phases`를 보고 건너뛸 수 있도록:

```python
async def asset_generator(state: GenerationState) -> GenerationState:
    if "assets" in state.get("completed_phases", []):
        return state  # 이미 완료됨 → 건너뜀

    # ... 실제 생성 로직 ...
```

---

## 진행 상황 발행 (WebSocket 연동)

각 노드는 `publish_progress()`를 호출해서 WebSocket 클라이언트에 실시간 업데이트를 전달한다.

### 표준 패턴

```python
# agent/generation/nodes/asset_generator.py
from agent.generation.progress import publish_progress

async def asset_generator(state: GenerationState) -> GenerationState:
    gen_id = state["generation_id"]

    await publish_progress(gen_id, {
        "type": "progress",
        "phase": "asset_generation",
        "progress": 15,
        "message": "캐릭터·스킬·아이템 생성 시작...",
    })

    # 병렬 생성
    results = await asyncio.gather(
        generate_classes(spec, id_table),
        generate_skills(spec, id_table),
        generate_items(spec, id_table),
        generate_enemies(spec, id_table),
        return_exceptions=True,
    )

    await publish_progress(gen_id, {
        "type": "progress",
        "phase": "asset_generation",
        "progress": 45,
        "message": f"기본 에셋 완료, 캐릭터 생성 중...",
    })

    assets["Actors.json"] = await generate_actors(...)

    await publish_progress(gen_id, {
        "type": "phase_complete",
        "phase": "asset_generation",
        "summary": f"캐릭터 {len(spec.characters)}명, 스킬 {skill_count}개, "
                   f"아이템 {item_count}개 생성 완료",
        "duration_seconds": elapsed,
    })

    return {**state, "generated_assets": assets, ...}
```

### 노드별 진행률 배분

| 노드 | 시작 % | 끝 % | generation_api.md phase 값 |
|------|--------|------|--------------------------|
| game_designer | 0 | 10 | `spec` |
| asset_planner | 10 | 15 | `planning` |
| asset_generator | 15 | 50 | `asset_generation` |
| map_designer | 50 | 60 | `map_design` |
| tile_generator | 60 | 70 | `tile_generation` |
| event_planner | 70 | 85 | `event_planning` |
| event_compiler | 85 | 90 | `event_compilation` |
| integrator | 90 | 95 | `integration` |
| validator | 95 | 98 | `validation` |
| responder | 98 | 100 | — (내부 전용) |

> **canonical**: `generation_api.md`의 Phase 이름 및 진행률 매핑 테이블. 구현 시 위 값 사용.

---

## 오류 전파 & 복구

### 노드에서 오류 발생 시

```python
async def map_designer(state: GenerationState) -> GenerationState:
    gen_id = state["generation_id"]
    try:
        map_specs = await _call_llm_for_maps(state)
        return {**state, "map_specs": map_specs}

    except LLMTimeoutError as e:
        # 재시도 가능한 오류 → 상태에 기록 후 예외 전파
        await publish_progress(gen_id, {
            "type": "error",
            "phase": "map_design",
            "message": "맵 설계 타임아웃, 재시도 중...",
            "can_retry": True,
        })
        raise  # LangGraph가 잡아서 체크포인트 저장 후 중단

    except Exception as e:
        await publish_progress(gen_id, {
            "type": "error",
            "phase": "map_design",
            "message": f"맵 설계 실패: {e}",
            "can_retry": False,
        })
        raise
```

### 재시도 카운터 관리

```python
def _route_after_validation(state: GenerationState) -> str:
    retry_count = state.get("retry_count", 0)
    if retry_count >= 2:
        return "respond"  # 더 이상 재시도 안 함
    ...


# validator가 재시도 경로를 선택하면 retry_count 증가
async def generation_validator(state: GenerationState) -> GenerationState:
    errors = run_all_checks(state)
    return {
        **state,
        "validation_errors": errors,
        "validation_passed": not errors,
        "retry_count": state.get("retry_count", 0) + (1 if errors else 0),
    }
```

---

## 부분 재생성 진입점

```python
async def run_partial_regeneration(
    generation_id: str,
    scope: Literal["assets", "maps", "events"],
    target_map_id: int | None = None,
) -> GenerationState:
    """
    기존 체크포인트를 로드하고 특정 Phase부터 재실행.
    """
    config = {"configurable": {"thread_id": generation_id}}

    # 현재 체크포인트 상태 로드
    checkpoint = await generation_graph.aget_state(config)
    current_state = checkpoint.values

    # 재생성 범위에 따라 completed_phases 조정
    phase_cutoff = {
        "assets": ["spec", "planning"],           # assets 이후 재실행
        "maps":   ["spec", "planning", "assets"], # maps 이후 재실행
        "events": ["spec", "planning", "assets", "maps"],  # events만 재실행
    }
    current_state["completed_phases"] = phase_cutoff[scope]

    if target_map_id is not None:
        current_state["regen_target_map_id"] = target_map_id

    final_state = await generation_graph.ainvoke(current_state, config=config)
    return final_state
```

---

## 독립 실행 (FastAPI 백그라운드 태스크)

```python
# app/backend/api/v1/generation.py

async def run_generation_in_background(
    generation_id: str,
    prompt: str,
    project_id: int,
    options: dict,
    db: AsyncSession,
):
    """BackgroundTasks에서 호출되는 실제 실행 함수."""
    try:
        await db.execute(
            update(Generation)
            .where(Generation.id == generation_id)
            .values(status="in_progress", current_phase="spec")
        )
        await db.commit()

        final_state = await run_generation_workflow(
            user_input=prompt,
            game_id=str(project_id),
            generation_id=generation_id,
        )

        # 완료 처리
        await db.execute(
            update(Generation)
            .where(Generation.id == generation_id)
            .values(
                status="completed",
                progress=100,
                result_summary=build_summary(final_state),
                completed_at=datetime.utcnow(),
            )
        )
        await db.commit()

    except Exception as e:
        logger.error("generation %s 실패: %s", generation_id, e, exc_info=True)
        await db.execute(
            update(Generation)
            .where(Generation.id == generation_id)
            .values(
                status="failed",
                error_message=str(e),
            )
        )
        await db.commit()

        await publish_progress(generation_id, {
            "type": "error",
            "message": "게임 생성 중 오류가 발생했습니다.",
            "can_retry": True,
        })
```

---

## 그래프 시각화 (디버깅용)

```python
# 개발 시 그래프 구조 확인
if __name__ == "__main__":
    graph = build_generation_graph()
    compiled = graph.compile()
    print(compiled.get_graph().draw_ascii())

# 예상 출력:
#
# game_designer
#      │
# asset_planner
#      │
# asset_generator
#    ├──(assets only)──► integrator
#    └──(full)──────────► map_designer
#                              │
#                        tile_generator
#                              │
#                        event_planner
#                              │
#                        event_compiler
#                              │
#                          integrator
#                              │
#                           validator
#                    ┌─────────┼──────────┐
#              retry_maps  retry_assets  retry_events  respond
#                    │         │              │            │
#              map_designer asset_generator event_planner responder
#                                                           │
#                                                         [END]
```

---

## 노드 실행 시간 목표

| 노드 | 목표 시간 | 병렬 여부 |
|------|---------|---------|
| game_designer | ≤ 5초 | 단독 |
| asset_planner | ≤ 0.5초 | 단독 (코드) |
| asset_generator | ≤ 12초 | **5~6개 병렬** |
| map_designer | ≤ 4초 | 단독 |
| tile_generator | ≤ 1초 | **3개 병렬** |
| event_planner | ≤ 12초 | **맵당 병렬** |
| event_compiler | ≤ 0.5초 | 코드 |
| integrator | ≤ 1초 | 코드 |
| validator | ≤ 0.5초 | 코드 |
| responder | ≤ 3초 | 단독 |
| **합계** | **≤ 40초** | |

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- 에셋 생성 상세: `docs/The_world/asset_generation.md`
- API 설계: `docs/The_world/generation_api.md`
- 리스크 (R6: 복구): `docs/The_world/risks_and_mitigations.md#r6`
