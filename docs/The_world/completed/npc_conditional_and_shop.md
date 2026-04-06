# NPC 조건부 대화 & 상점 컴파일러 상세

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06
> 관련 문서: dsl_specification.md, event_command_complete.md

---

## 1. NPC 조건부 대화 — 2-페이지 패턴

### 문제

NPC는 게임 진행 상황에 따라 다른 대사를 해야 한다:
- 보스 처치 전: "아직 드래곤이 살아있다니…"
- 보스 처치 후: "당신 덕분에 마을이 평화로워졌어요!"

RPG Maker MZ에는 두 가지 구현 방법이 있다:
1. **인-이벤트 if/else**: 코드 111 (If) + 411 (Else) + 412 (End If)
2. **2-페이지 패턴**: 페이지1(조건 없음) + 페이지2(스위치 조건)

### 선택: 2-페이지 패턴

| 방식 | 장점 | 단점 |
|------|------|------|
| 인-이벤트 if/else | 페이지 구조 단순 | 코드 111/411/412 들여쓰기 복잡 |
| 2-페이지 패턴 (채택) | 페이지 조건이 RPG Maker 네이티브 | 페이지 2개 생성 필요 |

**이유**: RPG Maker MZ의 페이지 시스템은 조건 스위치가 ON이면 **더 높은 페이지(숫자 큰 쪽)가 우선 실행**된다. 이를 이용하면 이벤트 내부 분기 없이 상태 전환이 가능하다.

---

### DSL 확장: `NpcEvent.alt_dialogue`

```yaml
# event_planner가 생성하는 DSL 예시

- type: npc
  name: 마을_주민
  x: 8
  y: 6
  trigger: action_button
  face_image: People1
  face_index: 2
  dialogue:
    - "아직 드래곤이 살아있다니…"
    - "용사님, 부탁드립니다."
  # 선택 필드: 스위치 ON일 때 대체 대화
  condition_switch: 드래곤_defeated   # switch_table에서 ID 변환
  alt_dialogue:
    - "당신 덕분에 마을에 평화가 찾아왔어요!"
    - "정말 감사합니다, 용사님."
```

**Pydantic 스키마 추가:**

```python
class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str
    x: int
    y: int
    trigger: str = "action_button"
    face_image: str = ""
    face_index: int = 0
    dialogue: list[str]
    # 조건부 대화 (선택)
    condition_switch: str | None = None   # 스위치 이름 → ID 변환
    alt_dialogue: list[str] | None = None  # condition_switch ON일 때 대화
    set_switch: str | None = None          # 대화 후 스위치 ON
```

---

### `compile_npc()` — 2-페이지 구현

```python
def compile_npc(event: NpcEvent, compiler: EventCompiler) -> dict:
    """
    NpcEvent → RPG Maker MZ 이벤트 JSON (페이지 1~2).

    페이지 1: 기본 대화 (조건 없음, 항상 실행 가능)
    페이지 2: alt_dialogue가 있는 경우, condition_switch=ON일 때 우선 실행
    """
    pages = []

    # --- 페이지 1: 기본 대화 ---
    page1_cmds = _build_dialogue_commands(
        face_image=event.face_image,
        face_index=event.face_index,
        speaker=event.name,
        lines=event.dialogue,
    )
    if event.set_switch:
        sw_id = compiler.resolve_switch(event.set_switch)
        page1_cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})
    page1_cmds.append({"code": 0, "indent": 0, "parameters": []})

    pages.append(_make_page(
        cmds=page1_cmds,
        conditions=_empty_conditions(),
        trigger=_trigger_code(event.trigger),
        direction_fix=True,
    ))

    # --- 페이지 2: 조건부 대화 (alt_dialogue 있는 경우에만) ---
    if event.condition_switch and event.alt_dialogue:
        cond_sw_id = compiler.resolve_switch(event.condition_switch)

        page2_cmds = _build_dialogue_commands(
            face_image=event.face_image,
            face_index=event.face_index,
            speaker=event.name,
            lines=event.alt_dialogue,
        )
        page2_cmds.append({"code": 0, "indent": 0, "parameters": []})

        pages.append(_make_page(
            cmds=page2_cmds,
            conditions=_make_switch_condition(cond_sw_id),
            trigger=_trigger_code(event.trigger),
            direction_fix=True,
        ))

    return {
        "id": 0,          # integrator가 최종 ID 할당
        "name": event.name,
        "note": "",
        "x": event.x,
        "y": event.y,
        "pages": pages,
    }


def _build_dialogue_commands(
    face_image: str,
    face_index: int,
    speaker: str,
    lines: list[str],
) -> list[dict]:
    """ShowText 커맨드 시퀀스 생성 (101 + 401×N)."""
    cmds = []
    # 최대 4줄씩 메시지 창 1개로 묶음
    for chunk_start in range(0, len(lines), 4):
        chunk = lines[chunk_start:chunk_start + 4]
        cmds.append({
            "code": 101,
            "indent": 0,
            "parameters": [face_image, face_index, 0, 2, speaker],
            # parameters: [face_name, face_index, background(0=창), position(2=하단), speaker_name]
        })
        for line in chunk:
            cmds.append({"code": 401, "indent": 0, "parameters": [line]})
    return cmds
```

---

### 페이지 조건 구조 (`_make_switch_condition`)

RPG Maker MZ 이벤트 페이지의 `conditions` 필드:

```python
def _make_switch_condition(switch_id: int) -> dict:
    """스위치 ID가 ON일 때 페이지 활성화 조건."""
    return {
        "actorId": 1,
        "actorValid": False,
        "itemId": 1,
        "itemValid": False,
        "selfSwitchCh": "A",
        "selfSwitchValid": False,
        "switch1Id": switch_id,
        "switch1Valid": True,   # ← 핵심
        "switch2Id": 1,
        "switch2Valid": False,
        "variableId": 1,
        "variableValid": False,
        "variableValue": 0,
    }

def _empty_conditions() -> dict:
    """조건 없음 (항상 실행)."""
    return {
        "actorId": 1, "actorValid": False,
        "itemId": 1, "itemValid": False,
        "selfSwitchCh": "A", "selfSwitchValid": False,
        "switch1Id": 1, "switch1Valid": False,
        "switch2Id": 1, "switch2Valid": False,
        "variableId": 1, "variableValid": False,
        "variableValue": 0,
    }
```

---

## 2. 상점 컴파일러 — `compile_shop()` 전체 구현

### DSL 복습

```yaml
- type: shop
  name: 무기상점
  x: 11
  y: 4
  trigger: action_button
  dialogue: "어서오세요! 좋은 무기가 많습니다."
  items:
    - { item: 철검, item_type: weapon }
    - { item: 가죽 방패, item_type: armor }
    - { item: 회복 포션, item_type: item }
  purchase_only: false
```

### RPG Maker MZ 상점 커맨드 구조

```
302: Shop Processing (첫 상품 + 상점 설정)
  parameters: [goods_type, goods_id, price_type, price, purchase_only, False]

605: Shop Item (추가 상품, 302 바로 다음에 연속)
  parameters: [goods_type, goods_id, price_type, price]

0:  Event End
```

`goods_type`: 0=item, 1=weapon, 2=armor, 3=gold (gold는 사용 안 함)
`price_type`: 0=기본가격, 1=직접 지정 → Full Generation에서는 항상 0 사용

### `compile_shop()` 전체 구현

```python
ITEM_TYPE_TO_GOODS_CODE = {
    "item":   0,
    "weapon": 1,
    "armor":  2,
}

def compile_shop(event: ShopEvent, compiler: EventCompiler) -> list[dict]:
    """
    ShopEvent → RPG Maker MZ 커맨드 리스트.

    반환: [선택적 대화, 302, 605×N, 0]
    """
    if not event.items:
        raise CompileError(f"상점 '{event.name}'에 상품이 없음")

    cmds: list[dict] = []

    # 1. 선택적 사전 대화
    if event.dialogue:
        cmds.append({
            "code": 101,
            "indent": 0,
            "parameters": ["", 0, 0, 2, event.name],
        })
        cmds.append({
            "code": 401,
            "indent": 0,
            "parameters": [event.dialogue],
        })

    # 2. 첫 번째 상품: 코드 302 (상점 시작 + 첫 아이템)
    first = event.items[0]
    goods_type = ITEM_TYPE_TO_GOODS_CODE.get(first.item_type, 0)
    goods_id   = compiler.resolve_item_id(first.item)
    purchase_flag = 1 if event.purchase_only else 0

    cmds.append({
        "code": 302,
        "indent": 0,
        "parameters": [goods_type, goods_id, 0, 0, purchase_flag, False],
        # [goods_type, goods_id, price_type=0(기본), price=0, purchase_only, ??]
    })

    # 3. 추가 상품: 코드 605 (302 바로 뒤, 연속)
    for item_spec in event.items[1:]:
        gtype = ITEM_TYPE_TO_GOODS_CODE.get(item_spec.item_type, 0)
        gid   = compiler.resolve_item_id(item_spec.item)
        cmds.append({
            "code": 605,
            "indent": 0,
            "parameters": [gtype, gid, 0, 0],
        })

    # 4. 이벤트 종료
    cmds.append({"code": 0, "indent": 0, "parameters": []})

    return cmds
```

### compile_shop 결과 예시 (위 DSL 기준)

```json
[
  {"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, "무기상점"]},
  {"code": 401, "indent": 0, "parameters": ["어서오세요! 좋은 무기가 많습니다."]},
  {"code": 302, "indent": 0, "parameters": [1, 2, 0, 0, 0, false]},
  {"code": 605, "indent": 0, "parameters": [2, 1, 0, 0]},
  {"code": 605, "indent": 0, "parameters": [0, 1, 0, 0]},
  {"code": 0,   "indent": 0, "parameters": []}
]
```

---

## 3. `resolve_item_id()` 확장 — 무기/방어구 통합 검색

상점은 item/weapon/armor를 모두 다루므로 `resolve_item_id()`는 세 테이블을 모두 검색해야 한다:

```python
def resolve_item_id(self, name: str, item_type: str | None = None) -> int:
    """
    아이템 이름 → ID 변환.
    item_type이 주어지면 해당 테이블만 검색 (빠름).
    없으면 item → weapon → armor 순서로 검색.
    """
    if item_type == "item" or item_type is None:
        if name in self.id_table.items:
            return self.id_table.items[name]
    if item_type == "weapon" or item_type is None:
        if name in self.id_table.weapons:
            return self.id_table.weapons[name]
    if item_type == "armor" or item_type is None:
        if name in self.id_table.armors:
            return self.id_table.armors[name]
    raise CompileError(f"아이템 '{name}' (type={item_type})을 id_table에서 찾을 수 없음")
```

---

## 4. ShopEvent와 2-페이지 NPC의 이벤트 JSON 구조 비교

| 특징 | NpcEvent (조건부) | ShopEvent |
|------|-----------------|-----------|
| 페이지 수 | 1 (기본) 또는 2 (alt_dialogue 있으면) | 1 |
| 페이지 조건 | 페이지 2: switch1Valid=True | 없음 |
| 커맨드 구성 | 101+401×N | 선택적 101+401, 302, 605×N |
| 이벤트 ID | integrator가 할당 | integrator가 할당 |
| trigger | action_button (기본) | action_button (기본) |

---

## 5. 리스크

### R-NS1: alt_dialogue 없이 condition_switch만 있는 경우 (P2)

DSL에 `condition_switch: X`만 있고 `alt_dialogue`가 없으면 페이지 2가 생성되지 않는다.
컴파일러는 이를 조용히 무시하고 1-페이지 이벤트만 생성한다.

**완화**: DSL 파서에서 경고:
```python
if event.condition_switch and not event.alt_dialogue:
    logger.warning("NpcEvent '%s': condition_switch 있지만 alt_dialogue 없음", event.name)
```

### R-NS2: 상점 상품 ID 불일치 (P1)

`item_type: weapon`으로 지정했는데 `id_table.items`에만 존재하는 경우:
`resolve_item_id("철검", "weapon")` → CompileError.

**완화**: event_planner 프롬프트에 아이템 타입 명시 지침 추가.
컴파일러에서 CompileError → validator가 포착 → event_planner 재시도.

### R-NS3: 상점 대화 4줄 초과 (P3)

`dialogue`가 4줄을 넘으면 RPG Maker MZ 텍스트 박스가 짤림.

**완화**: 상점 DSL에서 `dialogue`는 문자열 1개(단일 줄)만 허용.
`_build_dialogue_commands()`의 4줄 청킹은 NpcEvent 전용.

---

## 테스트

```python
# agent/tests/generation/test_npc_shop_compile.py

def test_compile_npc_single_page_no_alt():
    """alt_dialogue 없으면 페이지 1개."""
    event = NpcEvent(type="npc", name="주민", x=5, y=5,
                     dialogue=["안녕!"], trigger="action_button")
    result = compile_npc(event, mock_compiler)
    assert len(result["pages"]) == 1

def test_compile_npc_two_pages_with_alt():
    """alt_dialogue 있으면 페이지 2개, 페이지2 switch1Valid=True."""
    event = NpcEvent(
        type="npc", name="주민", x=5, y=5,
        dialogue=["적이 살아있다!"],
        condition_switch="boss_defeated",
        alt_dialogue=["평화가 왔다!"],
    )
    result = compile_npc(event, mock_compiler)
    assert len(result["pages"]) == 2
    assert result["pages"][1]["conditions"]["switch1Valid"] is True

def test_compile_shop_no_dialogue():
    """대화 없는 상점: 302로 시작."""
    event = ShopEvent(
        type="shop", name="상점", x=10, y=5,
        items=[ShopItem(item="회복 포션", item_type="item")],
        purchase_only=False,
    )
    cmds = compile_shop(event, mock_compiler)
    assert cmds[0]["code"] == 302

def test_compile_shop_with_dialogue():
    """대화 있는 상점: 101→401→302→0."""
    event = ShopEvent(
        type="shop", name="상점", x=10, y=5,
        dialogue="어서오세요!",
        items=[ShopItem(item="회복 포션", item_type="item")],
        purchase_only=False,
    )
    cmds = compile_shop(event, mock_compiler)
    codes = [c["code"] for c in cmds]
    assert codes == [101, 401, 302, 0]

def test_compile_shop_multiple_items():
    """상품 3개: 302 + 605×2 + 0."""
    event = ShopEvent(
        type="shop", name="상점", x=10, y=5,
        items=[
            ShopItem(item="철검", item_type="weapon"),
            ShopItem(item="가죽 방패", item_type="armor"),
            ShopItem(item="회복 포션", item_type="item"),
        ],
    )
    cmds = compile_shop(event, mock_compiler)
    codes = [c["code"] for c in cmds]
    assert codes == [302, 605, 605, 0]

def test_compile_shop_purchase_only():
    """purchase_only=True면 302 parameters[4]=1."""
    event = ShopEvent(
        type="shop", name="상점", x=10, y=5,
        items=[ShopItem(item="회복 포션", item_type="item")],
        purchase_only=True,
    )
    cmds = compile_shop(event, mock_compiler)
    assert cmds[0]["parameters"][4] == 1  # purchase_only flag
```
