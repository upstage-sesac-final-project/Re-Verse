# RPG Maker MZ 이벤트 커맨드 완전 레퍼런스

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 주의: dsl_specification.md 오류 수정

`dsl_specification.md`의 커맨드 코드 표에 다음 오류가 있다:

| 기존 기록 | 실제 |
|-----------|------|
| `354 | Game Over` | **354 = Return to Title**, 353 = Game Over |
| `121 | id, value` | **[id_start, id_end, value]** (3개 파라미터) |
| `301 | troopId, canEscape, canLose` | **5개 파라미터** (아래 참조) |

이 문서가 기준이다. 코드 작성 시 반드시 이 문서를 참조할 것.

---

## 1. 텍스트/대화

### 101 — Show Text (메시지 창 시작)

```python
{"code": 101, "indent": 0, "parameters": [
    face_name,       # str: 얼굴 이미지 파일명 ("Actor1", "" 등)
    face_index,      # int: 얼굴 이미지 인덱스 0~7
    background,      # int: 0=일반창, 1=어두운창, 2=투명
    position,        # int: 0=하단, 1=중앙, 2=상단
    speaker_name,    # str: 화자 이름 표시 (RPG MZ 1.6.0+)
]}
```

### 401 — Text Data (메시지 본문, 101 뒤에 여러 개)

```python
{"code": 401, "indent": 0, "parameters": [text_line]}  # str
```

**NPC 2줄 대화 예시:**
```python
[
    {"code": 101, "indent": 0, "parameters": ["Actor1", 0, 0, 2, "해럴드"]},
    {"code": 401, "indent": 0, "parameters": ["안녕하세요!"]},
    {"code": 401, "indent": 0, "parameters": ["오늘도 모험을 떠나시나요?"]},
    {"code": 0,   "indent": 0, "parameters": []},  # 이벤트 종료
]
```

---

## 2. 선택지

### 102 — Show Choices

```python
{"code": 102, "indent": 0, "parameters": [
    choices,          # list[str]: 선택지 텍스트 목록 (최대 6개)
    cancel_type,      # int: -1=취소불가, 0~5=취소시 해당 인덱스로, 5=분기없음
    default_type,     # int: 기본 선택 인덱스 (0~)
    position_type,    # int: 0=좌, 1=중, 2=우
    background,       # int: 0=일반, 1=어두운, 2=투명
]}
```

### 402 — When [Choice]

```python
{"code": 402, "indent": 0, "parameters": [choice_index, choice_text]}
```

### 404 — End (선택지 종료)

```python
{"code": 404, "indent": 0, "parameters": []}
```

---

## 3. 조건 분기

### 111 — Conditional Branch (If)

```python
{"code": 111, "indent": 0, "parameters": [
    condition_type,  # int: 타입 코드 (아래 표)
    *type_params,    # condition_type에 따라 다른 추가 파라미터
]}
```

**condition_type 값:**

| type | 의미 | 추가 파라미터 |
|------|------|-------------|
| 0 | 스위치 ON/OFF | `[switch_id, 0]` (0=ON, 1=OFF) |
| 1 | 변수 값 비교 | `[variable_id, 0, compare_op, value]` (0=상수) |
| 2 | Self Switch | `[self_switch_ch, 0]` (ch="A"~"D") |
| 3 | 타이머 | `[timer_sec, 0]` (0=이상, 1=이하) |
| 4 | 액터 파티 참가 여부 | `[actor_id]` |
| 12 | 골드 | `[amount, 0]` (0=이상, 1=이하) |
| 13 | 아이템 소지 여부 | `[item_id]` |

**스위치 조건 예시 (switch_id=3이 ON인 경우):**
```python
{"code": 111, "indent": 0, "parameters": [0, 3, 0]}
# condition_type=0, switch_id=3, 0=ON
```

### 411 — Else

```python
{"code": 411, "indent": 1, "parameters": []}
```

### 412 — End If

```python
{"code": 412, "indent": 0, "parameters": []}
```

**Full conditional branch structure:**
```python
[
    {"code": 111, "indent": 0, "parameters": [0, 3, 0]},  # If switch 3 = ON
    {"code": 101, "indent": 1, "parameters": ["Actor1", 0, 0, 2, "NPC"]},
    {"code": 401, "indent": 1, "parameters": ["드래곤이 쓰러졌군요!"]},
    {"code": 411, "indent": 0, "parameters": []},          # Else
    {"code": 101, "indent": 1, "parameters": ["Actor1", 0, 0, 2, "NPC"]},
    {"code": 401, "indent": 1, "parameters": ["드래곤을 처치해주세요."]},
    {"code": 412, "indent": 0, "parameters": []},          # End If
    {"code": 0,   "indent": 0, "parameters": []},
]
```

> **indent 주의**: If 블록 내부의 명령들은 `indent: 1`이어야 한다.
> 중첩 If는 `indent: 2`까지 가능.

---

## 4. 스위치/변수 제어

### 121 — Control Switches

```python
{"code": 121, "indent": 0, "parameters": [
    switch_id_start,  # int: 시작 스위치 ID
    switch_id_end,    # int: 종료 스위치 ID (단일 스위치면 start와 동일)
    value,            # int: 0=OFF, 1=ON, 2=Toggle
]}
```

**스위치 1개 ON으로 설정 (id=3):**
```python
{"code": 121, "indent": 0, "parameters": [3, 3, 1]}  # switch 3 ON
```

**스위치 1~3 모두 OFF:**
```python
{"code": 121, "indent": 0, "parameters": [1, 3, 0]}
```

### 122 — Control Variables

```python
{"code": 122, "indent": 0, "parameters": [
    variable_id_start,
    variable_id_end,
    operation,    # int: 0=대입, 1=더하기, 2=빼기, 3=곱하기, 4=나누기, 5=나머지
    operand_type, # int: 0=상수, 1=변수, 2=랜덤, 3=게임데이터, 4=스크립트
    operand,      # int: operand_type에 따라 다른 값
    *extra,       # operand_type=2(랜덤)이면 [min, max]
]}
```

### 123 — Control Self Switches

```python
{"code": 123, "indent": 0, "parameters": [
    self_switch_ch,  # str: "A", "B", "C", "D"
    value,           # int: 0=OFF, 1=ON
]}
```

**상자 이벤트에서 Self Switch A를 ON으로:**
```python
{"code": 123, "indent": 0, "parameters": ["A", 1]}
```

---

## 5. 아이템/무기/방어구 제어

### 126 — Change Items

```python
{"code": 126, "indent": 0, "parameters": [
    item_id,       # int: Items.json의 ID
    inc_or_dec,    # int: 0=증가, 1=감소
    operand_type,  # int: 0=상수, 1=변수
    operand,       # int: 수량 (operand_type=0) 또는 변수 ID (operand_type=1)
]}
```

### 127 — Change Weapons

```python
{"code": 127, "indent": 0, "parameters": [
    weapon_id,     # int: Weapons.json의 ID
    inc_or_dec,    # int: 0=증가, 1=감소
    operand_type,  # int: 0=상수, 1=변수
    operand,       # int
    include_equipped,  # bool: 장착 중인 것도 포함 (True/False)
]}
```

### 128 — Change Armors

```python
{"code": 128, "indent": 0, "parameters": [
    armor_id, inc_or_dec, operand_type, operand, include_equipped
]}
```

**컴파일러에서 item_type 분기:**
```python
ITEM_TYPE_TO_CODE = {
    "item":   126,
    "weapon": 127,
    "armor":  128,
}

def compile_give_item(
    item_type: str, item_id: int, amount: int = 1
) -> dict:
    code = ITEM_TYPE_TO_CODE[item_type]
    params = [item_id, 0, 0, amount]  # 증가, 상수, amount
    if item_type in ("weapon", "armor"):
        params.append(False)  # include_equipped=False
    return {"code": code, "indent": 0, "parameters": params}
```

### 125 — Change Gold

```python
{"code": 125, "indent": 0, "parameters": [
    inc_or_dec,    # int: 0=증가, 1=감소
    operand_type,  # int: 0=상수, 1=변수
    operand,       # int
]}
```

---

## 6. 이동/전투/상점

### 201 — Transfer Player

```python
{"code": 201, "indent": 0, "parameters": [
    mode,       # int: 0=직접지정, 1=변수로지정
    map_id,     # int: 목적지 맵 ID
    x,          # int: 목적지 X 좌표
    y,          # int: 목적지 Y 좌표
    direction,  # int: 0=유지, 2=하, 4=좌, 6=우, 8=상
    fade_type,  # int: 0=검은화면, 1=흰화면, 2=없음
]}
```

### 301 — Battle Processing

```python
{"code": 301, "indent": 0, "parameters": [
    mode,             # int: 0=직접지정, 1=변수로지정, 2=랜덤인카운터
    troop_id,         # int: Troops.json의 troop ID (mode=0일 때)
    can_escape,       # bool: 도주 가능 여부
    can_lose,         # bool: 패배 허용 여부
    # RPG MZ 1.6+ 추가 파라미터:
    # background, background_name (선택적)
]}
```

**보스 전투 (도주 불가, 패배 불가):**
```python
{"code": 301, "indent": 0, "parameters": [0, boss_troop_id, False, False]}
```

**일반 전투 (도주 가능):**
```python
{"code": 301, "indent": 0, "parameters": [0, troop_id, True, False]}
```

### 601/602/603/604 — Battle Result 분기

```python
{"code": 601, "indent": 0, "parameters": []},  # If Win
# ... 승리 처리 커맨드 (indent: 1) ...
{"code": 602, "indent": 0, "parameters": []},  # If Escape
# ... 도주 처리 커맨드 (indent: 1) ...
{"code": 603, "indent": 0, "parameters": []},  # If Lose (can_lose=true일 때)
# ... 패배 처리 커맨드 (indent: 1) ...
{"code": 604, "indent": 0, "parameters": []},  # End Battle Processing
```

### 302 — Shop Processing

```python
{"code": 302, "indent": 0, "parameters": [
    goods_type,   # int: 0=item, 1=weapon, 2=armor
    goods_id,     # int
    price_type,   # int: 0=기본가격, 1=지정가격
    price,        # int: price_type=1일 때 사용
]}
```

뒤에 추가 상품은 605 코드로:
```python
{"code": 605, "indent": 0, "parameters": [goods_type, goods_id, price_type, price]}
```

---

## 7. 화면 효과/이동

### 221 — Fadeout Screen

```python
{"code": 221, "indent": 0, "parameters": []}
```

### 222 — Fadein Screen

```python
{"code": 222, "indent": 0, "parameters": []}
```

### 230 — Wait

```python
{"code": 230, "indent": 0, "parameters": [frames]}  # int: 프레임 수 (60 = 1초)
```

---

## 8. 게임 흐름

### 353 — Game Over (**353**, NOT 354)

```python
{"code": 353, "indent": 0, "parameters": []}
```

### 354 — Return to Title Screen (**354**, NOT Game Over)

```python
{"code": 354, "indent": 0, "parameters": []}
```

> **⚠️ 중요**: `dsl_specification.md`의 기존 표에서 354를 "Game Over"로 잘못 기술.
> 올바른 것: 353=Game Over, 354=Return to Title.

---

## 9. 이벤트 종료

### 0 — Event End (모든 커맨드 목록 마지막에 필수)

```python
{"code": 0, "indent": 0, "parameters": []}
```

---

## 10. 트루프 이름 규칙

`generate_troops()`가 생성하는 트루프 이름과 event_planner가 DSL에 쓰는 이름이 일치해야 한다.

### 명명 규칙

```python
def _troop_name(enemy_name: str, count: int, tier: str) -> str:
    """
    트루프 이름 생성 규칙 (generate_troops와 event_planner DSL이 동일하게 사용).
    id_table.troops의 키가 되는 이름.
    """
    if tier == "boss":
        # 보스: 항상 단독, 이름 그대로 사용
        return enemy_name                    # "드래곤"
    elif count == 1:
        return f"{enemy_name}_단독"          # "슬라임_단독"
    else:
        return f"{enemy_name}_×{count}"     # "슬라임_×2"
```

**generate_troops() 업데이트:**
```python
def generate_troops(enemies: list[dict], id_table: IdTable) -> list[dict | None]:
    troops: list[dict | None] = [None]
    for enemy in enemies:
        enemy_id = id_table.get_id("enemies", enemy["name"])
        tier = _detect_tier(enemy)
        name = enemy["name"]

        if tier == "boss":
            troop_name = _troop_name(name, 1, "boss")  # "드래곤"
            troops.append(_make_troop(len(troops), troop_name, [_make_member(enemy_id, 408, 312)]))
        else:
            for count in [1, 2, 3]:
                troop_name = _troop_name(name, count, tier)  # "슬라임_단독", "슬라임_×2" 등
                positions = BATTLE_POSITIONS[count]
                troops.append(_make_troop(
                    len(troops), troop_name,
                    [_make_member(enemy_id, x, y) for x, y in positions],
                ))
    return troops
```

**event_planner 프롬프트에서 사용 가능한 트루프 이름 제공:**
```python
def _format_troop_list(switch_table: SwitchTable, id_table: IdTable) -> str:
    """event_planner에 주입할 트루프 이름 목록."""
    lines = ["## 사용 가능한 트루프 (battle 이벤트의 troop_id에 이름 그대로 사용)"]
    for name, tid in sorted(id_table.troops.items(), key=lambda x: x[1]):
        lines.append(f"  - {name} (id={tid})")
    return "\n".join(lines)
```

### EventCompiler의 troop 이름 해석

```python
def resolve_troop_id(self, name: str) -> int:
    """
    트루프 이름 → ID.
    1. 정확한 이름 매칭 우선
    2. 없으면 적 이름으로 부분 매칭 (보스 이름만 쓴 경우 처리)
    """
    if name in self.id_table.troops:
        return self.id_table.troops[name]

    # 보스 이름으로 부분 매칭 (LLM이 "드래곤"만 쓴 경우 → "드래곤" 트루프 찾기)
    candidates = [
        (tname, tid)
        for tname, tid in self.id_table.troops.items()
        if tname == name or tname.startswith(name)
    ]
    if len(candidates) == 1:
        return candidates[0][1]
    if len(candidates) > 1:
        # 보스 (단독) 우선: "_단독" 없는 것 = 보스
        boss_candidates = [(t, tid) for t, tid in candidates if "_단독" not in t and "_×" not in t]
        if boss_candidates:
            return boss_candidates[0][1]
        return candidates[0][1]

    raise CompileError(f"트루프 '{name}'을 찾을 수 없음. 사용 가능: {list(self.id_table.troops.keys())}")
```

---

## 11. 완전한 BattleEvent 컴파일 예시

```python
def compile_battle(event: BattleEvent, compiler: EventCompiler) -> dict:
    troop_id = compiler.resolve_troop_id(event.troop_id)
    defeat_sid = compiler.resolve_switch(event.defeat_switch_id)

    battle_cmd = {
        "code": 301, "indent": 0,
        "parameters": [0, troop_id, event.can_escape, False],
    }
    win_cmds = [
        {"code": 601, "indent": 0, "parameters": []},              # If Win
        {"code": 121, "indent": 1, "parameters": [defeat_sid, defeat_sid, 1]},  # Switch ON
        {"code": 604, "indent": 0, "parameters": []},              # End Battle
    ]
    escape_cmds = [
        {"code": 602, "indent": 0, "parameters": []},              # If Escape
        # 도주 시 아무것도 안 함 (스위치 켜지 않음)
    ] if event.can_escape else []

    all_cmds = [battle_cmd] + win_cmds + escape_cmds + [
        {"code": 0, "indent": 0, "parameters": []},
    ]

    return _wrap_event(event.name, event.x, event.y, trigger=0, cmds=all_cmds)
```

---

## 12. 완전한 ChestEvent 컴파일 예시

```python
def compile_chest(event: ChestEvent, compiler: EventCompiler) -> dict:
    item_code = ITEM_TYPE_TO_CODE[event.item_type]
    item_params = [event.item_id, 0, 0, event.amount]
    if event.item_type in ("weapon", "armor"):
        item_params.append(False)

    # 페이지 1: 상자 미개봉 → 아이템 지급 + Self Switch A ON
    page1_cmds = [
        {"code": item_code,  "indent": 0, "parameters": item_params},
        {"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]},
        {"code": 401, "indent": 0, "parameters": [f"{event.item_type} 획득!"]},
        {"code": 123, "indent": 0, "parameters": ["A", 1]},  # Self Switch A ON
        {"code": 0,   "indent": 0, "parameters": []},
    ]
    # 페이지 2: Self Switch A = ON → 빈 상자 메시지
    page2_cmds = [
        {"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]},
        {"code": 401, "indent": 0, "parameters": ["빈 상자입니다."]},
        {"code": 0,   "indent": 0, "parameters": []},
    ]

    return {
        "id": 0, "name": event.name, "note": "",
        "x": event.x, "y": event.y,
        "pages": [
            _make_page(page1_cmds, _empty_conditions(), image="!Chest", trigger=0),
            _make_page(page2_cmds, _self_switch_condition("A"), image="!Chest", trigger=0),
        ],
    }

def _self_switch_condition(ch: str) -> dict:
    return {
        "actorId": 1, "actorValid": False,
        "itemId": 1, "itemValid": False,
        "selfSwitchCh": ch, "selfSwitchValid": True,
        "switch1Id": 1, "switch1Valid": False,
        "switch2Id": 1, "switch2Valid": False,
        "variableId": 1, "variableValid": False, "variableValue": 0,
    }
```

---

## 빠른 참조 요약

| 코드 | 기능 | 파라미터 배열 예시 |
|------|------|-----------------|
| 0 | Event End | `[]` |
| 101 | ShowText Header | `["Actor1", 0, 0, 2, "이름"]` |
| 401 | ShowText Content | `["텍스트"]` |
| 102 | Show Choices | `[["예","아니오"], -1, 0, 2, 0]` |
| 111 | Conditional Branch | `[0, switch_id, 0]` (스위치 ON 조건) |
| 121 | Control Switches | `[id, id, 1]` (ON) |
| 123 | Control Self Switch | `["A", 1]` (ON) |
| 125 | Change Gold | `[0, 0, 100]` (+100골드) |
| 126 | Change Items | `[item_id, 0, 0, 1]` (+1개) |
| 127 | Change Weapons | `[weapon_id, 0, 0, 1, False]` |
| 128 | Change Armors | `[armor_id, 0, 0, 1, False]` |
| 201 | Transfer Player | `[0, map_id, x, y, 0, 0]` |
| 221 | Fadeout Screen | `[]` |
| 222 | Fadein Screen | `[]` |
| 230 | Wait | `[60]` (1초) |
| 301 | Battle Processing | `[0, troop_id, True, False]` |
| 353 | **Game Over** | `[]` |
| 354 | **Return to Title** | `[]` |
| 401 | TextData | `["텍스트"]` |
| 601 | If Win | `[]` |
| 602 | If Escape | `[]` |
| 603 | If Lose | `[]` |
| 604 | End Battle | `[]` |
| 605 | Shop Item | `[type, id, 0, 0]` |
