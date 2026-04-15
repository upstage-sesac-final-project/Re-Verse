# Editor (Chatbot Modification)

사용자의 자연어 한 줄로 기존 RPG Maker MZ 데이터를 **생성·수정·조회**하는 증분 편집 에이전트. Generator("게임 만들어줘")와는 별개 파이프라인.

> 엔트리: `agent/editor/workflow.py` · 상태: `agent/editor/state.py` · 라우팅: `agent/editor/routing.py`

---

## 1. 서비스 모드 구분

```
사용자 입력
   ├── 조회               → Reader (이 문서)
   ├── 수정/생성(증분)     → Router → Definition → Planner → Executor → Validator (이 문서)
   └── "게임 만들어줘"      → Full Generation (generator.md)
```

## 2. 핵심 위험과 대응

- **할루시네이션으로 JSON 구조 파괴** → Validator의 룰베이스 스키마 검사 + MCP 툴 호출로 정확한 필드 조작.
- **다단계 수정 의존성 실패** → Planner의 `depends_on` 위상 정렬 + Executor snapshot/backup + Validator retry 루프.
- **사용자 의도 모호** → Router 조기 종료 + Definition의 `params_sufficient=False` clarification 경로.

---

## 3. 워크플로우 (Router ~ Synthesizer)

```
사용자 입력: "1번 맵에 고블린 전투 이벤트 추가해줘"
   │
   ▼
1. Router router.py                ← LLM 1회 → intent + confidence
   │   • 액션 intent → Definition
   │   • 조회 intent → Reader
   │   • 그 외(추가_정보_필요/일반_대화/범위_외/복합_의도) → END(final_response)
   ▼
2. Reader reader.py                ← 조회 전용 빠른 경로 (파일 직읽기)
   └── END(final_response)
   ▼
3. Definition definition.py        ← LLM 3~4회 (5단계 파이프라인)
   │   Step 1: subject/property/value/action 추출
   │   Step 2: RPG Maker 카테고리 분류
   │   Step 3: system_ref 보정 (hero/game_title/currency)
   │   Step 4: RAG + SequenceMatcher로 엔티티 ID 매핑
   │   Step 5: target_files / modifications 생성 (+ 5.5 bulk 재시도)
   │   Step 6: output 보정 · Step 7: NEW ID 실제 next ID로 치환
   │   • params_sufficient=False → END(message_for_user)
   ▼
4. Planner planner.py              ← LLM 1회 → execution_plan (step_id, action_type, target_file, target_info, depends_on)
   │   └─ _restore_bulk_updates_from_definition() 로 bulk selector 복원
   ▼
5. Executor executor.py            ← 알고리즘 + MCP 툴 호출 (LLM 없음)
   │   depends_on 위상 정렬 → snapshot/backup → step 순차 실행
   │   (MCP → manager fallback → legacy handler → [UNSUPPORTED_STRUCTURED_STEP])
   │   _enrich_changes_log_entry() 로 로그 표준화
   ▼
6. Validator validator/            ← 알고리즘 (LLM 없음)
   │   schema validation + query consistency
   │   • success → Synthesizer
   │   • fail, retry<2 → Executor 재진입
   │   • fail, retry≥2 → Synthesizer
   ▼
7. Synthesizer synthesizer.py      ← LLM 1회 → final_response
   ▼
사용자 응답
```

**Retry 루프 규칙**
- retry 결정 주체는 Validator. 실패 시 `retry_count` 증가.
- Routing은 `retry_count < 2`면 Executor 재진입, `≥ 2`면 Synthesizer로.
- Executor는 `retry_count ≥ 2`면 guard로 즉시 실패 로그만 남기고 실행 안 함.
- 실질 재시도 = "Validator 기준 2번째 실패 후 Synthesizer로 종료".

---

## 4. `AgentState`

`TypedDict(total=False)` — 모든 필드 선택적. 노드마다 필요한 것만 읽고 쓴다.

```python
class AgentState(TypedDict, total=False):
    # ── 입력 ─────────────────────────────────────────────
    user_input: str
    game_id: str
    conversation_history: list[dict]

    # ── 1. Router ────────────────────────────────────────
    intent: Literal[
        "게임_요소_생성", "게임_요소_수정", "게임_요소_조회",
        "추가_정보_필요", "복합_의도", "일반_대화", "범위_외",
    ]
    confidence: float

    # ── 2. Definition ────────────────────────────────────
    target_files: list[str]
    modifications: list[dict]
    extracted_ids: dict
    params_sufficient: bool

    # ── 2.5 Operation IR (definition_v2 → planner_v2) ───
    operation_tuples: list[dict]
    plan_meta: dict                   # op_idx → step_ids 역매핑

    # ── 3. Planner ───────────────────────────────────────
    game_context: dict                # 프롬프트에 주입할 현재 게임 데이터
    execution_plan: list[dict]        # step_id/action_type/target_file/target_info/depends_on/condition

    # ── 4. Executor ──────────────────────────────────────
    current_game_state: dict          # 파일명 → 스냅샷 JSON 절대경로
    modified_game_state: dict
    backup_paths: Annotated[dict, _merge_dict]
    operation_id: str

    # ── 5. Validator ─────────────────────────────────────
    validation_results: list
    validation_summary: str
    validation_details: list[str]
    judge_feedback: str
    success: bool
    retry_count: int

    # ── 6. Synthesizer ───────────────────────────────────
    final_response: str

    # ── 누적 필드 (add reducer — retry 시 덮어쓰지 않고 쌓임) ──
    changes_log: Annotated[list, add]
    tool_results: Annotated[list, add]
```

**단계별 주 소유 필드**

| 노드 | 읽음 | 씀 |
|------|------|------|
| Router | `user_input`, `conversation_history` | `intent`, `confidence`, `final_response`(terminal) |
| Reader | `user_input`, `game_id`, `intent` | `final_response` |
| Definition | `user_input`, `game_id`, `intent` | `target_files`, `modifications`, `extracted_ids`, `params_sufficient`, `message_for_user` |
| Planner | `modifications`, `target_files`, `extracted_ids`, `user_input` | `execution_plan` |
| Executor | `execution_plan`, `modifications`, `game_id`, `retry_count`, `user_input` | `current_game_state`, `modified_game_state`, `changes_log`, `tool_results`, `modified_file_paths`, `backup_paths` |
| Validator | `current_game_state`, `modified_game_state`, `execution_plan`, `changes_log`, `retry_count` | `validation_results`, `validation_summary`, `success`, `retry_count` |
| Synthesizer | (거의 전체 state) | `final_response` |

**런타임 특이사항**
- `changes_log`, `tool_results`는 `Annotated[list, add]`라 retry에도 누적. Validator는 `step_id` 기준 최신 로그만 선택.
- `current_game_state`, `modified_game_state`는 raw JSON이 아니라 `논리파일명 → 스냅샷 경로` 맵.
- Validator는 `load_snapshot_payload()`로 path/string/payload 모두 처리.

**알려진 계약 불일치** (정리 필요)
- Definition의 `message_for_user`가 `AgentState`에 미선언.
- Executor의 `modified_file_paths`가 `AgentState`에 미선언.
- `game_context`, `operation_id`는 선언돼 있지만 실사용 거의 없음.
- Definition이 `params_sufficient=False`로 종료 시 `final_response` 대신 `message_for_user`를 내보내 그래프 contract와 어긋남.

---

## 5. 디렉터리 레이아웃

```
agent/editor/
├── workflow.py                     LangGraph 전체 워크플로우 정의
├── state.py                        AgentState TypedDict
├── routing.py                      조건부 분기 (route_after_router, route_after_definition, route_after_validator)
├── schemas.py                      공통 Pydantic 스키마
├── utils/                          스냅샷·JSON IO 헬퍼
└── nodes/
    ├── router.py                   (1) intent 분류
    ├── reader.py                   (2) 조회 전용 빠른 경로
    ├── definition.py               (3) 5단계 의미 확정 파이프라인
    ├── planner.py                  (4) execution_plan 생성
    ├── planner_v2/                 (4') Operation IR 기반 플래너
    ├── executor.py                 (5) 구조화/레거시 dispatch + MCP 인터셉트
    ├── executor_v2/                (5') 정리된 실행 경로
    ├── game_index_resolve.py       definition_v2 → planner_v2 사이 IR 해소
    ├── profiler.py                 실행 프로파일링
    ├── validator/                  (6) schema + consistency 검증
    └── synthesizer.py              (7) 최종 응답 생성

agent/
├── prompts/                        노드별 LLM 프롬프트
├── rag/                            RAG 검색 (벡터 DB + schema 문서)
├── mcp_toolbox/                    MCP stdio 클라이언트
└── tests/                          pytest + REPL (test_repl.py, full_pipeline_check.py, executor_step4_map_test.py)
```

---

## 6. 노드별 상세

### 6.1 Router (`nodes/router.py`)

- 빈 입력이면 LLM 호출 없이 `추가_정보_필요`로 조기 종료.
- 그 외 `invoke_llm(..., structured_output=_RouterOutput)` 1회.
- 액션 intent라도 confidence < `0.7`이면 `추가_정보_필요`로 강등.
- `복합_의도`/`추가_정보_필요`/`일반_대화`/`범위_외`는 즉시 `final_response` 생성 후 종료.

**intent 집합(한국어 literal)**: `게임_요소_생성`, `게임_요소_수정`, `게임_요소_조회`, `복합_의도`, `추가_정보_필요`, `일반_대화`, `범위_외`.

**병목/하드코딩**
- 매 요청 LLM 1회 필수.
- conversation history가 프롬프트에 전부 들어가 토큰 비용 증가.
- confidence threshold·intent 집합·terminal 판정 모두 상수.

### 6.2 Reader (`nodes/reader.py`)

- `게임_요소_조회` 전용. 파일 직읽기 기반, MCP·Executor 경유 없음.
- `_ReaderQuery`로 자연어 → 구조화 쿼리, 카테고리별 executor로 분기.
- 구성: 참조 해소(`_REFERENCE_MAP`), 필터(`_FILTER_MAP`), 카테고리 표시(`_CATEGORY_DISPLAY`), System 전용(`_execute_system_query`).

**알려진 공백**
- Map/MapInfos 조회 분기 없음(맵 목록·맵 정보·맵 이벤트 목록 요청이 엉뚱한 카테고리로 폴백). → `todo/map_crud.md` 참조.

### 6.3 Definition (`nodes/definition.py`)

수정·생성 intent의 의미를 `target_files + modifications`로 확정하는 다단계 파이프라인.

1. Step 1 — LLM으로 `subject/property/value/action` 추출
2. Step 2 — LLM으로 subject의 RPG Maker 카테고리 분류
3. Step 3 — `get_system_context()`로 system ref 보정 (`hero`, `game_title`, `currency` 중심)
4. Step 4 — RAG + `SequenceMatcher`로 엔티티 ID 매핑
5. Step 5 — LLM으로 최종 `target_files`/`modifications` 생성
6. Step 5.5 — bulk contract 깨졌으면 Step 5 재시도
7. Step 6 — 내부 progress spec에 맞게 output 보정
8. Step 7 — `NEW` ID를 실제 next ID로 치환

**데이터 소스**: `RPGRetriever`, `vector_store`, `get_system_context(game_id)`, `get_next_entity_id(game_id, target)`, `agent/rag/data/rpgmaker-mz-data-schema[2].md`.

**병목**
- LLM 호출 3~4회(Step 1/2/5, 필요시 5.5) + RAG + schema read.

**하드코딩**
- `game_id` 기본값 `game_001`.
- `CATEGORY_TO_PLURAL`, `CATEGORY_TO_ID_FIELD` (map/map_event 누락).
- bulk 지원: actor/enemy/item/weapon/armor/class/state/element (skill·map 미지원).
- `system_ref` 보정 대상이 hero/game_title/currency로 한정.
- SequenceMatcher 임계값: create=0.9, update/read=0.5.
- Step 6 규칙 기반 보정이 LLM 출력 형식 흔들림에 취약.
- Step 7 ID 부여는 "마지막 ID + 1" → 동시성 취약.

### 6.4 Planner (`nodes/planner.py`)

LLM 1회로 structured output `_PlannerOutput` 생성. step 스키마:

- `step_id`, `description`, `action_type`, `target_file`, `target_info`, `depends_on`, `condition`

이후 `_restore_bulk_updates_from_definition()`로 Definition의 bulk selector를 덮어쓰기 복원.

**병목**
- Planner 자체는 가볍지만 Executor가 이 포맷에 강하게 의존 — planner 출력이 흔들리면 Executor 후처리가 폭증.

**하드코딩**
- bulk target alias / target file map 상수.
- `_restore_bulk_updates_from_definition()`는 candidate 정확히 1개일 때만 복원.
- `_has_explicit_target_identity()` 기준이 key 이름 집합으로 박힘.

### 6.5 Executor (`nodes/executor.py`)

두 경로: **structured path**(planner가 step list 제공) / **legacy path**(미구조 plan → LLM으로 tool call로 번역). 실전은 structured path가 중심.

**structured path 흐름**
1. `_is_structured_execution_plan()` 판별
2. `_enrich_execution_plan_items_from_modifications()`로 일부 Items step 보정
3. `_executor_structured()` 진입
4. `depends_on` 위상 정렬 → target file 집합 계산
5. 실행 전 snapshot + backup 생성
6. step 순차 실행
    - `_should_execute_structured_step()`로 skip 판정
    - `_execute_one_structured_step()`가 giant dispatcher (MCP → manager fallback → legacy handler → `[UNSUPPORTED_STRUCTURED_STEP]`)
    - `_enrich_changes_log_entry()`로 로그 표준화
7. 실행 후 after snapshot
8. `modified_file_paths` 계산 후 반환

**MCP 통합** (통합 MCP / @rein634/rpg-maker-mz-mcp 기준)

| (target_file, action) | MCP tool |
|------|------|
| `Actors/Enemies/Items/Weapons/Armors/Classes/States/Skills.json` + CRUD | 해당 `create_*` / `update_*` / `get_*` 등 |
| `System.json` + `update_starting_position` | `update_starting_position` |
| `MapInfos.json` + `list`/`query` | `list_maps` |
| `MapInfos.json` + `create` | `create_map` |
| `Map{NNN}.json` + `query`/`read` | `get_map` |
| `Map{NNN}.json` + `update` | `update_map` |
| `Map{NNN}.json` + `list_events` | `get_map_events` |
| `Map{NNN}.json` + `search`/`search_events` | `search_map_events` |
| `Map{NNN}.json` + `create_event` | `create_map_event` |
| `Map{NNN}.json` + `update_event` | `update_map_event` |
| `Map{NNN}.json` + `add_event_command` | `add_event_command` |
| `Map{NNN}.json` + `draw_tile` | `draw_map_tile` |

- `Map{NNN}.json`은 파일명에서 mapId 자동 보강.
- MCP 실패 시 manager/legacy handler로 fallback.

**로그 표준화 — Validator의 primary evidence**

`_enrich_changes_log_entry()`가 `target_file`, 정규화된 `action`, `query_result`, `decision_basis.source_query_step_ids`, `modified_files`, 그리고 요약 필드(`exists`, `actor_id`, `class_id` 등)를 보강.

**병목**
- 파일이 monolithic하고 순차 실행만 사용.
- 매 실행마다 snapshot/backup.
- retry도 동일 heavy path를 다시 탐.

**하드코딩**
- `MCP_TOOL_MAP`, `TARGET_FILE_MAP`, legacy support set 전부 상수.
- `game_id` 기본값 `game_001`.
- target file 비면 기본 `Actors.json`.
- skip 판단이 `condition`의 한국어 phrase(`"존재하지 않"`, `"없을 경우"` 등)에 의존.
- Actors 전용 특수 로직 과다(id reconciliation, old name check, context validation, update vs update_actor 분기).
- 잔존 `print()` debug로 stdout 오염 가능.

### 6.6 Validator (`nodes/validator/`)

**실행 단계**
1. `extract_validation_inputs()` 입력 정규화
2. `load_validation_entries()` snapshot path/payload 로드
3. `validate_single_file()` schema validation
4. `validate_query_consistency()` query-result 정합성 검사
5. `build_output()` 결과 취합, 실패 시 retry_count+1
6. `finalize_output()` JSON-safe dict 반환

**consistency validation 실제 범위**
- `Actors.json`: create / update
- `Classes.json`: create
- 그 외 파일은 **schema만** 검사

**query evidence 해석 우선순위**
1. 현재 log의 직접 `query_result`
2. `decision_basis.source_query_step_ids`
3. Planner의 `depends_on`
4. 제한적 fallback 탐색

retry 시 누적 log에서 step별 최신 로그만 사용.

**병목/하드코딩**
- 모든 대상 파일을 매번 schema validate.
- consistency가 파일 단위가 아닌 log 전체 이중 순회.
- `SCHEMA_MAP`, failure category/summary 문자열, query linkage 규칙 모두 상수 + Actors/Classes 중심.
- `modified_game_state` 비면 즉시 state error.

### 6.7 Synthesizer (`nodes/synthesizer.py`)

- prompt builder에 state 전체를 넘겨 LLM 응답을 `final_response`로.
- 성공/실패 모두 synthesizer가 마지막 사용자 응답을 만든다.

**병목**
- deterministic하게 만들 수 있는 요약도 항상 LLM.
- state가 커질수록 프롬프트 비용 증가.

---

## 7. 우선 리팩터링 후보

1. **State contract 정리** — `message_for_user`/`modified_file_paths` 반영 또는 반환 계약에서 제거. `definition → END` 터미널 응답을 `final_response`로 정규화.
2. **Executor 분해** — structured/legacy path 분리, target별 handler registry, Actors 전용 로직 분리.
3. **Validator 범위 확장** — Actors/Classes 외 파일(특히 Map*) consistency 추가.
4. **Definition 간소화** — 다중 LLM 호출 축소, bulk·ID 매핑 규칙 분리, 맵 카테고리 지원.
5. **Dead field 정리** — `game_context`, `operation_id`.
6. **Reader/Definition/Planner의 맵 지원** — `todo/map_crud.md` 참조.

---

## 8. 읽기 순서

1. `agent/editor/state.py`
2. `agent/editor/workflow.py`
3. `agent/editor/routing.py`
4. `agent/editor/nodes/router.py`
5. `agent/editor/nodes/reader.py`
6. `agent/editor/nodes/definition.py`
7. `agent/editor/nodes/planner.py`
8. `agent/editor/nodes/executor.py`
9. `agent/editor/nodes/validator/`
10. `agent/editor/nodes/synthesizer.py`
