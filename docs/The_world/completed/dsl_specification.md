# DSL 명세서 — 이벤트 기술 언어

> 관련 노드: F. 이벤트 기획자, G. 이벤트 컴파일러
> 위치: `agent/generation/compilers/`

---

## 개요

RPG Maker MZ의 이벤트 커맨드는 code 번호 + 파라미터 배열 형식으로 구성되어 있어
LLM이 직접 생성하면 오류가 잦다.

대신 LLM이 읽기 쉬운 YAML DSL을 작성하면
`EventCompiler`가 이를 RPG Maker 커맨드로 변환한다.

```
LLM이 작성 (쉬움)          컴파일러가 변환 (정확함)
────────────────────       ──────────────────────
type: npc               →  {"code": 101, ...}
dialogue: ["안녕!"]     →  {"code": 401, ...}
                        →  {"code": 0, ...}
```

---

## DSL 타입 전체 명세

### npc — NPC 대화

```yaml
- x: 8
  y: 3
  name: 여관주인              # 이벤트 이름 (에디터 표시용)
  type: npc
  trigger: action_button     # action_button | player_touch | auto_run
  face_image: Actor1         # 페이스 그래픽 (선택)
  face_index: 0
  dialogue:
    - "어서오세요, 용사여!"
    - "이 마을은 요즘 몬스터 때문에 큰일이에요."
  condition:                 # 선택: 조건부 대화
    switch: town_npc_talked
    value: false
  set_switch: town_npc_talked  # 선택: 대화 후 스위치 ON
```

**컴파일 결과:**
```json
[
  {"code": 111, "parameters": [0, 3, 0]},
  {"code": 101, "parameters": ["Actor1", 0, 0, 2, "여관주인"]},
  {"code": 401, "parameters": ["어서오세요, 용사여!"]},
  {"code": 401, "parameters": ["이 마을은 요즘 몬스터 때문에 큰일이에요."]},
  {"code": 121, "parameters": [3, 3, 0]},
  {"code": 412, "parameters": []},
  {"code": 0,   "parameters": []}
]
```

---

### transfer — 맵 이동

```yaml
- x: 8
  y: 12
  name: 던전_입구
  type: transfer
  trigger: player_touch
  to_map: 어둠의 던전         # id_table에서 map_id로 변환
  to_x: 8
  to_y: 1
  direction: down            # up | down | left | right | retain
  set_switch: dungeon_entered  # 선택
```

**컴파일 결과:**
```json
[
  {"code": 201, "parameters": [0, 2, 8, 1, 2, 0]},
  {"code": 121, "parameters": [1, 1, 0]},
  {"code": 0,   "parameters": []}
]
```

파라미터 순서: `[mode, mapId, x, y, direction, fadeType]`

---

### chest — 보물 상자

```yaml
- x: 14
  y: 5
  name: 보물상자_01
  type: chest
  item: 회복 포션             # id_table에서 item_id로 변환
  item_type: item            # item | weapon | armor | gold
  amount: 2
  one_time: true             # true면 스위치로 중복 방지
  chest_switch: chest_opened_01  # switch_table에서 번호 변환
  dialogue_before: "낡은 상자가 있다."
  dialogue_after: "회복 포션을 2개 손에 넣었다!"
```

**컴파일 결과:**
```json
[
  {"code": 111, "parameters": [0, 4, 1]},
  {"code": 101, "parameters": ["", 0, 0, 2, ""]},
  {"code": 401, "parameters": ["낡은 상자가 있다."]},
  {"code": 126, "parameters": [1, 0, 0, 2]},
  {"code": 401, "parameters": ["회복 포션을 2개 손에 넣었다!"]},
  {"code": 121, "parameters": [4, 4, 0]},
  {"code": 412, "parameters": []},
  {"code": 0,   "parameters": []}
]
```

---

### battle — 전투 이벤트

```yaml
- x: 8
  y: 6
  name: 슬라임_전투
  type: battle
  trigger: player_touch
  troop: 슬라임_무리          # id_table에서 troop_id로 변환
  escape_allowed: true
  lose_condition: game_over  # game_over | continue
  on_win:
    - give_item: { item: 회복 포션, amount: 1 }
    - give_exp: 50
    - set_switch: slime_defeated
  one_time: true             # 한 번 이기면 다시 발생 안 함
  battle_switch: slime_group_01
```

**컴파일 결과:**
```json
[
  {"code": 111, "parameters": [0, 5, 1]},
  {"code": 301, "parameters": [0, 1, true, false, true]},
  {"code": 601, "parameters": []},
  {"code": 126, "parameters": [1, 0, 0, 1]},
  {"code": 121, "parameters": [3, 3, 0]},
  {"code": 602, "parameters": []},
  {"code": 603, "parameters": []},
  {"code": 412, "parameters": []},
  {"code": 0,   "parameters": []}
]
```

---

### shop — 상점

```yaml
- x: 11
  y: 4
  name: 무기상점
  type: shop
  trigger: action_button
  dialogue: "어서오세요! 좋은 무기가 많습니다."
  items:
    - { item: 철검, item_type: weapon }
    - { item: 가죽 방패, item_type: armor }
    - { item: 회복 포션, item_type: item }
  purchase_only: false       # true면 판매 불가
```

**컴파일 결과:**
```json
[
  {"code": 101, "parameters": ["", 0, 0, 2, "무기상점"]},
  {"code": 401, "parameters": ["어서오세요! 좋은 무기가 많습니다."]},
  {"code": 302, "parameters": [0, 1, 0, 0, 0, false]},
  {"code": 605, "parameters": [2, 1, 0]},
  {"code": 605, "parameters": [2, 2, 0]},
  {"code": 605, "parameters": [1, 1, 0]},
  {"code": 0,   "parameters": []}
]
```

---

### condition — 조건 분기 ⚠️ Phase 5 (미구현)

> **주의**: Pydantic 모델 없음, EventCompiler.compile()에 핸들러 없음.
> 엔딩 시퀀스는 `ending` 타입으로 대체. 조건 분기는 Phase 5에서 구현 예정.

```yaml
- x: 0
  y: 0
  name: 마왕처치_확인
  type: condition
  trigger: auto_run
  condition:
    switch: boss_defeated
    value: true
  on_true:
    - type: dialogue
      text: "마왕을 쓰러뜨렸다! 마을에 평화가 찾아왔다."
    - type: set_switch
      switch: ending_triggered
  on_false:
    - type: dialogue
      text: "아직 마왕이 살아있다..."
```

---

### sign — 안내판 (읽기 전용 NPC) ⚠️ Phase 5 (미구현)

> **주의**: Pydantic 모델 없음, EventCompiler.compile()에 핸들러 없음.
> Phase 4에서는 `npc` 타입으로 대체 가능. Phase 5에서 구현 예정.

```yaml
- x: 5
  y: 8
  name: 마을_안내판
  type: sign
  trigger: action_button
  text:
    - "→ 북쪽: 던전 입구"
    - "← 서쪽: 여관"
```

---

## 컴파일러 구현 상세

### 이름 → ID 변환 (id_table, switch_table 참조)

```python
class EventCompiler:
    def __init__(self, id_table: IdTable, switch_table: SwitchTable):
        self.id_table = id_table
        self.switch_table = switch_table

    def resolve_map_id(self, name: str) -> int:
        if name not in self.id_table.maps:
            raise CompileError(f"맵 '{name}'을 id_table에서 찾을 수 없음")
        return self.id_table.maps[name]

    def resolve_item_id(self, name: str) -> int:
        # item / weapon / armor 통합 검색
        for table in [self.id_table.items, self.id_table.weapons, self.id_table.armors]:
            if name in table:
                return table[name]
        raise CompileError(f"아이템 '{name}'을 id_table에서 찾을 수 없음")

    def resolve_switch_id(self, name: str) -> int:
        if name not in self.switch_table.switches:
            # 없으면 새로 할당 — SwitchTable은 불변이므로 model_copy() 사용
            # allocate_switch()는 (new_table, new_id) 튜플 반환 (switch_allocation.md)
            self.switch_table, _ = self.switch_table.allocate_switch(name)
        return self.switch_table.switches[name]

    def compile(self, dsl_event: DslEvent) -> list[dict]:
        match dsl_event.type:
            case "npc":      return self._compile_npc(dsl_event)
            case "transfer": return self._compile_transfer(dsl_event)
            case "chest":    return self._compile_chest(dsl_event)
            case "battle":   return self._compile_battle(dsl_event)
            case "shop":     return self._compile_shop(dsl_event)
            case "ending":   return self._compile_ending(dsl_event)  # game_ending_design.md
            case _:          raise CompileError(f"미지원 타입: {dsl_event.type}")
```

### 파싱 실패 처리

```python
def parse_dsl_safe(raw_yaml: str, map_id: int) -> list[DslEvent] | None:
    """
    파싱 실패 시 None 반환 (예외 발생 안 함).
    호출자가 재시도 여부 결정.
    """
    try:
        data = yaml.safe_load(raw_yaml)
        events = data.get("events", [])
        return [parse_event(e) for e in events]
    except (yaml.YAMLError, ValidationError) as e:
        logger.warning("DSL 파싱 실패 map_id=%d: %s", map_id, e)
        return None
```

---

## RPG Maker MZ 주요 커맨드 코드 참조

| 코드 | 기능 | 주요 파라미터 |
|------|------|------------|
| 101 | Show Text (대화 시작) | face, faceIndex, background, position, name |
| 401 | Text Data (대화 내용) | text |
| 102 | Show Choices (선택지) | choices[], cancelType |
| 402 | When [Choice] | index |
| 111 | If (조건 분기) | type, value |
| 411 | Else | - |
| 412 | End If | - |
| 121 | Control Switches | [id_start, id_end, value] (0=OFF,1=ON,2=Toggle) |
| 122 | Control Variables | [id_start, id_end, op, operand_type, operand] |
| 123 | Control Self Switches | ["A"\|"B"\|"C"\|"D", 0\|1] |
| 125 | Change Gold | [inc_or_dec, operand_type, amount] |
| 126 | Change Items | [item_id, inc_or_dec, operand_type, amount] |
| 127 | Change Weapons | [weapon_id, inc_or_dec, operand_type, amount, include_equipped] |
| 128 | Change Armors | [armor_id, inc_or_dec, operand_type, amount, include_equipped] |
| 201 | Transfer Player | [mode, map_id, x, y, direction, fade_type] |
| 221 | Fadeout Screen | [] |
| 222 | Fadein Screen | [] |
| 230 | Wait | [frames] |
| 301 | Battle Processing | [mode, troop_id, can_escape, can_lose] (MZ 1.6+: 5번째 파라미터 선택) |
| 302 | Shop Processing | [goods_type, goods_id, price_type, price] |
| 353 | **Game Over** | [] |
| 354 | **Return to Title** (Game Over 아님!) | [] |
| 601 | If Win (전투 승리) | [] |
| 602 | If Escape (도주) | [] |
| 603 | If Lose (패배) | [] |
| 604 | End Battle Processing | [] |
| 605 | Shop Item (추가 상품) | [goods_type, goods_id, price_type, price] |
| 0   | Event End | [] |
| (상세 파라미터는 event_command_complete.md 참조) | | |
