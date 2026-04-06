# The World — 문서 인덱스

> 최종 업데이트: 2026-04-06
> 상태: **Phase 2~5 구현 완료.** Phase 6+ 진행 예정.

---

## 1. 구현 현황

### 완료된 페이즈

| 페이즈 | 내용 | 핵심 파일 |
|--------|------|---------|
| Phase 2 | 에셋 생성 (A~C 노드 + API) | `agent/generation/nodes/`, `app/backend/api/v1/endpoints/generation.py` |
| Phase 3 | 맵 생성 (D~E 노드 + mapgen) | `agent/generation/mapgen/`, `nodes/map_designer.py`, `nodes/tile_generator.py` |
| Phase 4 | 이벤트 생성 (F~J 노드) | `agent/generation/compilers/`, `nodes/event_planner.py`, `nodes/event_compiler_node.py` |
| Phase 5 | 품질 개선 (balance + 프론트엔드 UI) | `agent/generation/balance.py`, `app/frontend/src/pages/GeneratePage.jsx` |

### 테스트

```
agent/tests/generation/
├── test_generation_foundations.py  # 8개 통과
└── test_balance.py                 # 6개 통과
총 14개 통과
```

---

## 2. 앞으로 구현할 페이즈

| 페이즈 | 문서 | 우선순위 | 내용 |
|--------|------|---------|------|
| **Phase 6** | `phase6_download.md` | **긴급** | 생성된 게임 ZIP 다운로드 API + 프론트엔드 버튼 |
| **Phase 7** | `phase7_db_persistence.md` | **높음** | `generations` 테이블 DB 영속성 (현재 in-memory) |
| **Phase 8** | `phase8_rag_integration.md` | 중간 | F 노드 RAG 컨텍스트 주입으로 이벤트 품질 향상 |
| **Phase 9** | `phase9_testing.md` | 중간 | 이벤트 컴파일러 + 통합 테스트 (mock LLM) |

---

## 3. 현재 폴더 구조

```
docs/The_world/
├── _INDEX.md                    ← 이 파일
│
├── [미래 페이즈 문서]
│   ├── phase6_download.md       ← Phase 6 설계
│   ├── phase7_db_persistence.md ← Phase 7 설계
│   ├── phase8_rag_integration.md← Phase 8 설계
│   └── phase9_testing.md        ← Phase 9 설계
│
├── [영구 참조 문서]
│   ├── additional_risks.md      — R11~R18 리스크 (배포 전 체크리스트)
│   ├── balance_and_economy.md   — 밸런스 수치 기준
│   ├── deployment_and_ops.md    — 운영 가이드 (Celery, Redis, 모니터링)
│   ├── rag_for_generation.md    — RAG 활용 전략
│   ├── risks_and_mitigations.md — R1~R10 리스크
│   ├── rpgmaker_constraints.md  — RPG Maker MZ JSON 제약
│   └── rpgmaker_default_assets.md — 기본 리소스 파일명
│
├── [미래 작업 문서]
│   ├── data_migration.md        — 기존 프로젝트 임포트 (우선순위 낮음)
│   └── testing_strategy.md      — 테스트 전략 상세
│
└── completed/                   ← Phase 2~5 구현 완료 문서 (20개)
    ├── IMPLEMENTATION_GUIDE.md
    ├── sprint_plan.md
    ├── workflow_implementation.md
    ├── generation_api.md
    ├── full_generation_plan.md
    ├── integration_with_existing.md
    ├── frontend_implementation.md
    ├── integrator_assembly.md
    ├── prompt_engineering.md
    ├── event_command_complete.md
    ├── asset_generation.md
    ├── classes_params_generation.md
    ├── dsl_specification.md
    ├── game_ending_design.md
    ├── llm_structured_output.md
    ├── map_connectivity_detail.md
    ├── map_generation.md
    ├── npc_conditional_and_shop.md
    ├── responder_node.md
    └── switch_allocation.md
```

---

## 4. Phase 6 상세 (다음 구현 대상)

**가장 시급한 이유**: 현재 게임 생성은 되지만 `final_project`가 메모리에만 존재.
사용자가 생성된 RPG Maker 프로젝트를 실제로 열거나 사용할 방법이 없음.

### 구현할 것

1. **`GET /api/v1/generate/{id}/download`** → ZIP 반환
   - `www/data/Actors.json`, `Map001.json` ... 구조로 압축
   - `GenerationStatusResponse`에 `final_project` 저장 필요

2. **프론트엔드 `GenerationResult.jsx`** — 다운로드 버튼 추가
   - `authFetch` binary response → `Blob` → `URL.createObjectURL`

→ 자세한 내용은 `phase6_download.md` 참조
