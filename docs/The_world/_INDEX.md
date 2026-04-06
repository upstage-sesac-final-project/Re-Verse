# The World — 문서 인덱스 및 검증 요약

> 최종 업데이트: 2026-04-06 (ralph-loop Iter 8)
> 상태: **설계 문서 전체 (미구현)** — 구현 목표: `agent/generation/` 모듈

---

## 1. 전체 맥락

이 폴더의 문서는 **Full Generation** 기능 설계서다.
"중세 판타지 게임 만들어줘" 한 문장으로 5~10분 플레이 가능한 RPG Maker MZ 프로젝트 자동 생성.

### 현재 구현된 것
- `agent/graph/` — Incremental Edit 파이프라인 (router → definition → planner → executor → validator → synthesizer)
- `agent/schemas/` — RPG Maker MZ JSON 스키마 (Pydantic)
- `agent/rag/` — RAG 파이프라인
- `app/backend/` — FastAPI REST API

### 미구현 (이 문서들이 설계)
- `agent/generation/` 디렉터리 전체
- `app/backend/api/v1/endpoints/generation.py`
- DB의 `generations` 테이블

---

## 2. 문서 목록 (카테고리별)

### 2-A. 아키텍처 / 마스터 플랜

| 파일 | 요약 |
|------|------|
| `full_generation_plan.md` | **마스터 인덱스**. 노드 A~I 정의, GenerationState, 에셋 규모, 토큰/시간 예산 |
| `sprint_plan.md` | 9스프린트 구현 일정 (Phase 2~5). 코드 예시 포함 |
| `workflow_implementation.md` | LangGraph 10노드 상세 (체크포인트·재시작·부분 재생성) |
| `generation_api.md` | REST + WebSocket API 설계 (엔드포인트, DB 스키마, 프론트엔드 훅) |
| `integration_with_existing.md` | 기존 Incremental Edit와의 통합 전략, 코드 재사용 맵 |

### 2-B. 에셋 생성 (Phase 2)

| 파일 | 요약 |
|------|------|
| `asset_generation.md` | B·C 노드. 전체 에셋 타입 생성 상세 (Pydantic, LLM 프롬프트, 병렬 실행) |
| `classes_params_generation.md` | Classes.json 8×99 params — LLM+알고리즘 하이브리드 |
| `balance_and_economy.md` | 밸런스 공식, 적 티어별 스탯, 경제 시스템, 검증 함수 |
| `llm_structured_output.md` | `invoke_llm(structured_output=Schema)` 패턴, Solar Pro 2 제약, 재시도 |
| `rag_for_generation.md` | Full Generation RAG 사용 범위 (C·F 노드만 선택적) |
| `prompt_engineering.md` | A·F 노드 프롬프트 설계, 토큰 예산, 공통 유틸리티 |
| `rpgmaker_constraints.md` | RPG Maker MZ JSON 제약 (index-0 null, ID 매핑, `ensure_null_at_index_0`) |
| `rpgmaker_default_assets.md` | 기본 리소스 파일명 목록, `MAP_SIZE_BY_TYPE` |

### 2-C. 맵 생성 (Phase 3)

| 파일 | 요약 |
|------|------|
| `map_generation.md` | D·E 노드. MapSpec 구조, 6레이어 타일 배열, 마을/던전 생성 알고리즘 |
| `map_connectivity_detail.md` | 맵 간 양방향 출구 보장, 그래프 연결성 검증 (R21·R22) |
| `switch_allocation.md` | SwitchTable 2단계 설계 (사전 할당 + 동적 확장), 충돌 방지 |

### 2-D. 이벤트 생성 (Phase 4)

| 파일 | 요약 |
|------|------|
| `dsl_specification.md` | DSL 명세 (F 노드 출력 언어). `condition`/`sign`은 ⚠️ Phase 5 미구현 |
| `event_command_complete.md` | RPG Maker MZ 커맨드 완전 레퍼런스 + dsl_specification 오류 수정표 |
| `npc_conditional_and_shop.md` | NPC 2-페이지 조건부 대화, 상점 컴파일러 상세 |
| `game_ending_design.md` | `EndingEvent` DSL 타입, Auto-Run 엔딩, `check_ending_reachable()` |

### 2-E. 조립 / 검증 / 응답

| 파일 | 요약 |
|------|------|
| `integrator_assembly.md` | H 노드. System.json·MapInfos.json·Troops.json·Map*.json 조립 상세 |
| `responder_node.md` | Responder 노드. 성공/부분 실패 메시지, WebSocket 100% 전송 |

### 2-F. 인프라 / 운영

| 파일 | 요약 |
|------|------|
| `deployment_and_ops.md` | BackgroundTasks→Celery+Redis, 비용 추적, 인시던트 대응, 환경변수 |
| `frontend_implementation.md` | Redux 슬라이스, WebSocket 미들웨어, 생성 진행 UI |
| `testing_strategy.md` | 노드별 단위·통합 테스트, CI 설정, 수동 체크리스트 |
| `data_migration.md` | 기존 RPG Maker MZ 프로젝트 임포트 설계 (우선순위 낮음) |

### 2-G. 리스크 관리

| 파일 | 요약 |
|------|------|
| `risks_and_mitigations.md` | R1~R10 (P0: ID 참조 오류, DSL 파싱 실패) |
| `additional_risks.md` | R11~R18 (P0: R16 시작 좌표 벽 타일, P1: R13 동시 쓰기, R15 타일셋 불일치) |

---

## 3. 핵심 아키텍처 요약

### 노드 흐름 (10 노드)

```
A. game_designer  →  B. asset_planner  →  C. asset_generator
                                                  ↓
D. map_designer   →  E. tile_generator  ←  (map_specs)
                                                  ↓
F. event_planner  →  G. event_compiler  ←  (tiles + map_specs)
                                                  ↓
                     H. integrator      ←  (assets + tiles + events)
                                                  ↓
                     I. validator  →(실패, retry<3)→ C or E or G
                              ↓ (통과 or 한계도달)
                     J. responder  →  END
```

> `full_generation_plan.md`는 A~I 9단계 표기, `workflow_implementation.md`는 10노드 분리.
> 실제 구현 시 10노드 (`workflow_implementation.md` 기준) 사용.

### GenerationState 핵심 필드 (canonical: `full_generation_plan.md`)

```python
class GenerationState(TypedDict):
    # 입력
    user_input: str;  game_id: str;  generation_id: str

    # B 노드 출력
    id_table: IdTable | None;  switch_table: SwitchTable | None
    generation_order: list[str];  phase_limit: str | None  # "assets"|"maps"|None

    # C 노드 출력 (A도 포함)
    game_spec: GameSpec | None;  generated_assets: dict[str, Any]

    # D+E 노드 출력
    map_specs: list[MapSpec];  map_tiles: dict[int, list[int]]  # flat 1D
    connection_info: dict[int, MapConnectionInfo]

    # F+G 노드 출력
    event_dsl: dict[int, list];  compiled_events: dict[int, list]

    # H 노드 출력
    final_project: dict[str, Any]

    # I 노드 출력
    validation_passed: bool;  validation_errors: list[str]
    validation_warnings: list[str];  retry_count: int

    # 체크포인트
    completed_phases: list[str];  error_phase: str | None;  error_message: str | None

    # J 노드 출력 (responder)
    final_message: str;  is_success: bool
```

### 에셋 규모 목표 / 시간 예산

| 에셋 | 수량 | 시간 | LLM 호출 |
|------|------|------|---------|
| Actor/Class | 2~4 | Phase 2: ~14초 (목표) | 4회 |
| Skill/Item/Weapon/Armor | 15~20종 | Phase 4: ~27초 (목표) / ≤40초 (상한) | 12회 |
| Enemy/Troop | 6~10종 | — | — |
| Map | 3~4개 | — | — |

### generation_validator 검증 함수 목록

| 함수 | 위치 문서 | 리스크 |
|------|---------|-------|
| `check_id_references()` | `risks_and_mitigations.md` | R1 |
| `check_null_at_index_0()` | `rpgmaker_constraints.md` | — |
| `check_array_lengths()` | `rpgmaker_constraints.md` | — |
| `check_start_position()` | `integrator_assembly.md` | R16 |
| `check_troop_positions()` | `additional_risks.md` | R17 |
| `check_map_id_consistency()` | `integrator_assembly.md` | R18 |
| `check_resource_filenames()` | `rpgmaker_default_assets.md` | R19 |
| `check_ending_reachable()` | `game_ending_design.md` | R23 |
| `check_balance()` | `risks_and_mitigations.md` | — |
| `check_event_coordinate_conflicts()` | `map_connectivity_detail.md` | R22 |
| `check_switch_semantic_conflicts()` | `switch_allocation.md` | R20 |

---

## 4. 발견 오류 전체 현황

### 수정 완료 (총 15건)

| ID | 파일 | 내용 | Iter |
|----|------|------|------|
| E-1 | `dsl_specification.md` | 353/354 코드 오류 — 이미 수정되어 있었음 (확인만) | 1 |
| E-2 | `responder_node.md` | `map_tiles: list[list[int]]` → `list[int]` (flat 1D) | 1 |
| E-3 | `full_generation_plan.md` | `additional_risks.md` 범위 R11~R15 → R11~R18 | 2 |
| E-4 | `full_generation_plan.md` | GenerationState: `retry_count`, `is_success`, `final_message` 누락 | 2 |
| E-5 | `responder_node.md` | GenerationState "최종 필드"에 7개 필드 누락 | 2 |
| E-6a | `dsl_specification.md` | `compile()` match문 `"ending"` 케이스 없음 | 3 |
| E-6b | `dsl_specification.md` | `resolve_switch_id()` SwitchTable 직접 변경 (불변성 위반) | 3/4 |
| E-7 | `game_ending_design.md` | 테스트: `type="boss"` → `map_type="boss"` | 3 |
| E-8 | `integration_with_existing.md` | `solar_client.py` → `llm_client.py` (3곳) | 4 |
| E-9 | `classes_params_generation.md` | Warrior MAT Lv99 = 100 → 135 (balance 기준 135~225 미달) | 4 |
| E-10 | `full_generation_plan.md` | GenerationState `phase_limit` 필드 누락 | 4 |
| E-11 | `sprint_plan.md` | `DslEvent` union에 `EndingEvent` 누락 | 5 |
| E-12 | `dsl_specification.md` | `condition`/`sign` 타입 ⚠️ Phase 5 미구현 경고 추가 | 5 |
| E-13 | `generation_api.md` + `frontend_implementation.md` | `completed_with_warnings` 이벤트/타입/핸들러 누락 | 6 |
| E-14 | `full_generation_plan.md` | 폴더 구조에서 E(tile_generator.py), G(event_compiler_node.py), J(generation_responder.py) 3개 노드 파일 누락 | 8 |

### 설계 결정 필요 (총 4건)

| ID | 내용 | 권장 |
|----|------|------|
| D-1 | 두 종류의 `MapSpec` 이름 충돌 (`type` vs `map_type`, 단순 vs 상세) | GameSpec용은 `GameMapInfo`로 rename |
| D-2 | MapSpec `width`/`height` 필드 — LLM 생성 후 `MAP_SIZE_BY_TYPE`으로 덮어쓰기 이중적 | 2번 채택 (덮어쓰기) 명시 |
| D-3 | 노드 명칭 혼재 (A~I vs 영문 10노드 vs 한글) | `workflow_implementation.md` 영문 10노드 통일 |
| D-4 | `sprint_plan.md` DslEvent 모델 필드 (int ID) vs npc_conditional (str 이름) | str 이름 방식이 정설. sprint_plan은 구버전 |

### 경고 / 참고사항

| ID | 내용 |
|----|------|
| W-1 | `sprint_plan.md` invoke_llm 호출이 구버전 패턴 (`prompt, temperature=`). 실제 구현은 `llm_structured_output.md` 패턴 우선 |
| W-2 | 적 스탯 범위 미세 불일치 (`balance_and_economy.md` vs `asset_generation.md`). `asset_generation.md`를 canonical로 취급 권장 |
| W-3 | `generation_api.md` S3 버킷명/IAM 정책 미정의. 구현 전 확정 필요 |
| W-4 | `data_migration.md`는 Sprint Plan에 없음. 우선순위 낮음 — Phase 5 이후 |

---

## 5. 문서 간 의존 관계

```
full_generation_plan.md  ← 마스터 (GenerationState canonical 정의)
    ├── workflow_implementation.md  (10노드 그래프)
    ├── generation_api.md           (REST + WebSocket API)
    ├── sprint_plan.md              (구현 일정 + 코드 예시)
    ├── integration_with_existing.md
    │
    ├── [Phase 2]
    │   ├── asset_generation.md     ← canonical 에셋 스탯
    │   ├── classes_params_generation.md
    │   ├── balance_and_economy.md  ← 스탯 범위 참고
    │   ├── llm_structured_output.md ← invoke_llm 패턴 canonical
    │   ├── prompt_engineering.md
    │   ├── rpgmaker_constraints.md
    │   └── rpgmaker_default_assets.md
    │
    ├── [Phase 3]
    │   ├── map_generation.md       ← 상세 MapSpec canonical
    │   ├── map_connectivity_detail.md
    │   └── switch_allocation.md   ← SwitchTable immutable 패턴 canonical
    │
    ├── [Phase 4]
    │   ├── dsl_specification.md   ← EventCompiler 구현
    │   ├── event_command_complete.md  ← 커맨드 코드 canonical
    │   ├── npc_conditional_and_shop.md ← NpcEvent 필드 canonical
    │   └── game_ending_design.md  ← EndingEvent, DslEvent 유니온 최신
    │
    ├── [조립/마무리]
    │   ├── integrator_assembly.md ← R16/R18 validator 함수 위치
    │   └── responder_node.md
    │
    ├── [인프라]
    │   ├── deployment_and_ops.md  (환경변수: CHECKPOINT_BACKEND, GENERATION_TIMEOUT_SECONDS)
    │   ├── frontend_implementation.md
    │   ├── testing_strategy.md
    │   └── data_migration.md
    │
    └── [리스크]
        ├── risks_and_mitigations.md (R1~R10)
        └── additional_risks.md     (R11~R18)
```

---

## 6. 구현 체크리스트 (Phase 2 시작용)

```
[ ] agent/generation/state.py              — GenerationState TypedDict (canonical: full_generation_plan.md)
[ ] agent/generation/registry/id_table.py  — IdTable
[ ] agent/generation/registry/switch_table.py — SwitchTable (immutable, model_copy)
[ ] agent/generation/nodes/game_designer.py
[ ] agent/generation/nodes/asset_planner.py
[ ] agent/generation/nodes/asset_generator.py
[ ] agent/generation/nodes/integrator.py   (Phase 2: 에셋만)
[ ] agent/generation/nodes/generation_validator.py
[ ] agent/generation/nodes/generation_responder.py
[ ] agent/generation/progress.py           — publish_progress()
[ ] agent/generation/workflow.py           — LangGraph 그래프
[ ] app/backend/api/v1/endpoints/generation.py
[ ] app/backend/schemas/generation.py      — Pydantic 요청/응답
[ ] DB migration: generations 테이블
[ ] agent/graph/nodes/router.py            — 전체_게임_생성 인텐트 추가
```

### 구현 시 주의사항

1. **DslEvent 모델 기준**: `npc_conditional_and_shop.md` (str 이름 방식, alt_dialogue)
2. **invoke_llm 패턴 기준**: `llm_structured_output.md` (structured_output=Schema)
3. **MapSpec 구분**: GameSpec 내 단순 버전(`type`)과 D 노드 출력 상세 버전(`map_type`) 혼용 주의
4. **SwitchTable 불변성**: `model_copy()` + tuple 언패킹 (`table, id = table.allocate_switch(name)`)
5. **에셋 스탯 기준**: `asset_generation.md` (balance_and_economy.md보다 보수적, canonical)

---

## 7. 주요 환경변수 (deployment_and_ops.md 기준)

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `CHECKPOINT_BACKEND` | `memory` | `memory` \| `s3` — Phase 4+ S3로 전환 |
| `GENERATION_TIMEOUT_SECONDS` | `180` | 전체 생성 타임아웃 |
| `GENERATION_USE_RAG` | `true` | C·F 노드 RAG 활성화 |

---
