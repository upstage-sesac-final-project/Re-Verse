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
총 14개 통과 (agent/tests 전체: 126개)
```

---

## 2. 앞으로 구현할 페이즈

| 페이즈 | 문서 | 우선순위 | 내용 |
|--------|------|---------|------|
| **Phase 6** | `phase6_save_to_disk.md` | **긴급** | `final_project` 디스크 저장 → 기존 인게임 플레이 환경 연결 |
| **Phase 7** | `phase7_rag_integration.md` | 중간 | F 노드 RAG 컨텍스트 주입으로 이벤트 품질 향상 |
| **Phase 8** | `phase8_testing.md` | 중간 | 이벤트 컴파일러 + 통합 테스트 (mock LLM) |

> **DB 영속성 불필요**: Phase 6에서 게임 파일이 디스크에 저장되므로 서버 재시작 후에도 플레이 가능.
> 대화이력은 이미 localStorage에 저장 중. `_generation_states` in-memory 손실은 허용 가능.

---

## 3. 현재 폴더 구조

```
docs/The_world/
├── _INDEX.md                    ← 이 파일
│
├── [미래 페이즈 문서]
│   ├── phase6_save_to_disk.md   ← Phase 6 설계
│   ├── phase7_rag_integration.md← Phase 7 설계
│   └── phase8_testing.md        ← Phase 8 설계
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
프론트엔드에 RPGMakerFrame(`/game/{game_id}/index.html` iframe)이 이미 있지만,
데이터가 디스크에 저장되지 않아 생성된 게임을 플레이할 수 없음.

### 구현할 것

1. **`agent/generation/writer.py`** (신규) — `write_project_to_disk(game_id, final_project)`
2. **`app/backend/api/v1/endpoints/generation.py`** 수정
   - `game_id = str(project_id)` 버그 수정 → `project.game_id` 사용
   - 백그라운드 태스크 완료 후 `write_project_to_disk` 호출
3. **`GenerationResult.jsx`** — "에디터에서 열기" → "게임 플레이 →" 텍스트 수정

→ 자세한 내용은 `phase6_save_to_disk.md` 참조
