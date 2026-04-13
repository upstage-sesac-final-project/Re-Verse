# SwitchTable 설계 — 사전 할당과 동적 확장

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 문제

Full Generation에서 스위치는 두 단계에서 필요하다:

1. **사전 할당** (B. asset_planner): 게임 전체 구조를 보고 예측 가능한 스위치를 미리 등록
2. **동적 할당** (F. event_planner + G. event_compiler): 맵별 이벤트를 생성하면서 필요한 스위치 등록

두 단계가 충돌하지 않으려면 **단일 카운터로 관리되는 할당 메커니즘**이 필요하다.

---

## SwitchTable 전체 설계

```python
class SwitchTable(BaseModel):
    switches:  dict[str, int]   # 이름 → ID 매핑
    variables: dict[str, int]   # 이름 → ID 매핑
    next_switch_id:  int = 1    # 다음에 할당할 스위치 ID
    next_variable_id: int = 1   # 다음에 할당할 변수 ID

    def allocate_switch(self, name: str) -> tuple["SwitchTable", int]:
        """
        이름이 이미 존재하면 기존 ID 반환.
        없으면 next_switch_id로 새로 할당하고 카운터 증가.
        SwitchTable은 불변(immutable)이므로 새 인스턴스를 반환한다.
        """
        if name in self.switches:
            return self, self.switches[name]
        new_id = self.next_switch_id
        new_switches = {**self.switches, name: new_id}
        new_table = self.model_copy(update={
            "switches": new_switches,
            "next_switch_id": new_id + 1,
        })
        return new_table, new_id

    def allocate_variable(self, name: str) -> tuple["SwitchTable", int]:
        """변수 동적 할당."""
        if name in self.variables:
            return self, self.variables[name]
        new_id = self.next_variable_id
        new_variables = {**self.variables, name: new_id}
        new_table = self.model_copy(update={
            "variables": new_variables,
            "next_variable_id": new_id + 1,
        })
        return new_table, new_id

    def get_switch_id(self, name: str) -> int:
        """이름으로 스위치 ID 조회. 없으면 KeyError."""
        return self.switches[name]

    def get_variable_id(self, name: str) -> int:
        return self.variables[name]
```

> **왜 불변 설계인가**: LangGraph 노드는 상태를 반환(dict)으로만 업데이트한다.
> 노드 내부에서 상태를 직접 변경하는 패턴은 LangGraph의 체크포인트와 충돌한다.
> `model_copy(update=...)` 패턴으로 새 인스턴스를 생성하고 반환한다.

---

## 1단계: asset_planner 사전 할당

`asset_planner._build_switch_table(game_spec)`에서
**GameSpec 구조만으로 예측 가능한 스위치**를 미리 등록한다.

### 사전 할당 규칙

```python
def _build_switch_table(spec: GameSpec) -> SwitchTable:
    """
    GameSpec에서 구조적으로 예측 가능한 스위치/변수를 사전 할당한다.
    이벤트 내용(구체적인 NPC 대화, 상자 위치)은 알 수 없으므로 등록하지 않음.
    """
    table = SwitchTable(switches={}, variables={}, next_switch_id=1, next_variable_id=1)

    # 1. 각 보스 처치 스위치
    for enemy in spec.enemies:
        if enemy.tier in ("boss", "elite"):
            table, _ = table.allocate_switch(f"{enemy.name}_defeated")

    # 2. 게임 진행 단계 스위치 (스토리 acts 수 기반)
    acts = spec.story.get("acts", [])
    for i, act in enumerate(acts):
        table, _ = table.allocate_switch(f"act_{i+1}_started")

    # 3. 맵 방문 여부 변수 (선택적)
    for map_spec in spec.maps:
        if map_spec.type == "dungeon":
            table, _ = table.allocate_switch(f"{map_spec.name}_cleared")

    # 4. 기본 게임 진행 스위치
    table, _ = table.allocate_switch("game_cleared")

    return table
```

### 사전 할당 결과 예시

GameSpec: enemies=[슬라임(weak), 고블린(normal), 드래곤(boss)], acts=["시작", "중반", "결말"], maps=[마을, 던전, 보스 방]

```python
SwitchTable(
    switches={
        "드래곤_defeated":  1,  # boss 처치
        "act_1_started":   2,
        "act_2_started":   3,
        "act_3_started":   4,
        "던전_cleared":    5,
        "game_cleared":    6,
    },
    next_switch_id=7,
)
```

---

## 2단계: event_planner DSL에서 스위치 이름 사용

event_planner LLM은 스위치를 **이름으로만** 참조한다. ID는 모른다.

### 프롬프트 주입

event_planner_prompt.py에서 이미 할당된 스위치 목록을 LLM에 제공:

```python
def build_event_planner_prompt(..., switch_table: SwitchTable, ...) -> list[BaseMessage]:
    allocated_switches = "\n".join(
        f"  - {name}: {sid}"
        for name, sid in sorted(switch_table.switches.items(), key=lambda x: x[1])
    )
    system = f"""...
## 사전 할당된 스위치 (이 이름을 우선 사용하세요)
{allocated_switches}

## 새 스위치 생성 규칙
- 위 목록에 없는 스위치가 필요하면 명확한 영어/한국어 이름을 사용하세요
- 예: chest_2_opened, npc_quest_started, shop_unlocked
- 숫자만 있는 이름 금지: "switch_1" 불허, "chest_opened" 허용
- 같은 맵 내에서만 유효한 스위치는 Self Switch(A/B/C/D)를 우선 사용
..."""
```

### DSL에서 스위치 이름 참조 예시

```yaml
- type: chest
  name: 보물상자
  x: 5
  y: 8
  item_type: item
  item_id: 3
  switch_id: chest_forest_opened    # 이름 참조 (ID 아님)

- type: npc
  name: 문지기
  x: 15
  y: 12
  lines:
    - "드래곤을 처치해야 통과할 수 있소."
  condition_switch: 드래곤_defeated  # 사전 할당된 스위치 이름 사용
```

---

## 3단계: event_compiler에서 스위치 이름 → ID 해석

`event_compiler.py`는 DSL을 RPG Maker MZ 커맨드로 변환할 때
스위치 이름을 ID로 해석해야 한다.

### 이름 해석 로직

```python
class EventCompiler:
    def __init__(self, id_table: IdTable, switch_table: SwitchTable):
        self.id_table = id_table
        self._switch_table = switch_table  # 내부적으로 변경 가능
        self._allocated: list[tuple[str, int]] = []  # 새 할당 기록

    def resolve_switch(self, name: str) -> int:
        """
        스위치 이름 → ID 해석.
        1. SwitchTable에 있으면 그 ID 반환
        2. 없으면 동적 할당 (이름과 ID를 _allocated에 기록)
        """
        self._switch_table, sid = self._switch_table.allocate_switch(name)
        if (name, sid) not in self._allocated and name not in self._original_switches:
            self._allocated.append((name, sid))
        return sid

    def resolve_variable(self, name: str) -> int:
        self._switch_table, vid = self._switch_table.allocate_variable(name)
        return vid

    @property
    def final_switch_table(self) -> SwitchTable:
        """컴파일 완료 후의 최종 SwitchTable (동적 할당 포함)."""
        return self._switch_table
```

### 컴파일러 사용 예시

```python
async def run_event_compiler(state: GenerationState) -> dict:
    compiler = EventCompiler(
        id_table=state["id_table"],
        switch_table=state["switch_table"],
    )
    compiled_events: dict[int, list] = {}

    # 맵별 직렬 컴파일 (스위치 할당 순서 보장)
    for map_id, dsl_events in state["event_dsl"].items():
        compiled = []
        for event in dsl_events:
            compiled.append(compile_event(event, compiler))
        compiled_events[map_id] = compiled

    return {
        "compiled_events": compiled_events,
        "switch_table": compiler.final_switch_table,  # 동적 할당 반영
    }
```

> **직렬 처리**: 맵별 컴파일을 `asyncio.gather()`로 병렬화하면 스위치 ID 할당에
> 경쟁 조건이 생긴다. 컴파일은 LLM 없는 순수 알고리즘이므로 직렬로도 충분히 빠름.

---

## Self Switch vs Global Switch 결정 기준

| 상황 | 사용할 스위치 |
|------|------------|
| 한 이벤트 내의 "열림/닫힘" 상태 | Self Switch (A) |
| 다른 맵에도 영향을 주는 상태 | Global Switch (SwitchTable) |
| 보스 처치 여부 | Global Switch (`보스명_defeated`) |
| 상자 열림 여부 | Self Switch (A) — 같은 맵 내 |
| 퀘스트 완료 여부 | Global Switch (`quest_완료명_done`) |
| NPC의 다음 대화 | Self Switch (A 또는 B) |
| 스토리 분기 | Global Switch (`act_N_started`) |

### event_planner 프롬프트에서 Self Switch 안내

```python
SELF_SWITCH_RULES = """
## Self Switch 사용 (같은 이벤트 내 상태)
같은 이벤트(상자, NPC 등)의 "사용됨" 상태는 condition_switch 대신
Self Switch를 사용하세요:

chest 타입의 경우: switch_id 생략 → 자동으로 Self Switch A 사용
npc 타입의 경우: condition_switch 생략 → 항상 표시
                condition_switch: "SELF_A" → Self Switch A 조건 사용

## Global Switch 사용 (다른 이벤트/맵에 영향)
condition_switch: "드래곤_defeated"  ← 사전 할당된 이름 사용
switch_id: "chest_dungeon_2"        ← 새 이름 (컴파일러가 할당)
"""
```

---

## DSL 컴파일러의 Self Switch 처리

Self Switch는 RPG Maker MZ에서 특별히 처리된다:

```python
def compile_chest(event: ChestEvent, compiler: EventCompiler) -> dict:
    switch_name = event.switch_id  # 예: "chest_forest_opened"

    if switch_name == "SELF_A":
        # Self Switch A 사용
        open_cmd  = {"code": 123, "indent": 0, "parameters": ["A", 0]}  # Control Self Switch
        cond_page = _make_conditions(self_switch="A")
    else:
        # Global Switch 사용
        sid = compiler.resolve_switch(switch_name)
        open_cmd  = {"code": 121, "indent": 0, "parameters": [sid, sid, 0]}  # Control Switches ON
        cond_page = _make_conditions(switch_id=sid)

    # 페이지 1: 상자가 열려있지 않을 때 (아이템 획득)
    page1_cmds = [
        {"code": 126, "indent": 0, "parameters": [event.item_id, 0, event.item_type_id, event.amount]},
        open_cmd,
        {"code": 0, "indent": 0, "parameters": []},
    ]
    # 페이지 2: 상자가 열려있을 때 (빈 상자)
    page2_cmds = [
        {"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, "상자"]},
        {"code": 401, "indent": 0, "parameters": ["이미 열린 상자입니다."]},
        {"code": 0, "indent": 0, "parameters": []},
    ]
    return {
        "id": 0, "name": event.name, "note": "",
        "x": event.x, "y": event.y,
        "pages": [
            _make_page(page1_cmds, conditions=_empty_conditions(), image="!Chest", trigger=0),
            _make_page(page2_cmds, conditions=cond_page, image="!Chest", trigger=0),
        ],
    }
```

---

## 스위치 이름 충돌 방지 (R20)

**R20: 병렬 맵 이벤트 기획에서 스위치 이름 중복 시맨틱 충돌**

event_planner가 맵 3개를 `asyncio.gather()`로 병렬 처리할 때,
Map1이 `"door_unlocked"`를 "북쪽 문"에 사용하고
Map2가 같은 이름 `"door_unlocked"`를 "남쪽 문"에 사용하면
두 문이 하나의 스위치를 공유해버린다.

**방지**:
1. event_planner 프롬프트에 **맵 이름 prefix 규칙** 명시:
   ```
   스위치 이름에는 반드시 현재 맵 이름을 prefix로 붙이세요.
   예: "마을_north_door_unlocked", "던전_chest_opened"
   단, 사전 할당된 스위치(드래곤_defeated 등)는 prefix 없이 그대로 사용.
   ```
2. event_compiler에서 컴파일 후 동적 할당된 스위치 목록 검토:
   ```python
   def check_switch_semantic_conflicts(switch_table: SwitchTable) -> list[str]:
       """스위치 이름 중복 또는 의미론적 충돌 검사 (단순 휴리스틱)."""
       warnings = []
       seen_suffixes: dict[str, list[str]] = {}
       for name in switch_table.switches:
           # prefix 제거 후 suffix만 추출
           suffix = name.split("_", 1)[-1] if "_" in name else name
           seen_suffixes.setdefault(suffix, []).append(name)
       for suffix, names in seen_suffixes.items():
           if len(names) > 1 and any("_" not in n for n in names):
               warnings.append(f"스위치 이름 충돌 가능: {names}")
       return warnings
   ```

---

## System.json switches 배열과의 동기화

`integrator.py`의 `build_system_json()`은 `final_switch_table` (컴파일 후)을 받아야 한다.
이를 위해 integrator가 호출되기 전에 `switch_table`이 최신 상태여야 한다.

**워크플로우 순서**:
```
asset_planner → [switch_table 사전 할당]
    ↓
event_planner → [DSL 생성, 스위치 이름 사용]
    ↓
event_compiler → [DSL 컴파일, 스위치 동적 할당]
               → 반환: {compiled_events, switch_table}  ← 최신 switch_table
    ↓
integrator → build_system_json(switch_table=최신)
           → System.json.switches 배열에 전체 스위치 이름 포함
```

`GenerationState`에서 `switch_table`은 **event_compiler 이후에 업데이트**된다:
```python
# workflow.py
graph.add_edge("event_compiler", "integrator")
# event_compiler의 반환값에 switch_table이 포함되어 state가 업데이트됨
# integrator는 최신 switch_table을 state["switch_table"]에서 읽음
```

---

## 요약: SwitchTable 생애주기

```
[asset_planner]
  _build_switch_table(GameSpec)
  → SwitchTable {boss_defeated:1, act_1_started:2, ..., next=7}
         ↓
[event_planner] (읽기만)
  프롬프트에 기존 스위치 목록 주입
  LLM이 스위치 이름으로 DSL 생성
         ↓
[event_compiler] (읽기 + 동적 확장)
  compile_chest → resolve_switch("마을_chest1_opened") → ID 7 할당
  compile_npc   → resolve_switch("마을_quest_started") → ID 8 할당
  → final_switch_table {... "마을_chest1_opened":7, "마을_quest_started":8, next=9}
         ↓
[integrator]
  build_system_json(switch_table=final)
  → System.json.switches = [null, "드래곤_defeated", ..., "마을_chest1_opened", ...]
```
