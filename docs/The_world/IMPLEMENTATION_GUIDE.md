# Full Generation 구현 가이드

> 29개 설계 문서를 구현에 필요한 핵심만 추출하여 정리한 단일 문서.
> 상세 사항은 각 원본 문서 참조. 최종 업데이트: 2026-04-06

---

## 1. 아키텍처 개요

자연어 한 문장 → 5~10분 플레이 가능한 RPG Maker MZ 프로젝트 자동 생성.

### 10노드 LangGraph 워크플로우

```
A. game_designer    (LLM 1회) → GameSpec
B. asset_planner    (코드)    → IdTable, SwitchTable, generation_order
C. asset_generator  (LLM 6회 병렬) → Actors/Classes/Skills/Items/Weapons/Armors/Enemies.json
       ↓ phase_limit=="assets"이면 skip_to_integrate
D. map_designer     (LLM 1회) → list[MapSpec]
E. tile_generator   (코드, 맵별 병렬) → map_tiles (flat 1D array)
F. event_planner    (LLM 맵당 1회, 병렬) → YAML DSL
G. event_compiler   (코드, 직렬) → compiled_events + switch_table 업데이트
H. integrator       (코드) → final_project (전체 JSON 파일)
I. validator        (코드) → validation_errors/warnings → 재시도 or respond
J. responder        (코드) → final_message, WebSocket 100% 전송
```

### 조건부 엣지

```python
# asset_generator 이후
"map_phase"        if phase_limit != "assets"
"skip_to_integrate" if phase_limit == "assets"

# validator 이후 (MAX_RETRY=2)
"retry_events"  if 이벤트 오류만 & retry_count < 2
"retry_assets"  if 에셋 ID 오류 & retry_count < 2
"respond"       if 성공 or retry_count >= 2
```

### 진행률(%) 배분

| 노드 | % |
|------|---|
| A game_designer | 0→10 |
| B asset_planner | 10→12 |
| C asset_generator | 12→48 |
| D map_designer | 48→55 |
| E tile_generator | 55→65 |
| F event_planner | 65→82 |
| G event_compiler | 82→87 |
| H integrator | 87→93 |
| I validator | 93→98 |
| J responder | 98→100 |

> 원본: `workflow_implementation.md`

---

## 2. GenerationState (canonical: `full_generation_plan.md`)

```python
class GenerationState(TypedDict):
    # 입력
    user_input: str
    game_id: str
    generation_id: str

    # B 노드
    id_table: IdTable | None
    switch_table: SwitchTable | None
    generation_order: list[str]
    phase_limit: str | None          # "assets" | "maps" | None

    # A+C 노드
    game_spec: GameSpec | None
    generated_assets: dict[str, Any]  # {"Actors.json": [...], ...}

    # D+E 노드
    map_specs: list[MapSpec]
    map_tiles: dict[int, list[int]]   # map_id → flat 1D (width×height×6)
    connection_info: dict[int, MapConnectionInfo]

    # F+G 노드
    event_dsl: dict[int, list]
    compiled_events: dict[int, list[dict]]

    # H 노드
    final_project: dict[str, Any]     # 파일명 → JSON

    # I 노드
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    retry_count: int

    # 체크포인트
    completed_phases: list[str]
    error_phase: str | None
    error_message: str | None

    # J 노드
    final_message: str
    is_success: bool
```

---

## 3. 핵심 데이터 모델

### 3-1. IdTable / SwitchTable (`registry/`)

```python
class IdTable(BaseModel):
    actors:  dict[str, int] = {}   # "해럴드" → 1
    classes: dict[str, int] = {}
    skills:  dict[str, int] = {}
    items:   dict[str, int] = {}
    weapons: dict[str, int] = {}
    armors:  dict[str, int] = {}
    enemies: dict[str, int] = {}
    troops:  dict[str, int] = {}
    maps:    dict[str, int] = {}

class SwitchTable(BaseModel):
    switches: dict[str, int] = {}       # "boss_defeated" → 1
    variables: dict[str, int] = {}
    next_switch_id: int = 1
    next_variable_id: int = 1

    def allocate_switch(self, name: str) -> tuple["SwitchTable", int]:
        """불변. 새 인스턴스 + ID 반환. 이미 존재하면 기존 ID."""
        if name in self.switches:
            return self, self.switches[name]
        new_id = self.next_switch_id
        return self.model_copy(update={
            "switches": {**self.switches, name: new_id},
            "next_switch_id": new_id + 1,
        }), new_id
```

> **핵심**: SwitchTable은 **불변**. `model_copy(update=...)` 패턴으로 새 인스턴스 반환.
> LangGraph 체크포인트와의 호환 때문. 원본: `switch_allocation.md`

### 3-2. GameSpec (A 노드 출력)

```python
class CharacterSpec(BaseModel):
    name: str
    class_name: str
    role: str           # "주인공" | "서포터"
    personality: str

class EnemySpec(BaseModel):
    name: str
    tier: str           # "weak" | "normal" | "elite" | "boss"
    location: str

class GameMapInfo(BaseModel):
    """GameSpec 내부의 단순 맵 정보. 상세 MapSpec과 구분."""
    name: str
    type: str           # "town" | "dungeon" | "boss" | "field"
    description: str
    connects_to: list[str]

class GameSpec(BaseModel):
    title: str
    theme: str
    playtime_minutes: int = 7
    story: dict          # {"synopsis": str, "acts": list[str]}
    characters: list[CharacterSpec]
    enemies: list[EnemySpec]
    maps: list[GameMapInfo]
    key_items: list[str] = []
    skills: list[str] = []
```

> **주의**: GameSpec의 maps는 `GameMapInfo`(단순), D 노드 출력은 `MapSpec`(상세). 이름 혼동 주의.

### 3-3. MapSpec (D 노드 출력, 상세)

```python
class LandmarkSpec(BaseModel):
    name: str
    landmark_type: str          # "building" | "exit" | "decoration"
    position_hint: str          # "north" | "south-center" | "center" 등
    npc: str | None = None

class ExitSpec(BaseModel):
    direction: str              # "north" | "south" | "east" | "west"
    to_map_id: int
    label: str

class MapSpec(BaseModel):
    map_id: int
    name: str
    map_type: Literal["town", "dungeon", "boss", "field"]  # 필드명: map_type
    width: int
    height: int
    tileset_id: int
    bgm: str
    atmosphere: str
    landmarks: list[LandmarkSpec]
    exits: list[ExitSpec]
    spawn_point: tuple[int, int]
```

### 3-4. DSL 이벤트 모델 (`compilers/dsl_models.py`)

```python
class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str; x: int; y: int
    trigger: str = "action_button"
    face_image: str = ""; face_index: int = 0
    dialogue: list[str]
    condition_switch: str | None = None    # 2페이지 조건부 대화용
    alt_dialogue: list[str] | None = None  # condition_switch ON일 때
    set_switch: str | None = None

class TransferEvent(BaseModel):
    type: Literal["transfer"]
    name: str; x: int; y: int
    trigger: str = "player_touch"
    to_map: str; to_x: int; to_y: int
    direction: str = "retain"
    set_switch: str | None = None

class ChestEvent(BaseModel):
    type: Literal["chest"]
    name: str; x: int; y: int
    item: str; item_type: str = "item"     # "item" | "weapon" | "armor"
    amount: int = 1
    one_time: bool = True
    chest_switch: str | None = None
    dialogue_before: str = ""; dialogue_after: str = ""

class BattleEvent(BaseModel):
    type: Literal["battle"]
    name: str; x: int; y: int
    trigger: str = "player_touch"
    troop: str                              # 이름. id_table에서 변환
    escape_allowed: bool = True
    lose_condition: str = "game_over"
    on_win: list[dict] = []
    one_time: bool = True
    battle_switch: str | None = None

class ShopEvent(BaseModel):
    type: Literal["shop"]
    name: str; x: int; y: int
    trigger: str = "action_button"
    dialogue: str = ""
    items: list[ShopItem]
    purchase_only: bool = False

class EndingEvent(BaseModel):
    type: Literal["ending"]
    name: str; x: int; y: int
    condition_switch: str
    lines: list[str]
    fade_type: Literal["black", "white"] = "black"
    action: Literal["title", "gameover"] = "title"

DslEvent = NpcEvent | TransferEvent | ChestEvent | BattleEvent | ShopEvent | EndingEvent
```

> 원본: `dsl_specification.md`, `npc_conditional_and_shop.md`, `game_ending_design.md`

### 3-5. RPG Maker MZ 에셋 스키마 (요약)

| 파일 | 핵심 필드 | 비고 |
|------|----------|------|
| Actors.json | id, name, classId, equips[5], characterName, faceName, traits | params 없음 — Class에서 관리 |
| Classes.json | id, name, expParams[4], params[8][99], learnings[] | params는 **알고리즘** 생성 |
| Skills.json | id, name, mpCost, scope(0-14), damage{type, formula} | formula: `"a.atk*2-b.def"` |
| Items.json | id, name, price, effects[{code:11=HP회복}] | code11 value1=회복률 |
| Weapons.json | id, name, wtypeId(1-6), params[8], price | params는 스탯 보정값 |
| Armors.json | id, name, atypeId, etypeId(1-5=장비슬롯), params[8] | |
| Enemies.json | id, name, params[8] (고정, 성장없음), exp, gold, dropItems[3], actions[] | |
| Troops.json | id, name, members[{enemyId,x,y}], pages[] | **알고리즘 생성** (LLM 아님) |

> **index-0 null 규칙**: 모든 배열의 첫 번째 요소는 `null`. ID는 1부터.
> 원본: `rpgmaker_constraints.md`, `asset_generation.md`

---

## 4. 노드별 구현 가이드

### A. game_designer

```python
async def game_designer(state: GenerationState) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=state["user_input"])]
    spec = cast(GameSpec, await invoke_llm(messages, structured_output=GameSpec))
    # connects_to 양방향 검증 + BFS 연결성 체크
    _validate_map_connections(spec)
    return {"game_spec": spec, "completed_phases": ["spec"]}
```

- LLM 패턴: `invoke_llm(messages, structured_output=GameSpec)` → Pydantic 인스턴스
- 용량 기준: 캐릭터 2~4명, 적 5~10종, 맵 3~4개
- 원본: `prompt_engineering.md`

### B. asset_planner (LLM 없음)

```python
def asset_planner(state: GenerationState) -> dict:
    spec = state["game_spec"]
    id_table = _build_id_table(spec)         # 이름→ID 매핑 (1부터)
    switch_table = _build_switch_table(spec)  # boss_defeated, act_N, game_cleared 사전할당
    order = ["classes", "actors", "skills", "items", "weapons", "armors", "enemies", "troops"]
    return {"id_table": id_table, "switch_table": switch_table,
            "generation_order": order, "completed_phases": [..., "planning"]}
```

- 원본: `asset_generation.md`, `switch_allocation.md`

### C. asset_generator (LLM 6회 병렬)

```python
async def asset_generator(state: GenerationState) -> dict:
    # 1단계: 독립 에셋 병렬 (classes, skills, items, weapons, armors, enemies)
    results = await asyncio.gather(
        generate_classes(spec, id_table), generate_skills(...), ...,
        return_exceptions=True)
    # 2단계: 의존성 있는 에셋 순차 (actors ← classes, troops ← enemies)
    actors = await generate_actors(spec, id_table, classes)
    return {"generated_assets": assets, "completed_phases": [..., "assets"]}
```

- **Classes.json params**: LLM은 개념만 (`LlmClass{id,name,expParams,learnings}`), 8×99 params는 알고리즘 생성
  - 역할 템플릿: warrior/mage/healer/thief, (lv1값, lv99값) 쌍에서 선형 보간
- **래퍼 모델 필수**: `class SkillListOutput(BaseModel): items: list[RpgSkill]`
  - `with_structured_output`은 최상위 객체 1개만 반환하므로 list 직접 반환 불가
- **Solar Pro 2 제약**: 최상위 필드 ≤12, 중첩 깊이 ≤2, 복잡 중첩 리스트 최소화
- 원본: `asset_generation.md`, `classes_params_generation.md`, `llm_structured_output.md`

### D. map_designer (LLM 1회)

```python
async def map_designer(state: GenerationState) -> dict:
    # GameSpec.maps 기반으로 상세 MapSpec 목록 생성
    specs = cast(MapSpecListOutput, await invoke_llm(messages, structured_output=MapSpecListOutput))
    # 크기 강제: MAP_SIZE_BY_TYPE으로 덮어쓰기
    for s in specs.items:
        s.width, s.height = MAP_SIZE_BY_TYPE[s.map_type]
    return {"map_specs": specs.items}
```

맵 크기 고정:
| map_type | width | height | tileset_id |
|----------|-------|--------|------------|
| town | 30 | 30 | 1 |
| dungeon | 40 | 30 | 2 |
| boss | 20 | 20 | 2 |
| field | 40 | 30 | 1 |

- 원본: `map_generation.md`, `rpgmaker_default_assets.md`

### E. tile_generator (코드, 맵별 병렬)

**마을** (`town_generator.py`): 격자형
1. 전체 잔디 → 외곽 나무 → 중앙 십자형 돌길
2. `position_hint` → 좌표 변환 → 2×2 건물 배치 → 길 연결 → 출구 → 통행 레이어

**던전** (`dungeon_generator.py`): BSP 트리
1. 전체 벽 → BSP 재귀 분할 (MIN_NODE_SIZE=7, MIN_ROOM_SIZE=4)
2. 잎 노드에 방 → 후위 순회로 L자 복도 연결
3. 첫 방에 stairs_up, 마지막 방에 stairs_down, 중간 방에 chest_tile

**타일 배열**: 6레이어, `data[layer * w * h + y * w + x]`
| 레이어 | 용도 |
|--------|------|
| 0 | 지형 (바닥, 물) |
| 1 | 건물/나무 |
| 2-3 | 장식 |
| 4 | 그림자 |
| 5 | 통행 불가 (0 이외=벽) |

`MapConnectionInfo` 추출 → F노드에 전달하여 transfer 이벤트 좌표 확정.

- 원본: `map_generation.md`

### F. event_planner (LLM 맵당 1회, 병렬)

```python
# structured_output 미사용 (YAML DSL → 자유 텍스트)
raw = cast(str, await invoke_llm(messages))
dsl = _extract_yaml_blocks(raw)        # YAML 파싱
validated = [DslEvent.model_validate(e) for e in dsl]
```

- 프롬프트 주입: map_spec, game_spec, id_table, switch_table(기할당 목록), connection_info
- 보스 맵 필수: battle 이벤트 + ending 이벤트
- 마을 필수: NPC 2개+, 선택적 shop
- 던전 필수: chest 1개+, transfer
- 3회 재시도, 실패 시 폴백 이벤트 생성
- 원본: `prompt_engineering.md`, `dsl_specification.md`

### G. event_compiler (코드, 직렬)

```python
compiler = EventCompiler(id_table=state["id_table"], switch_table=state["switch_table"])
for map_id, dsl_events in state["event_dsl"].items():
    compiled_events[map_id] = [compiler.compile(e) for e in dsl_events]
# 동적 할당된 스위치 포함
return {"compiled_events": compiled_events, "switch_table": compiler.final_switch_table}
```

DSL → RPG Maker MZ 커맨드 변환:
| DSL type | 주요 커맨드 코드 |
|----------|---------------|
| npc | 101(ShowText) + 401(Text) + 선택적 121(Switch) |
| npc (2페이지) | 페이지1: 기본대사, 페이지2: condition_switch ON시 alt_dialogue |
| transfer | 201(Transfer Player) |
| chest | 111(If switch OFF) → 126(Change Item) → 121(Switch ON) → 412(EndIf) |
| battle | 301(Battle) → 601(Win) → 보상 → 602(Escape) → 603(Lose) |
| shop | 302(Shop 첫 상품) + 605(추가 상품)×N |
| ending | 101+401(텍스트) → 221(Fadeout) → 354(Return to Title) / 353(GameOver) |

- **직렬 처리**: 병렬화하면 스위치 ID 할당 경쟁 조건 발생. 코드만이라 빠름.
- 원본: `dsl_specification.md`, `npc_conditional_and_shop.md`, `game_ending_design.md`, `event_command_complete.md`

### H. integrator (코드)

생성하는 파일:

| 파일 | 소스 |
|------|------|
| Actors~Enemies.json | asset_generator 출력 (ensure_null_at_index_0) |
| Troops.json | **알고리즘** (`generate_troops()`) |
| System.json | **알고리즘** (`build_system_json()`) |
| MapInfos.json | **알고리즘** (dict, 배열 아님!) |
| Map001~N.json | map_tiles + compiled_events + encounterList |
| States/Animations/CommonEvents.json | 고정값 `[null]` |
| Tilesets.json | 고정 3개 (마을/던전/필드) |

핵심 로직:
- `System.json`: startMapId (town 첫 번째), startX/Y (BFS로 walkable 타일 탐색), partyMembers, switches 배열
- `Troops.json`: `generate_troops()` — weak 적은 1/2/3마리 변형, boss는 단독 중앙, BATTLE_POSITIONS 사용
- `MapInfos.json`: **dict** (배열 아님). 키 = `str(map_id)`, 값 = `{id, name, order, parentId:0}`
- `encounterList`: town/boss → 빈 배열, dungeon → normal/elite troop, field → weak/normal troop
- 원본: `integrator_assembly.md`

### I. validator (코드)

11개 검증 함수:

| 함수 | 리스크 | 종류 |
|------|--------|------|
| `check_id_references()` | R1 | error |
| `check_null_at_index_0()` | — | error |
| `check_array_lengths()` | — | error |
| `check_start_position()` | R16 | error |
| `check_troop_positions()` | R17 | error |
| `check_map_id_consistency()` | R18 | error |
| `check_resource_filenames()` | R19 | error |
| `check_ending_reachable()` | R23 | error |
| `check_balance()` | — | warning |
| `check_event_coordinate_conflicts()` | R22 | warning |
| `check_switch_semantic_conflicts()` | R20 | warning |

- error → 재시도 대상, warning → 통과하되 메시지 포함
- retry_count 증가, MAX_RETRY=2 초과 시 respond로 이동
- 원본: `risks_and_mitigations.md`, `additional_risks.md`

### J. responder (코드)

```python
async def generation_responder(state: GenerationState) -> dict:
    is_success = len(state.get("validation_errors", [])) == 0
    message = _build_success_message(...) if is_success else _build_partial_message(...)
    ws_type = "completed" if is_success else "completed_with_warnings"
    await publish_progress(gen_id, {"type": ws_type, "progress": 100, "message": message})
    return {"final_message": message, "is_success": is_success}
```

- 원본: `responder_node.md`

---

## 5. LLM 호출 패턴

### 표준 패턴 (A, C, D 노드)

```python
from typing import cast
result = cast(Schema, await invoke_llm(messages, structured_output=Schema))
```

- `invoke_llm` 내부: `llm.with_structured_output(Schema, method="function_calling")`
- 반환: Pydantic 인스턴스 (str 아님)
- **재시도**: `invoke_with_retry(messages, schema, max_attempts=3)` — 실패 시 오류 컨텍스트 추가

### 예외 패턴 (F 노드 — event_planner)

```python
raw = cast(str, await invoke_llm(messages))  # structured_output 미지정 → str
dsl = _extract_yaml_blocks(raw)               # YAML 파싱
```

- YAML DSL은 function_calling 스키마로 표현 어려움
- 3회 재시도, 실패 시 폴백 이벤트 생성

### Solar Pro 2 스키마 제약

- 최상위 필드 ≤ 12
- 중첩 깊이 ≤ 2
- 리스트를 직접 반환 불가 → 래퍼 모델 (`SkillListOutput{items: list[RpgSkill]}`)

> 원본: `llm_structured_output.md`

---

## 6. RPG Maker MZ 주요 커맨드 코드

| 코드 | 기능 | 파라미터 |
|------|------|---------|
| 0 | Event End | [] |
| 101 | Show Text (시작) | [face, faceIdx, bg, pos, speaker] |
| 401 | Text Data | [text] |
| 111 | If (조건분기) | [type, value, ...] |
| 412 | End If | [] |
| 121 | Control Switches | [id_start, id_end, value] (0=ON, 1=OFF) |
| 123 | Control Self Switch | ["A"\|"B"\|"C"\|"D", value] |
| 126 | Change Items | [item_id, inc_or_dec, operand_type, amount] |
| 127 | Change Weapons | [weapon_id, ...] |
| 128 | Change Armors | [armor_id, ...] |
| 201 | Transfer Player | [mode, mapId, x, y, direction, fadeType] |
| 221 | Fadeout Screen | [] |
| 230 | Wait | [frames] |
| 301 | Battle Processing | [mode, troopId, canEscape, canLose] |
| 302 | Shop Processing | [goodsType, goodsId, priceType, price, purchaseOnly, false] |
| 605 | Shop Item (추가) | [goodsType, goodsId, priceType, price] |
| 353 | Game Over | [] |
| 354 | Return to Title | [] |
| 601 | If Win | [] |
| 602 | If Escape | [] |
| 603 | If Lose | [] |

> 원본: `event_command_complete.md`, `dsl_specification.md`

---

## 7. 밸런스 기준

### 플레이어 Lv1 스탯 범위

| 스탯 | Lv1 | Lv99 |
|------|-----|------|
| MHP | 150~200 | 2000~3000 |
| MMP | 60~100 | 800~1200 |
| ATK | 12~18 | 200~300 |
| DEF | 6~10 | 100~150 |
| MAT | 8~15 | 150~250 |
| AGI | 8~12 | 100~150 |
| LUK | 8~12 | 80~120 |

### 적 티어별 스탯

| 티어 | HP | ATK | EXP | GOLD |
|------|-----|-----|-----|------|
| weak | 60~90 | 8~12 | 20~50 | 10~30 |
| normal | 120~200 | 12~18 | 50~100 | 30~80 |
| elite | 300~500 | 20~28 | 200~400 | 100~300 |
| boss | 2000~4000 | 30~45 | 1000~3000 | 500~2000 |

### 역할별 보정 (Classes.json params 알고리즘용)

| 역할 | mhp | mmp | atk | def | mat | mdf | agi | luk |
|------|-----|-----|-----|-----|-----|-----|-----|-----|
| warrior | (180,2500) | (60,800) | (18,280) | (10,150) | (8,135) | (8,110) | (9,110) | (8,80) |
| mage | (120,1800) | (100,1500) | (8,100) | (5,80) | (15,300) | (10,180) | (8,100) | (10,100) |
| healer | (140,2200) | (80,1200) | (6,80) | (6,100) | (12,250) | (12,200) | (7,90) | (12,120) |
| thief | (130,2000) | (50,600) | (14,220) | (7,100) | (6,100) | (6,90) | (14,200) | (14,150) |

> 원본: `balance_and_economy.md`, `classes_params_generation.md`

---

## 8. API & WebSocket

### REST 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/generate` | 생성 시작 → generation_id 반환 |
| GET | `/api/v1/generate/{id}/status` | 상태 조회 |
| POST | `/api/v1/generate/{id}/retry` | 재시도 |
| DELETE | `/api/v1/generate/{id}` | 취소 |

### WebSocket 이벤트

| type | 의미 | progress |
|------|------|---------|
| progress | 진행 중 | 0~99 |
| phase_complete | 노드 완료 | — |
| completed | 성공 | 100 |
| completed_with_warnings | 부분 성공 (경고 있음) | 100 |
| error | 오류 | — |
| warning | 경고 (계속 진행) | — |

### DB (generations 테이블)

status: `started | in_progress | completed | completed_with_warnings | failed | cancelled`

> 원본: `generation_api.md`

---

## 9. 폴더 구조

```
agent/generation/
├── workflow.py                  # LangGraph 그래프 정의
├── state.py                     # GenerationState TypedDict
├── progress.py                  # publish_progress() WebSocket
├── nodes/
│   ├── game_designer.py         # A. LLM→GameSpec
│   ├── asset_planner.py         # B. IdTable, SwitchTable (코드)
│   ├── asset_generator.py       # C. LLM×6→에셋 JSON
│   ├── map_designer.py          # D. LLM→MapSpec[]
│   ├── tile_generator.py        # E. 알고리즘→타일 배열 (mapgen/ 래퍼)
│   ├── event_planner.py         # F. LLM→YAML DSL
│   ├── event_compiler_node.py   # G. DSL→커맨드 (compilers/ 래퍼)
│   ├── integrator.py            # H. 전체 조립
│   ├── generation_validator.py  # I. 11개 검증 함수
│   └── generation_responder.py  # J. 최종 메시지
├── mapgen/
│   ├── __init__.py              # generate_map() 진입점
│   ├── town_generator.py
│   ├── dungeon_generator.py
│   └── tile_constants.py        # TOWN_TILES, DUNGEON_TILES
├── compilers/
│   ├── event_compiler.py        # EventCompiler 클래스
│   └── dsl_models.py            # DslEvent 유니온, NpcEvent 등
├── registry/
│   ├── id_table.py
│   └── switch_table.py
├── prompts/
│   ├── game_designer_prompt.py
│   ├── asset_generator_prompt.py
│   ├── map_designer_prompt.py
│   └── event_planner_prompt.py
└── models.py                    # GameSpec, MapSpec, etc.

app/backend/
├── api/v1/endpoints/generation.py   # REST + WS 엔드포인트
└── schemas/generation.py            # 요청/응답 Pydantic
```

---

## 10. 구현 순서 (권장)

### Phase 2: 에셋 생성

```
1. state.py           — GenerationState
2. registry/          — IdTable, SwitchTable (불변 패턴)
3. models.py          — GameSpec, CharacterSpec, EnemySpec, GameMapInfo
4. nodes/game_designer.py     — A노드 + 프롬프트
5. nodes/asset_planner.py     — B노드 (코드)
6. nodes/asset_generator.py   — C노드 + 병렬 LLM
7. nodes/integrator.py        — H노드 (에셋만)
8. nodes/generation_validator.py — I노드 (에셋 검증만)
9. nodes/generation_responder.py — J노드
10. workflow.py        — 그래프 조립 (phase_limit="assets")
11. progress.py        — WebSocket 진행률
12. API + DB           — generation.py, generations 테이블
```

### Phase 3: 맵 생성

```
13. mapgen/tile_constants.py
14. mapgen/town_generator.py
15. mapgen/dungeon_generator.py
16. nodes/map_designer.py      — D노드
17. nodes/tile_generator.py    — E노드 (mapgen 래퍼)
18. integrator 확장             — Map*.json, System.json 완성
```

### Phase 4: 이벤트 생성

```
19. compilers/dsl_models.py    — DslEvent 유니온
20. compilers/event_compiler.py — EventCompiler (compile_npc, compile_transfer, ...)
21. nodes/event_planner.py     — F노드 (YAML DSL)
22. nodes/event_compiler_node.py — G노드 래퍼
23. integrator 확장             — events → Map*.json, encounterList
24. validator 확장              — 전체 11개 검증 함수
```

---

## 11. 주의사항 체크리스트

- [ ] **SwitchTable 불변**: `self.switch_table, sid = self.switch_table.allocate_switch(name)` (tuple 언패킹!)
- [ ] **index-0 null**: 모든 RPG Maker 배열의 `[0]`은 `null`
- [ ] **MapSpec vs GameMapInfo**: D노드 출력(`map_type` 필드)과 GameSpec 내부(`type` 필드) 구분
- [ ] **LLM 패턴**: `cast(Schema, await invoke_llm(messages, structured_output=Schema))` — `_extract_json` 사용 금지
- [ ] **event_planner만 예외**: structured_output 미사용, YAML 자유 텍스트 + 파싱
- [ ] **래퍼 모델**: list 반환 시 `class XListOutput(BaseModel): items: list[X]`
- [ ] **Solar Pro 2 제약**: 필드 ≤12, 중첩 ≤2
- [ ] **event_compiler 직렬**: 병렬화 시 스위치 ID 충돌
- [ ] **맵 크기 강제**: MAP_SIZE_BY_TYPE으로 LLM 출력 덮어쓰기
- [ ] **스위치 이름 prefix**: 맵별 이벤트에서 `"맵이름_switch명"` 형식으로 충돌 방지
- [ ] **통행 레이어**: data[5 * w * h + y * w + x] — 0이면 통행 가능, 아니면 벽
- [ ] **MapInfos.json**: **dict** (배열 아님), 키는 `str(map_id)`
- [ ] **Troops 좌표**: x ∈ [0, 816], y ∈ [0, 624]
- [ ] **엔딩 필수**: 보스 맵에 code 354 또는 353이 없으면 validator 오류

---

## 12. 원본 문서 참조표

| 주제 | 원본 문서 |
|------|----------|
| 마스터 플랜 / GenerationState | `full_generation_plan.md` |
| 10노드 그래프 / 체크포인트 | `workflow_implementation.md` |
| REST + WebSocket API | `generation_api.md` |
| 구현 일정 | `sprint_plan.md` |
| 기존 코드 통합 | `integration_with_existing.md` |
| 에셋 생성 상세 | `asset_generation.md` |
| Classes 8×99 params | `classes_params_generation.md` |
| 밸런스 공식 | `balance_and_economy.md` |
| invoke_llm 패턴 | `llm_structured_output.md` |
| RAG 사용 범위 | `rag_for_generation.md` |
| 프롬프트 설계 | `prompt_engineering.md` |
| RPG Maker 제약 | `rpgmaker_constraints.md` |
| 기본 리소스 목록 | `rpgmaker_default_assets.md` |
| 맵 생성 알고리즘 | `map_generation.md` |
| 맵 연결성 | `map_connectivity_detail.md` |
| 스위치 할당 | `switch_allocation.md` |
| DSL 명세 | `dsl_specification.md` |
| 커맨드 코드 레퍼런스 | `event_command_complete.md` |
| NPC 조건부/상점 | `npc_conditional_and_shop.md` |
| 엔딩 설계 | `game_ending_design.md` |
| 통합기 조립 | `integrator_assembly.md` |
| 응답기 | `responder_node.md` |
| 테스트 전략 | `testing_strategy.md` |
| 리스크 R1~R10 | `risks_and_mitigations.md` |
| 리스크 R11~R18 | `additional_risks.md` |
