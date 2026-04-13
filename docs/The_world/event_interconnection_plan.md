# 이벤트 간 연동(Switch Chain) 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이벤트 간 스위치 연동을 개선하여 Transfer/Shop 조건부 활성화, 스위치 검증, 프롬프트 가이드를 구현한다.

**Architecture:** Phase D(프롬프트) → Phase A(DSL+컴파일러) → 검증 순으로 진행. 각 Phase 완료 후 기존 테스트 + 신규 테스트로 실증 검증.

**Tech Stack:** Python 3.12, Pydantic, pytest, YAML DSL

---

## Phase D: 프롬프트 개선 (코드 변경 없음)

### Task 1: 프롬프트에 스위치 연동 가이드 추가

**Files:**
- Modify: `agent/generation/prompts/event_planner_prompt.py:13-100` (\_SYSTEM 문자열)

- [ ] **Step 1: 기존 테스트 통과 확인 (베이스라인)**

Run: `uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: 모든 테스트 PASS

- [ ] **Step 2: \_SYSTEM 프롬프트에 스위치 연동 규칙 섹션 추가**

`agent/generation/prompts/event_planner_prompt.py`의 `_SYSTEM` 문자열 끝(`### ending` 섹션 뒤)에 다음을 추가:

```python
## 스위치 연동 규칙

### 스위치 이름 규칙
- 사전 할당된 스위치를 **우선** 사용할 것 (아래 목록 참조)
- 새 스위치 생성 시: `{목적}_{대상}` 형식 (예: `quest_elder_talked`)
- **절대 같은 개념에 다른 이름을 쓰지 말 것** (예: `고블린_battle_01`과 `고블린_배틀_01`은 다른 스위치)
- 같은 스위치 이름은 맵이 달라도 동일한 게임 상태를 의미함 — 글로벌 범위

### 스위치 연동 패턴
**패턴 1: 보스 처치 → NPC 대화 변경**
```yaml
- type: battle
  troop: 마왕_단독
  on_win:
    - set_switch: 마왕_defeated
  battle_switch: 마왕_battle
- type: npc
  name: 마을장로
  dialogue: ["마왕을 물리쳐주세요!"]
  condition_switch: 마왕_defeated
  alt_dialogue: ["평화가 찾아왔어요!"]
```

**패턴 2: NPC 대화 → 다른 이벤트 활성화**
```yaml
- type: npc
  name: 장로
  dialogue: ["이 열쇠를 가져가세요."]
  set_switch: quest_started
```

### 금지 사항
- NPC의 set_switch에 `chest_` 접두어 스위치를 쓰지 말 것 (보물상자 스위치 오염)
- 전투 battle_switch와 on_win.set_switch에 같은 이름을 쓰지 말 것
- 이 맵에서 사용하지 않을 스위치를 임의로 만들지 말 것
```

- [ ] **Step 3: _describe_required_events에 스위치 사용 힌트 추가**

`event_planner_prompt.py:432-470`의 `_describe_required_events` 함수에서 각 맵 타입별 반환 문자열에 스위치 힌트를 추가:

**dungeon 타입** (line 446-453 부근):
```python
    elif spec.map_type == "dungeon":
        return (
            "1. 맵 이동 이벤트 (입구/출구, 위 좌표 정보 사용)\n"
            "2. 전투 이벤트 2~3개 (player_touch, one_time=true)\n"
            "3. 보물 상자 1~2개 (chest 타입)\n"
            "4. 선택: 경고 NPC 1개\n"
            "⚠️ 금지: ending 이벤트 생성 금지 — 엔딩은 boss 맵 전용\n"
            "⚠️ 스위치: 전투 battle_switch는 맵 고유 이름 사용 "
            "(예: {맵이름}_고블린_battle). 다른 맵과 절대 중복 금지"
        )
```

**boss 타입** (line 454-468 부근) — 이미 `{boss_name}_defeated`를 안내하므로 추가 불필요.

- [ ] **Step 4: 기존 테스트 재확인**

Run: `uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: 모든 테스트 PASS (프롬프트 문자열만 변경했으므로 기존 테스트 영향 없음)

- [ ] **Step 5: 커밋**

```bash
git add agent/generation/prompts/event_planner_prompt.py
git commit -m "feat: event_planner 프롬프트에 스위치 연동 가이드 추가

- 스위치 이름 규칙 (글로벌 범위, 네이밍 컨벤션)
- 연동 패턴 예시 (보스→NPC, NPC→이벤트)
- 금지 사항 (chest 스위치 오염, 이름 중복)
- 던전 맵 타입에 맵 고유 스위치 이름 힌트"
```

---

## Phase A: DSL 필드 확장 + 컴파일러 구현

### Task 2: TransferEvent에 condition_switch 추가

**Files:**
- Modify: `agent/generation/compilers/dsl_models.py:29-42`
- Modify: `agent/generation/compilers/event_compiler.py:165-189`
- Test: `agent/tests/generation/test_event_compiler.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`agent/tests/generation/test_event_compiler.py` 끝에 추가:

```python
def test_compile_transfer_with_condition_switch(compiler: EventCompiler) -> None:
    """TransferEvent: condition_switch 있으면 2페이지 — page1 차단, page2 이동."""
    event = TransferEvent(
        type="transfer",
        name="보스맵_입구",
        x=10,
        y=13,
        to_map="보스의 성",
        to_x=1,
        to_y=1,
        condition_switch="던전_입구_클리어",
        blocked_dialogue="아직 던전을 클리어하지 못했습니다.",
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # page1: 조건 없음 (차단 메시지)
    assert result["pages"][0]["conditions"]["switch1Valid"] is False
    codes_p1 = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 101 in codes_p1  # 차단 대화
    # page2: switch 조건 ON일 때 이동
    assert result["pages"][1]["conditions"]["switch1Valid"] is True
    codes_p2 = [cmd["code"] for cmd in result["pages"][1]["list"]]
    assert 201 in codes_p2  # Transfer


def test_compile_transfer_without_condition_switch_unchanged(compiler: EventCompiler) -> None:
    """TransferEvent: condition_switch 없으면 기존과 동일 1페이지."""
    event = TransferEvent(
        type="transfer", name="마을_이동", x=5, y=5, to_map="출발 마을", to_x=1, to_y=1
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 1
    assert result["pages"][0]["conditions"]["switch1Valid"] is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py::test_compile_transfer_with_condition_switch -v`
Expected: FAIL (TransferEvent에 condition_switch 필드 없음)

- [ ] **Step 3: DSL 모델에 필드 추가**

`agent/generation/compilers/dsl_models.py:29-42`의 TransferEvent 수정:

```python
class TransferEvent(BaseModel):
    type: Literal["transfer"]
    name: str
    x: int
    y: int
    trigger: Literal["player_touch", "event_touch"] = "player_touch"
    to_map: str
    to_x: int
    to_y: int
    direction: str = "retain"
    set_switch: str | None = None
    condition_switch: str | None = None      # 추가: 스위치 ON일 때만 이동
    blocked_dialogue: str | None = None      # 추가: 조건 미충족 시 메시지
    character_name: str = "!Crystal"
    character_index: int = 0
```

- [ ] **Step 4: 컴파일러 구현**

`agent/generation/compilers/event_compiler.py`의 `_compile_transfer` 메서드 전체 교체 (line 165-189):

```python
    def _compile_transfer(self, event: TransferEvent) -> dict:
        map_id = self.resolve_map_id(event.to_map)
        direction = _DIRECTION_CODE.get(event.direction, 0)

        transfer_cmds: list[dict] = []
        transfer_cmds.append(
            {
                "code": 201,
                "indent": 0,
                "parameters": [0, map_id, event.to_x, event.to_y, direction, 0],
            }
        )
        if event.set_switch:
            sw_id = self.resolve_switch_id(event.set_switch)
            transfer_cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})
        transfer_cmds.append({"code": 0, "indent": 0, "parameters": []})

        if event.condition_switch:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)

            # page1: 조건 없음 — 차단 메시지 (switch OFF 시 활성)
            page1_cmds: list[dict] = []
            if event.blocked_dialogue:
                page1_cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]})
                page1_cmds.append(
                    {"code": 401, "indent": 0, "parameters": [event.blocked_dialogue]}
                )
            page1_cmds.append({"code": 0, "indent": 0, "parameters": []})

            # page2: switch ON → 이동 실행
            pages = [
                _make_page(
                    page1_cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
                _make_page(
                    transfer_cmds,
                    _make_switch_condition(cond_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
            ]
        else:
            pages = [
                _make_page(
                    transfer_cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            ]

        return _make_event(event.name, event.x, event.y, pages)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py -v`
Expected: 전체 PASS (신규 2개 + 기존 모두)

- [ ] **Step 6: 커밋**

```bash
git add agent/generation/compilers/dsl_models.py agent/generation/compilers/event_compiler.py agent/tests/generation/test_event_compiler.py
git commit -m "feat: TransferEvent에 condition_switch 추가

- DSL: condition_switch, blocked_dialogue 필드 추가
- 컴파일러: 조건부 2페이지 구성 (page1: 차단, page2: 이동)
- condition_switch 없으면 기존 동작 유지 (하위 호환)"
```

### Task 3: ShopEvent에 condition_switch 추가

**Files:**
- Modify: `agent/generation/compilers/dsl_models.py:99-109`
- Modify: `agent/generation/compilers/event_compiler.py:318-353`
- Test: `agent/tests/generation/test_event_compiler.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`agent/tests/generation/test_event_compiler.py` 끝에 추가:

```python
def test_compile_shop_with_condition_switch(compiler: EventCompiler) -> None:
    """ShopEvent: condition_switch 있으면 2페이지 — page1 차단, page2 상점."""
    event = ShopEvent(
        type="shop",
        name="무기상인",
        x=6,
        y=4,
        condition_switch="quest_completed",
        items=[ShopItem(item="회복 포션", item_type="item")],
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # page1: 조건 없음 (비활성 상태)
    assert result["pages"][0]["conditions"]["switch1Valid"] is False
    # page2: switch 조건 ON일 때 상점
    assert result["pages"][1]["conditions"]["switch1Valid"] is True
    codes_p2 = [cmd["code"] for cmd in result["pages"][1]["list"]]
    assert 302 in codes_p2  # Shop


def test_compile_shop_without_condition_switch_unchanged(compiler: EventCompiler) -> None:
    """ShopEvent: condition_switch 없으면 기존과 동일 1페이지."""
    event = ShopEvent(
        type="shop",
        name="무기상인",
        x=6,
        y=4,
        items=[ShopItem(item="회복 포션", item_type="item")],
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 1
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 302 in codes
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py::test_compile_shop_with_condition_switch -v`
Expected: FAIL

- [ ] **Step 3: DSL 모델에 필드 추가**

`agent/generation/compilers/dsl_models.py:99-109`의 ShopEvent 수정:

```python
class ShopEvent(BaseModel):
    type: Literal["shop"]
    name: str
    x: int
    y: int
    trigger: Literal["action_button"] = "action_button"
    dialogue: str = ""
    items: list[ShopItem]
    purchase_only: bool = False
    condition_switch: str | None = None  # 추가: 스위치 ON일 때만 상점 활성
    character_name: str = "People1"
    character_index: int = 0
```

- [ ] **Step 4: 컴파일러 구현**

`agent/generation/compilers/event_compiler.py`의 `_compile_shop` 메서드 전체 교체 (line 318-353):

```python
    def _compile_shop(self, event: ShopEvent) -> dict:
        if not event.items:
            raise CompileError(f"상점 '{event.name}'에 상품이 없음")

        cmds: list[dict] = []

        if event.dialogue:
            cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, event.name]})
            cmds.append({"code": 401, "indent": 0, "parameters": [event.dialogue]})

        first = event.items[0]
        goods_type = _ITEM_TYPE_TO_GOODS_CODE.get(first.item_type, 0)
        goods_id = self.resolve_item_id(first.item, first.item_type)
        purchase_flag = 1 if event.purchase_only else 0
        cmds.append(
            {
                "code": 302,
                "indent": 0,
                "parameters": [goods_type, goods_id, 0, 0, purchase_flag, False],
            }
        )

        for item_spec in event.items[1:]:
            gtype = _ITEM_TYPE_TO_GOODS_CODE.get(item_spec.item_type, 0)
            gid = self.resolve_item_id(item_spec.item, item_spec.item_type)
            cmds.append({"code": 605, "indent": 0, "parameters": [gtype, gid, 0, 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        if event.condition_switch:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)

            # page1: 조건 없음 — 비활성 (NPC 스프라이트는 보이지만 상점 안 열림)
            page1_cmds = [{"code": 0, "indent": 0, "parameters": []}]
            pages = [
                _make_page(
                    page1_cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
                _make_page(
                    cmds,
                    _make_switch_condition(cond_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
            ]
        else:
            pages = [
                _make_page(
                    cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            ]

        return _make_event(event.name, event.x, event.y, pages)
```

- [ ] **Step 5: 전체 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py -v`
Expected: 전체 PASS

- [ ] **Step 6: 커밋**

```bash
git add agent/generation/compilers/dsl_models.py agent/generation/compilers/event_compiler.py agent/tests/generation/test_event_compiler.py
git commit -m "feat: ShopEvent에 condition_switch 추가

- DSL: condition_switch 필드 추가
- 컴파일러: 조건부 2페이지 구성 (page1: 비활성, page2: 상점)
- condition_switch 없으면 기존 동작 유지 (하위 호환)"
```

### Task 4: 프롬프트에 Transfer/Shop condition_switch 안내 추가

**Files:**
- Modify: `agent/generation/prompts/event_planner_prompt.py:13-100` (\_SYSTEM의 DSL 타입 설명)

- [ ] **Step 1: \_SYSTEM의 transfer 섹션에 condition_switch 필드 설명 추가**

`_SYSTEM` 문자열에서 `### transfer` 부분 찾아서 DSL 필드 설명에 추가:

```
  condition_switch: {스위치 이름}   # 선택 (이 스위치 ON일 때만 이동 가능)
  blocked_dialogue: "아직 갈 수 없습니다."  # 선택 (조건 미충족 시 메시지)
```

`### shop` 부분에도 추가:

```
  condition_switch: {스위치 이름}   # 선택 (이 스위치 ON일 때만 상점 오픈)
```

- [ ] **Step 2: _describe_required_events boss 타입에 Transfer condition_switch 힌트 추가**

`event_planner_prompt.py:454-468`의 boss 타입 반환값 수정:

```python
    elif spec.map_type == "boss":
        boss_enemies = [e for e in game_spec.enemies if e.tier == "boss"]
        boss_name = boss_enemies[0].name if boss_enemies else "보스"
        troop_key = f"{boss_name} × 1"
        if troop_key not in id_table.troops:
            troop_key = next(
                (k for k in id_table.troops if boss_name in k), list(id_table.troops.keys())[-1]
            )
        return (
            f"1. 보스 전투 이벤트 필수 (type: battle, troop: {troop_key}, "
            f"lose_condition: game_over, battle_switch: {boss_name}_defeated)\n"
            f"2. 엔딩 이벤트 필수 (type: ending, condition_switch: {boss_name}_defeated, "
            f"action: title)\n"
            "3. 맵 이동 이벤트 (탈출용)\n"
            "   ⚠️ battle 이벤트와 ending 이벤트의 x, y 좌표는 반드시 달라야 함\n"
            "   ⚠️ 엔딩은 이 맵에만 1개 — 다른 맵에 엔딩 이벤트 중복 생성 금지"
        )
```

- [ ] **Step 3: 테스트 확인**

Run: `uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: 전체 PASS

- [ ] **Step 4: 커밋**

```bash
git add agent/generation/prompts/event_planner_prompt.py
git commit -m "feat: 프롬프트에 Transfer/Shop condition_switch DSL 안내 추가"
```

### Task 5: 스위치 참조 검증 추가

**Files:**
- Modify: `agent/generation/nodes/event_planner.py:203-239`
- Test: `agent/tests/generation/test_event_compiler.py` (또는 별도 테스트)

- [ ] **Step 1: 실패하는 테스트 작성**

`agent/tests/generation/test_event_compiler.py` 끝에 추가:

```python
def test_validate_switch_refs_warns_on_orphan_condition(caplog) -> None:
    """condition_switch가 어떤 이벤트의 set_switch에도 없으면 경고 로그."""
    import logging
    from agent.generation.nodes.event_planner import _validate_switch_refs

    events = [
        NpcEvent(
            type="npc", name="NPC", x=1, y=1,
            dialogue=["hi"],
            condition_switch="never_set_switch",
        ),
        NpcEvent(
            type="npc", name="NPC2", x=2, y=2,
            dialogue=["hello"],
            set_switch="some_other_switch",
        ),
    ]
    with caplog.at_level(logging.WARNING):
        _validate_switch_refs(events, set())

    assert any("never_set_switch" in r.message for r in caplog.records)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py::test_validate_switch_refs_warns_on_orphan_condition -v`
Expected: FAIL (함수 미존재)

- [ ] **Step 3: 스위치 참조 검증 함수 구현**

`agent/generation/nodes/event_planner.py`에 `_validate_switch_refs` 함수 추가 (기존 `_validate_name_refs` 뒤에):

```python
def _validate_switch_refs(events: list, pre_allocated_switches: set[str]) -> None:
    """condition_switch가 참조하는 스위치가 set되는 곳이 있는지 경고 로그."""
    # 이벤트들이 SET하는 스위치 수집
    set_switches: set[str] = set(pre_allocated_switches)
    for e in events:
        if hasattr(e, "set_switch") and e.set_switch:
            set_switches.add(e.set_switch)
        if hasattr(e, "battle_switch") and e.battle_switch:
            set_switches.add(e.battle_switch)
        if hasattr(e, "chest_switch") and e.chest_switch:
            set_switches.add(e.chest_switch)
        if hasattr(e, "on_win"):
            for action in e.on_win:
                if action.set_switch:
                    set_switches.add(action.set_switch)

    # condition_switch가 참조하는데 SET되는 곳이 없는 스위치 경고
    for e in events:
        if hasattr(e, "condition_switch") and e.condition_switch:
            if e.condition_switch not in set_switches:
                logger.warning(
                    "이벤트 '%s': condition_switch '%s'가 어떤 이벤트에서도 set되지 않음",
                    e.name,
                    e.condition_switch,
                )
```

- [ ] **Step 4: event_planner에서 검증 호출**

`agent/generation/nodes/event_planner.py`의 `_plan_single_map` 함수 (line 97-124), `valid = _validate_name_refs(...)` 뒤에 추가:

```python
            if valid is not None:
                _validate_switch_refs(valid, set(switch_table.switches.keys()))
                return _fix_battle_sprites(valid, troop_to_sprite)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py -v`
Expected: 전체 PASS

- [ ] **Step 6: 전체 generation 테스트 확인**

Run: `uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: 전체 PASS

- [ ] **Step 7: 커밋**

```bash
git add agent/generation/nodes/event_planner.py agent/tests/generation/test_event_compiler.py
git commit -m "feat: 스위치 참조 검증 추가

- _validate_switch_refs: condition_switch가 어디서도 set되지 않으면 경고
- event_planner에서 이벤트 검증 시 자동 호출"
```

---

## Phase 검증: 실증 테스트

### Task 6: 전체 테스트 스위트 실행 + 실증 보고

**Files:**
- 없음 (검증만)

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `uv run pytest app/backend/tests agent/tests -v --tb=short -m "not integration"`
Expected: 전체 PASS

- [ ] **Step 2: ruff 린트 확인**

Run: `uv run ruff check agent/generation/compilers/ agent/generation/nodes/event_planner.py agent/generation/prompts/event_planner_prompt.py`
Expected: All checks passed

- [ ] **Step 3: 변경 사항 요약 보고**

다음 항목을 확인하여 보고:
1. Phase D 완료: 프롬프트에 스위치 연동 가이드 추가됨
2. Phase A 완료: TransferEvent/ShopEvent에 condition_switch 추가됨
3. 스위치 참조 검증 추가됨
4. 기존 테스트 전체 통과 (하위 호환 확인)
5. 신규 테스트 4개 추가 (transfer 2개 + shop 2개 + switch_refs 1개 — 5개)
6. 분석 문서 대비 해결된 문제:
   - 문제 1 (Transfer 무조건 이동): **해결** — condition_switch 추가
   - 문제 2 (스위치 이름 충돌): **완화** — 프롬프트 가이드 + 네이밍 규칙
   - 문제 3 (유령 스위치): **완화** — 검증 경고 로그 추가
   - 문제 4 (사전 할당 미사용): **완화** — 프롬프트에 우선 사용 지시
   - 문제 6 (Shop 스위치 없음): **해결** — condition_switch 추가
   - 문제 7 (엔딩 중복): **완화** — 프롬프트에 중복 금지 지시
   - 문제 8 (프롬프트 가이드 부재): **해결** — 연동 패턴/규칙/금지사항 추가
   - 문제 5 (troop=0): **미해결** — 별도 이슈 (이벤트 연동과 무관)
