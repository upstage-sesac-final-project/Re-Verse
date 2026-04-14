# Generator (Full Game Generation / "The World")

"중세 판타지 게임 만들어줘" 같은 한 문장 입력으로 **5~10분 플레이타임의 RPG Maker MZ 프로젝트 전체**를 생성하는 파이프라인. Editor(증분 편집) 파이프라인과는 별개 워크플로우다.

> 엔트리: `agent/generation/workflow.py`  ·  상태: `agent/generation/state.py`  ·  API: `app/backend/api/v1/endpoints/generation.py`

---

## 1. 서비스 모드 구분

```
사용자 입력
   ├── 조회              → Reader (editor.md 참조)
   ├── 수정/생성(증분)    → Definition→Planner→Executor→Validator (editor.md)
   └── "게임 만들어줘"     → Full Generation (이 문서)
```

## 2. 구현 현황 (2026-04-06 기준)

| 페이즈 | 상태 | 범위 |
|--------|------|------|
| Phase 2 — 에셋 생성 (A~C) | 완료 | `agent/generation/nodes/{game_designer,asset_planner,asset_generator}.py` |
| Phase 3 — 맵 생성 (D~E) | 완료 | `agent/generation/mapgen/`, `nodes/{map_designer,tile_generator}.py` |
| Phase 4 — 이벤트 생성 (F~J) | 완료 | `agent/generation/compilers/`, `nodes/{event_planner,event_compiler_node}.py` |
| Phase 5 — 품질 개선 | 완료 | `agent/generation/balance.py`, 프론트엔드 `GeneratePage.jsx` |
| **Phase 6 — 디스크 저장** | **긴급, 미구현** | `agent/generation/writer.py`(신규), `generation.py` 버그 수정 |
| Phase 7 — RAG 주입 | 중간 | F 노드에 컨텍스트 주입으로 이벤트 품질 향상 |
| Phase 8 — 테스트 | 중간 | 이벤트 컴파일러 + 통합 테스트 (mock LLM) |

**테스트**: `agent/tests/generation/test_generation_foundations.py` 8, `test_balance.py` 6 — 총 14건 통과.

### Phase 6 시급성

생성은 되지만 `final_project`가 메모리에만 존재하고 디스크에 저장되지 않아 **생성된 게임을 플레이할 수 없다**. 프론트엔드에 RPGMakerFrame(`/game/{game_id}/index.html` iframe)이 이미 있어, 디스크 기록만 붙이면 바로 연결된다.

해야 할 것:
1. `agent/generation/writer.py`에 `write_project_to_disk(game_id, final_project)` 신규.
2. `generation.py`의 `game_id = str(project_id)` 버그를 `project.game_id`로 수정.
3. 백그라운드 태스크 완료 후 위 함수 호출.
4. `GenerationResult.jsx`의 버튼 텍스트 "에디터에서 열기" → "게임 플레이 →".

> DB 영속성은 불필요. 게임 파일이 디스크에 저장되므로 서버 재시작 후에도 플레이 가능. 대화이력은 localStorage. `_generation_states` in-memory 손실은 허용.

---

## 3. 워크플로우 A~J

```
사용자 입력: "중세 판타지 게임 만들어줘"
   │
   ▼
A. 기획자 game_designer.py        ← LLM 1회 → GameSpec (제목/스토리/캐릭/맵/적)
   ▼
B. 설계사 asset_planner.py        ← LLM 없음 → IdTable, SwitchTable 사전 확정
   ▼
C. 에셋 생성 asset_generator.py    ← LLM 병렬 5~6회 → Actors/Skills/Items/Enemies JSON
   ▼
D. 맵 설계사 map_designer.py       ← LLM 1회 → MapSpec (맵별 고수준 명세)
   ▼
E. 타일 생성기 mapgen/             ← 알고리즘 (BSP 던전 / 격자형 마을) → 타일 배열
   ▼
F. 이벤트 기획자 event_planner.py  ← LLM 맵당 1회 → YAML DSL (NPC/이동/전투/상자/상점)
   ▼
G. 이벤트 컴파일러 compilers/      ← LLM 없음 → DSL → RPG Maker MZ 커맨드 코드
   ▼
H. 통합기 integrator.py            ← LLM 없음 → Map001.json, System.json 등 조립
   ▼
I. 검증기 generation_validator.py  ← LLM 없음 → ID 참조/맵 연결성/밸런스 검증
   ▼
J. 응답기 generation_responder.py  ← 성공/실패 한국어 메시지 + WebSocket 100% 전송
   ▼
완성된 RPG Maker MZ 프로젝트
```

LLM 호출은 A/C(병렬)/D/F에만 들어가고 B/E/G/H/I/J는 결정론적. 재시도 루프는 Validator(I) → asset_generator/event_planner로.

---

## 4. `GenerationState`

```python
class GenerationState(TypedDict):
    # 입력
    user_input: str
    game_id: str
    generation_id: str

    # A. 기획자
    game_spec: GameSpec | None

    # B. 설계사
    id_table: IdTable | None
    switch_table: SwitchTable | None
    generation_order: list[str]
    phase_limit: str | None          # "assets" | "maps" | None(전체)

    # C. 에셋
    generated_assets: dict[str, Any] # 파일명 → JSON

    # D+E. 맵
    map_specs: list[MapSpec]
    map_tiles: dict[int, list[int]]
    connection_info: dict[int, MapConnectionInfo]

    # F+G. 이벤트
    event_dsl: dict[int, list]
    compiled_events: dict[int, list]

    # H. 통합
    final_project: dict[str, Any]    # 파일명 → 최종 JSON

    # I. 검증
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    retry_count: int

    # J. 응답
    final_message: str
    is_success: bool

    # 체크포인트
    completed_phases: list[str]
    error_phase: str | None
    error_message: str | None
```

---

## 5. 디렉터리 레이아웃

```
agent/generation/
├── workflow.py                  LangGraph 전체 워크플로우
├── state.py                     GenerationState
├── balance.py                   EXP/골드/전투 시뮬레이션
├── progress.py                  WebSocket 진행률 발행
├── nodes/
│   ├── game_designer.py         (A)
│   ├── asset_planner.py         (B)
│   ├── asset_generator.py       (C)
│   ├── map_designer.py          (D)
│   ├── tile_generator.py        (E, mapgen 래퍼)
│   ├── event_planner.py         (F)
│   ├── event_compiler_node.py   (G, compilers 래퍼)
│   ├── integrator.py            (H)
│   ├── generation_validator.py  (I)
│   └── generation_responder.py  (J)
├── mapgen/
│   ├── __init__.py              generate_map() 진입
│   ├── town_generator.py        격자형 마을
│   ├── dungeon_generator.py     BSP 던전
│   └── tile_constants.py        타일셋 ID 매핑
├── compilers/
│   ├── event_compiler.py        DSL → MZ 커맨드
│   └── dsl_models.py            Pydantic DSL 모델
├── registry/
│   ├── id_table.py
│   └── switch_table.py
└── prompts/
    ├── game_designer_prompt.py
    ├── asset_generator_prompt.py
    ├── map_designer_prompt.py
    └── event_planner_prompt.py
```

---

## 6. DSL (이벤트 명세)

이벤트 기획자(F)의 출력은 YAML DSL. 컴파일러(G)가 RPG Maker MZ 커맨드 코드로 변환한다. 타입:

- `npc` — 대화/조건부 2페이지 대화, 상점 호출
- `transfer` — 맵 이동 (양방향 `connects_to` 정규화, 출구 좌표 계산)
- `chest` — 보물상자 (아이템/골드 획득 + self switch로 1회성)
- `battle` — 강제 전투 (Troop 코드 정확한 파라미터 배열)
- `shop` — 상점 대화
- `ending` — EndingEvent Auto-Run 시퀀스 (커맨드 354)

NPC는 2-페이지 조건부 패턴(Self Switch로 기본 대사 / 완료 대사 분기)을 쓰고, 상점은 `compile_shop()`이 전 아이템을 단일 커맨드로 묶는다.

---

## 7. 생성 조립 규칙 (R16~R23 관련)

- **시작 좌표**(startX/Y)는 패스 가능 타일이어야 함 — integrator가 벽 타일 회피(R16).
- **Troop 전투 좌표**는 화면 범위 안에 있어야 함(R17).
- **MapInfos.json의 map_id**는 실제 MapNNN.json과 1:1 일치해야 함(R18).
- **기본 리소스 파일명**은 RPG Maker MZ 디폴트 목록에서만 선택(스프라이트/BGM/전투배경, R19).
- **Switch 충돌 방지**: `SwitchTable`이 사전 할당 + 동적 확장, Self Switch는 이벤트별 독립(R20).
- **맵 연결성**: `connects_to`를 양방향 정규화하여 비대칭 연결 차단(R21).
- **이벤트 좌표 중복** 방지(R22).
- **엔딩 미달성 탐지** — validator가 엔딩 이벤트 도달 가능성 검증(R23).

---

## 8. 주요 리스크 (요약)

| # | 리스크 | 우선순위 | 완화 |
|---|--------|---------|------|
| R11 | 프롬프트 인젝션 / 부적절 콘텐츠 | P1 | 입력 정제, 길이 제한, 시스템 프롬프트 격리 |
| R12 | 스토리지 비용 무한 증가 | P2 | 생성량 상한, TTL·GC |
| R13 | Full Gen ↔ Incremental Edit 동시 쓰기 | P1 | game_lock, write 경로 직렬화 |
| R14 | LLM 언어 드리프트 (영어 출력) | P2 | 한국어 강제 예시, 후처리 필터 |
| R15 | 타일셋 ID 불일치 | P1 | `tile_constants.py` 고정, validator 검사 |
| R16 | 시작 좌표가 벽 | **P0** | 통합기 패스어블 검증 |
| R17 | Troop 좌표 범위 초과 | P2 | 컴파일러 clamp |
| R18 | MapInfos ID 불일치 | P2 | IdTable 강제 일치 |

> R1~R10은 할루시네이션/의존성/비용 등 일반 리스크. 현 구현은 Structured Output(Pydantic) + few-shot + RAG 스키마 참조 + validator로 방어.

---

## 9. 밸런스·경제

- EXP 곡선, 골드 경제, 전투 시뮬레이션은 `agent/generation/balance.py`가 결정론으로 계산.
- Classes.json은 LLM이 역할/설명만 만들고, `_build_params_2d()`가 레벨별 스탯 2D 배열을 알고리즘으로 생성.

---

## 10. API / 프론트엔드 연동

- `POST /api/v1/generate` — 비동기 시작, `project_id` 반환.
- `WS /api/v1/generate/ws/{generation_id}` — 진행률 + 페이즈 이벤트 스트림.
- 프론트: `GeneratePage.jsx` + Redux 생성 슬라이스 + WebSocket 미들웨어.
- 완료 시 `GenerationResult.jsx` → RPGMakerFrame으로 플레이.

---

## 11. 향후 작업 우선순위

1. **Phase 6 디스크 저장** (P0) — 현재 가장 큰 병목.
2. Phase 7 RAG 주입 (F 노드 이벤트 품질).
3. Phase 8 통합 테스트 (mock LLM으로 전체 파이프라인 커버).
4. 데이터 마이그레이션 (기존 RPG Maker MZ 프로젝트 임포트) — 우선순위 낮음.
