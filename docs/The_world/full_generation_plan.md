# Full Generation 설계 — 인덱스

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 목표

사용자가 "중세 판타지 게임 만들어줘"처럼 자연어로 입력하면
**5~10분 플레이타임의 완성된 RPG Maker MZ 프로젝트**가 자동 생성된다.

---

## 서브 문서 목록

| 문서 | 내용 |
|------|------|
| [dsl_specification.md](dsl_specification.md) | 이벤트 DSL 전체 명세 (npc/transfer/chest/battle/shop) |
| [map_generation.md](map_generation.md) | 맵 생성 알고리즘 상세 (BSP 던전, 격자형 마을) |
| [asset_generation.md](asset_generation.md) | 에셋 생성 상세 (Pydantic 스키마, LLM 프롬프트, 병렬 실행) |
| [risks_and_mitigations.md](risks_and_mitigations.md) | R1~R10 리스크 분석 및 완화 전략 |
| [generation_api.md](generation_api.md) | REST API, WebSocket, DB 스키마, 프론트엔드 연동 |
| [testing_strategy.md](testing_strategy.md) | 단위/통합/수동 테스트 전략 및 커버리지 목표 |
| [workflow_implementation.md](workflow_implementation.md) | LangGraph 워크플로우 구현 (노드 연결, 체크포인트, 진행률) |
| [prompt_engineering.md](prompt_engineering.md) | A(기획자)/F(이벤트 기획자) 프롬프트 전체 설계 |
| [rpgmaker_constraints.md](rpgmaker_constraints.md) | RPG Maker MZ JSON 필드 제약 (agent/schemas/ 기반) |
| [integration_with_existing.md](integration_with_existing.md) | 기존 Incremental Edit 파이프라인과의 통합 전략 |
| [balance_and_economy.md](balance_and_economy.md) | 밸런스·경제 시스템 (EXP 곡선, 골드 경제, 전투 시뮬레이션) |
| [deployment_and_ops.md](deployment_and_ops.md) | 배포·운영 가이드 (BackgroundTasks→Celery, LangSmith, 비용) |
| [additional_risks.md](additional_risks.md) | R11~R18 추가 리스크 (프롬프트 인젝션, 저장비용, 경쟁조건, 언어드리프트, 타일셋, R16 시작좌표, R17 트루프좌표, R18 MapInfos ID) |
| [frontend_implementation.md](frontend_implementation.md) | Redux 슬라이스, WebSocket 미들웨어, 생성 UI 컴포넌트 |
| [sprint_plan.md](sprint_plan.md) | 스프린트별 구현 계획 (Sprint 1~9, 완료 기준, 테스트 목표) |
| [data_migration.md](data_migration.md) | 기존 RPG Maker MZ 프로젝트 가져오기 (IdTable 재구성, API 설계) |
| [llm_structured_output.md](llm_structured_output.md) | `invoke_llm(structured_output=...)` 실제 패턴, Solar Pro 2 제약, 재시도 전략 |
| [rag_for_generation.md](rag_for_generation.md) | Full Generation에서 RAG 활용 전략 (노드별 사용 여부, 컨텍스트 예산) |
| [integrator_assembly.md](integrator_assembly.md) | System.json/MapInfos.json/Troops.json/encounterList 조립 상세 (R16~R18 대응) |
| [rpgmaker_default_assets.md](rpgmaker_default_assets.md) | 유효한 기본 리소스 파일명 목록 (스프라이트/BGM/전투배경), 맵 크기 표준, R19 대응 |
| [switch_allocation.md](switch_allocation.md) | SwitchTable 사전 할당·동적 확장·Self Switch 결정 기준, R20 스위치 충돌 방지 |
| [map_connectivity_detail.md](map_connectivity_detail.md) | connects_to 양방향 정규화, 출구 좌표 계산, R21 비대칭 연결, R22 이벤트 좌표 중복 |
| [game_ending_design.md](game_ending_design.md) | EndingEvent DSL 타입, Auto-Run 엔딩 시퀀스, 커맨드 354 구현, R23 엔딩 미달성 탐지 |
| [event_command_complete.md](event_command_complete.md) | 전체 커맨드 코드 정확한 파라미터 배열 (353/354 오류 수정 포함), 트루프 명명 규칙 |
| [classes_params_generation.md](classes_params_generation.md) | Classes.json LLM+알고리즘 분리: LlmClassList 스키마, `_build_params_2d()`, 역할 정규화, R-C1~C4 |
| [npc_conditional_and_shop.md](npc_conditional_and_shop.md) | NPC 2-페이지 조건부 대화 패턴, `compile_npc()` 구현, `compile_shop()` 전체 구현, R-NS1~NS3 |
| [responder_node.md](responder_node.md) | generation_responder 최종 노드: 성공/실패 메시지 생성, WebSocket 100% 전송, build_summary(), R-R1~R3 |

---

## 서비스 모드 구분

```
사용자 입력
    ↓
[분류기]
    ↓              ↓              ↓
 조회           수정/생성        전체 게임 생성
"목록 보여줘"  "슬라임 HP 올려줘"  "게임 만들어줘"
    ↓              ↓              ↓
 Query         Incremental      Full Generation
 Reader         Edit             (이 문서의 범위)
```

---

## 전체 워크플로우

```
사용자 입력: "중세 판타지 게임 만들어줘"
    │
    ▼
A. 기획자 (game_designer.py)
   └─ LLM 1회 → GameSpec 생성
       (제목, 스토리, 캐릭터, 맵, 적 목록)
    │
    ▼
B. 설계사 (asset_planner.py)  ← LLM 없음
   └─ ID 테이블, 스위치 테이블 사전 확정
    │
    ▼
C. 에셋 생성 (asset_generator.py)  ← LLM 병렬 (5~6회)
   └─ Actors, Skills, Items, Enemies 등 JSON 생성
    │
    ▼
D. 맵 설계사 (map_designer.py)  ← LLM 1회
   └─ 각 맵의 고수준 명세 (MapSpec) 생성
    │
    ▼
E. 타일 생성기 (mapgen/)  ← 알고리즘 (LLM 없음)
   └─ BSP 던전 / 격자형 마을 → 타일 배열 생성
    │
    ▼
F. 이벤트 기획자 (event_planner.py)  ← LLM 맵당 1회
   └─ YAML DSL 생성 (NPC 대화, 이동, 전투, 상자)
    │
    ▼
G. 이벤트 컴파일러 (compilers/)  ← LLM 없음
   └─ DSL → RPG Maker MZ 커맨드 코드 변환
    │
    ▼
H. 통합기 (integrator.py)  ← LLM 없음
   └─ 타일 배열 + 이벤트 → Map001.json, System.json 등 조립
    │
    ▼
I. 검증기 (generation_validator.py)  ← LLM 없음
   └─ ID 참조, 맵 연결성, 밸런스 수치 검증
    │
    ▼
완성된 RPG Maker MZ 프로젝트
```

---

## GenerationState 구조

```python
class GenerationState(TypedDict):
    # 입력
    user_input: str
    game_id: str
    generation_id: str

    # A. 기획자 출력
    game_spec: GameSpec | None

    # B. 설계사 출력
    id_table: IdTable | None
    switch_table: SwitchTable | None
    generation_order: list[str]
    phase_limit: str | None          # "assets" | "maps" | None (None=전체 생성)

    # C. 에셋 생성 출력
    generated_assets: dict[str, Any]        # 파일명 → JSON 데이터

    # D+E. 맵 설계사 + 타일 생성기 출력
    map_specs: list[MapSpec]
    map_tiles: dict[int, list[int]]         # map_id → 타일 배열
    connection_info: dict[int, MapConnectionInfo]

    # F+G. 이벤트 기획자 + 컴파일러 출력
    event_dsl: dict[int, list]              # map_id → DSL 이벤트
    compiled_events: dict[int, list]        # map_id → RPG Maker 커맨드

    # H. 통합기 출력
    final_project: dict[str, Any]           # 파일명 → 최종 JSON

    # I. 검증기 출력
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    retry_count: int                 # 재시도 횟수 (validator→asset_generator/event_planner 루프)

    # J. 응답기 출력 (generation_responder)
    final_message: str               # 사용자에게 전달할 한국어 결과 메시지
    is_success: bool                 # True=완전 성공, False=부분 실패(파일은 저장됨)

    # 체크포인트
    completed_phases: list[str]
    error_phase: str | None
    error_message: str | None
```

---

## 폴더 구조 (미구현)

```
agent/
└── generation/
    ├── workflow.py              # LangGraph 전체 생성 워크플로우
    ├── state.py                 # GenerationState TypedDict
    ├── nodes/
    │   ├── game_designer.py         # A. 기획자
    │   ├── asset_planner.py         # B. 설계사
    │   ├── asset_generator.py       # C. 에셋 생성
    │   ├── map_designer.py          # D. 맵 설계사
    │   ├── tile_generator.py        # E. 타일 생성기 (mapgen/ 모듈의 LangGraph 래퍼)
    │   ├── event_planner.py         # F. 이벤트 기획자
    │   ├── event_compiler_node.py   # G. 이벤트 컴파일러 (compilers/event_compiler.py 래퍼)
    │   ├── integrator.py            # H. 통합기
    │   ├── generation_validator.py  # I. 검증기
    │   └── generation_responder.py  # J. 응답기
    ├── mapgen/
    │   ├── __init__.py          # generate_map() 진입점
    │   ├── town_generator.py    # E-1. 마을 타일 생성
    │   ├── dungeon_generator.py # E-2. 던전 BSP 생성
    │   └── tile_constants.py    # 타일셋 ID 매핑
    ├── compilers/
    │   ├── event_compiler.py    # G. 이벤트 컴파일러
    │   └── dsl_models.py        # DSL Pydantic 모델
    ├── registry/
    │   ├── id_table.py          # IdTable 모델
    │   └── switch_table.py      # SwitchTable 모델
    ├── prompts/
    │   ├── game_designer_prompt.py
    │   ├── asset_generator_prompt.py
    │   ├── map_designer_prompt.py
    │   └── event_planner_prompt.py
    └── progress.py              # WebSocket 진행 상황 발행

app/backend/
└── api/v1/
    └── generation.py            # REST API 라우터
```

---

## 에셋 규모 기준 (5~10분 게임)

| 에셋 | 최소 수량 |
|------|---------|
| Actor | 2~4명 |
| Class | 2~4개 |
| Skill | 10~15개 |
| Item / Weapon / Armor | 15~20개 |
| Enemy | 6~10종 |
| Troop | 4~6개 |
| Map | 3~4개 |
| Event (맵당) | 3~8개 |

---

## Pydantic 모델 핵심

### GameSpec

```python
class CharacterSpec(BaseModel):
    name: str
    class_name: str
    role: Literal["주인공", "서포터", "딜러", "탱커"]
    personality: str

class EnemySpec(BaseModel):
    name: str
    tier: Literal["weak", "normal", "elite", "boss"]
    location: str

class MapSpec(BaseModel):
    name: str
    type: Literal["town", "dungeon", "boss", "field"]
    description: str
    connects_to: list[str]

class GameSpec(BaseModel):
    title: str
    theme: str
    playtime_minutes: int
    story: dict             # {"synopsis": ..., "acts": [...]}
    characters: list[CharacterSpec]
    enemies: list[EnemySpec]
    maps: list[MapSpec]
    key_items: list[str]
```

### IdTable / SwitchTable

```python
class IdTable(BaseModel):
    actors:  dict[str, int]   # {"해럴드": 1, "세라": 2}
    classes: dict[str, int]
    skills:  dict[str, int]
    items:   dict[str, int]
    weapons: dict[str, int]
    armors:  dict[str, int]
    enemies: dict[str, int]
    troops:  dict[str, int]
    maps:    dict[str, int]   # {"출발 마을": 1, "어둠의 던전": 2}

class SwitchTable(BaseModel):
    switches:  dict[str, int]  # {"boss_defeated": 1}
    variables: dict[str, int]
    next_switch_id: int = 1
    next_variable_id: int = 1
```

---

## 밸런스 공식 요약

```
플레이어 기준 (레벨 1):
  HP  = 100~200,  MP  = 50~100
  ATK = 10~20,    DEF = 5~10

적 HP 기준:
  weak   = 플레이어 HP × 0.4~0.6
  normal = 플레이어 HP × 0.8~1.2
  elite  = 플레이어 HP × 2.0~3.0
  boss   = 플레이어 HP × 15~25

적 ATK 한계:
  weak   ≤ 플레이어 MaxHP × 0.15
  normal ≤ 플레이어 MaxHP × 0.20
  boss   ≤ 플레이어 MaxHP × 0.30
```

---

## 구현 로드맵

### Phase 1 (현재)
- Incremental Edit 완성도 향상
- Synthesizer 할루시네이션 개선

### Phase 2 — 에셋 생성
```
A. 기획자 + B. 설계사 + C. 에셋 생성 + H. 통합 + I. 검증

결과: "게임 만들어줘" → 캐릭터/스킬/적/아이템 생성
      맵 없음 (검은 화면)
```

### Phase 3 — 맵 생성
```
D. 맵 설계사 + E. 타일 생성기 + H(맵 파일 조립)

결과: 걸어다닐 수 있는 맵 3개
      NPC/이벤트 없음
```

### Phase 4 — 이벤트 생성
```
F. 이벤트 기획자 + G. 이벤트 컴파일러

결과: 실제로 플레이 가능한 게임
      NPC 대화, 맵 이동, 보스 전투, 엔딩
```

### Phase 5 — 품질 개선
```
- 밸런스 시뮬레이션 검증
- 부분 재생성 기능
- 복잡한 DSL 타입 (중첩 조건, 변수, 연출)
- 맵 디자인 다양화
```

---

## 생성 시간 및 비용 추정

### Phase 2 기준 (에셋만)

```
A. 기획자:          ~3초
B. 설계사:          <1초
C. 에셋 생성 (병렬): ~8초
H+I:               <2초
─────────────────
합계:               ~14초
```

### Phase 4 추가 시

```
D. 맵 설계사:       ~3초
E. 타일 생성:       <1초
F. 이벤트 기획자:   ~9초 (맵 3개 × 3초)
G. 컴파일러:        <1초
─────────────────
추가:               ~13초
전체:               ~27초
```

### 토큰 비용 (게임 1개)

| 노드 | 입력 | 출력 |
|------|------|------|
| A. 기획자 | ~300 | ~600 |
| C. 에셋 생성 ×5 | ~2,500 | ~4,000 |
| D. 맵 설계사 | ~800 | ~500 |
| F. 이벤트 기획자 ×3 | ~3,000 | ~1,800 |
| 응답 생성 | ~400 | ~200 |
| **합계** | **~7,000** | **~7,100** |

---

## 부분 재생성

```
"캐릭터만 다시 만들어줘" → C(에셋 생성) 재실행
"맵 다시 짜줘"         → D+E+F+G+H+I 재실행
"이벤트 내용 바꿔줘"   → F+G+H+I 재실행
"스토리 완전히 바꿔줘" → A부터 전체 재시작
```

---

## 멀티턴 피드백 분류

| 사용자 요청 | 분류 |
|-----------|------|
| "슬라임 HP 올려줘" | incremental (기존 파이프라인) |
| "새 스킬 추가해줘" | incremental |
| "NPC 대화 바꿔줘" | partial_regen (events) |
| "던전 구조 바꿔줘" | partial_regen (maps+events) |
| "세계관 바꿔줘"   | full_regen |

---

## 참고

- RPG Maker MZ 커맨드 코드: `docs/rpgmaker/`
- Synthesizer 개선: `docs/nodes/synthesizer/`
- 현재 MCP 도구 목록: `docs/project/executor_capabilities.md`
