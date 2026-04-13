# 게임 엔딩 시퀀스 설계

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 문제

다른 문서들은 `boss_defeated` 스위치와 `ending_triggered` 스위치를 언급하지만,
실제로 RPG Maker MZ에서 "게임 엔딩"을 구현하는 방법이 정의되지 않았다.

플레이어가 보스를 쓰러뜨린 후:
- 어떤 커맨드 코드로 엔딩 텍스트를 보여주나?
- 화면 페이드아웃은?
- 타이틀 화면으로 돌아가나 아니면 엔딩 스크린인가?
- DSL에는 어떤 타입으로 표현하나?

---

## R23. 도달 가능한 엔딩 없음 (P1)

보스 처치 후 아무것도 안 일어나면 플레이어는 "게임이 끝났는가?"를 알 수 없다.
`check_ending_reachable()` validator가 이를 탐지해야 한다.

---

## 엔딩 구현 전략

### 선택된 방식: 보스 맵의 Auto-Run 이벤트

가장 단순하고 안정적인 방법:
1. 보스 맵에 **Auto-Run 이벤트** 배치 (전투 후 자동 실행)
2. `boss_defeated` 스위치가 ON인 경우 활성화
3. 엔딩 텍스트 → 페이드아웃 → 타이틀 복귀

Auto-Run(trigger=3)은 조건을 만족하는 순간 자동으로 실행된다.

### 대안 방식 (미채택)

| 방식 | 장점 | 단점 |
|------|------|------|
| Battle Event의 postbattle 처리 | 전투 직후 실행 | RPG Maker MZ battle event 복잡 |
| Common Event | 전역 사용 가능 | CommonEvents.json 추가 필요 |
| Auto-Run (채택) | 단순, 예측 가능 | 스위치 조건 필수 |

---

## DSL 엔딩 타입

현재 `DslEvent` 유니온에 엔딩 타입이 없다. 추가한다:

```python
class EndingEvent(BaseModel):
    type: Literal["ending"]
    name: str
    x: int
    y: int
    # 엔딩 활성화 조건
    condition_switch: str          # SwitchTable 이름 (예: "boss_defeated")
    # 엔딩 내용
    lines: list[str]               # 엔딩 텍스트 (최대 5줄 권장)
    fade_type: Literal["black", "white"] = "black"
    # 엔딩 후 처리
    action: Literal["title", "gameover"] = "title"

# DslEvent 유니온에 추가
DslEvent = NpcEvent | TransferEvent | ChestEvent | BattleEvent | ShopEvent | EndingEvent
```

### DSL 예시

```yaml
# 보스 맵의 자동 실행 엔딩 이벤트
- type: ending
  name: 엔딩_이벤트
  x: 10                        # 보스 방 중앙 근처 임의 위치
  y: 10
  condition_switch: 드래곤_defeated   # boss_defeated 스위치
  lines:
    - "드래곤이 쓰러졌다!"
    - "왕국에 평화가 찾아왔다."
    - "용사여, 고맙소..."
    - "～ END ～"
  fade_type: black
  action: title                # 타이틀 화면으로 복귀
```

---

## event_compiler 구현

```python
def compile_ending(event: EndingEvent, compiler: EventCompiler) -> dict:
    """EndingEvent → RPG Maker MZ 이벤트 JSON."""

    cond_switch_id = compiler.resolve_switch(event.condition_switch)

    # 페이지 1: boss_defeated가 ON일 때 (엔딩 실행)
    page1_cmds = _build_ending_commands(event)

    # 페이지 2 (조건 없음): 아무것도 하지 않음 (게임 상태 유지용 더미)
    page2_cmds = [{"code": 0, "indent": 0, "parameters": []}]

    return {
        "id": 0, "name": event.name, "note": "",
        "x": event.x, "y": event.y,
        "pages": [
            _make_page(
                cmds=page1_cmds,
                conditions=_make_switch_condition(cond_switch_id),
                trigger=3,   # 3 = Auto-Run (조건 충족 시 자동 실행)
                priority=0,  # 캐릭터 아래 (바닥 이벤트)
            ),
            _make_page(
                cmds=page2_cmds,
                conditions=_empty_conditions(),
                trigger=3,   # Auto-Run이지만 조건 없으면 항상 실행 → 주의
            ),
        ],
    }

def _build_ending_commands(event: EndingEvent) -> list[dict]:
    """엔딩 커맨드 시퀀스."""
    cmds: list[dict] = []

    # 1. 플레이어 이동 잠금 (엔딩 중 움직임 방지)
    cmds.append({"code": 106, "indent": 0, "parameters": [60]})   # Wait 60 frames
    cmds.append({
        "code": 122, "indent": 0,                                  # ChangeActorImages
        "parameters": [],
    })
    # 더 간단하게: 이동 제한은 Auto-Run이 자동으로 처리 (플레이어 입력 차단)

    # 2. 엔딩 텍스트 출력
    for line in event.lines:
        cmds.append({
            "code": 101,  # ShowText (메시지 창)
            "indent": 0,
            "parameters": ["", 0, 0, 2, ""],  # face_name, face_index, background, position, speaker
        })
        cmds.append({
            "code": 401,  # ShowText continuation
            "indent": 0,
            "parameters": [line],
        })

    # 3. 잠시 대기
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})   # Wait 60 frames (1초)

    # 4. 화면 페이드아웃
    fade_color = 0 if event.fade_type == "black" else 1
    cmds.append({"code": 221, "indent": 0, "parameters": []})     # Fadeout Screen

    # 5. 대기
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})

    # 6. 엔딩 후 처리
    if event.action == "title":
        cmds.append({"code": 354, "indent": 0, "parameters": []}) # Return to Title Screen
    else:  # "gameover"
        cmds.append({"code": 353, "indent": 0, "parameters": []}) # Game Over

    # 7. 이벤트 종료
    cmds.append({"code": 0, "indent": 0, "parameters": []})

    return cmds
```

### RPG Maker MZ 커맨드 코드 참조

| 코드 | 이름 | 설명 |
|------|------|------|
| 101 | Show Text (header) | 메시지 창 시작 |
| 401 | Show Text (content) | 메시지 텍스트 줄 |
| 221 | Fadeout Screen | 화면 페이드아웃 |
| 222 | Fadein Screen | 화면 페이드인 |
| 230 | Wait | N프레임 대기 |
| 354 | Return to Title | 타이틀 화면으로 |
| 353 | Game Over | 게임오버 화면 |
| 106 | Wait (alias) | (230과 동일, 구버전 호환) |

---

## event_planner 프롬프트 규칙

event_planner가 보스 맵에 EndingEvent를 배치하도록 안내:

```python
BOSS_MAP_REQUIRED_EVENTS = """
## 보스 맵 필수 이벤트

보스 맵(type='boss')에는 반드시 다음을 포함해야 합니다:

1. **보스 전투 이벤트** (type: battle)
   - troop_id: [보스 트루프 ID]
   - defeat_switch_id: [보스이름]_defeated

2. **엔딩 이벤트** (type: ending)
   - condition_switch: [보스이름]_defeated
   - 보스 처치 후 승리 메시지 표시
   - action: title (타이틀 화면 복귀)
   - 위치: 보스 전투 이벤트와 다른 좌표

예시:
```yaml
- type: battle
  name: 드래곤_전투
  x: 10
  y: 10
  troop_id: 드래곤        # id_table.troops에서 이름 참조
  defeat_switch_id: 드래곤_defeated

- type: ending
  name: 엔딩
  x: 10
  y: 12                   # 전투 이벤트와 Y좌표 다르게
  condition_switch: 드래곤_defeated
  lines:
    - "드래곤이 쓰러졌다!"
    - "세계에 평화가 찾아왔다."
    - "～ 완 ～"
  action: title
```
"""
```

---

## `_describe_required_events()` 구현

prompt_engineering.md에서 언급된 함수. 맵 타입별 필수 이벤트 설명을 생성:

```python
def _describe_required_events(
    spec: MapSpec,
    connection_info: MapConnectionInfo,
    id_to_name: dict[int, str],
    id_table: IdTable,
    game_spec: GameSpec,
) -> str:
    """맵 타입별 필수 이벤트 설명 생성 (event_planner 프롬프트용)."""
    lines = [f"## {spec.name} 필수 이벤트"]

    # 모든 맵: transfer 이벤트 (다른 맵 연결)
    for exit_info in connection_info.exits:
        tgt_name = id_to_name.get(exit_info.target_map_id, "알 수 없는 맵")
        lines.append(
            f"- transfer 이벤트: {tgt_name}으로 이동 "
            f"(exit: x={exit_info.exit_x}, y={exit_info.exit_y}, "
            f"target_map_id={exit_info.target_map_id}, "
            f"target_x={exit_info.entry_x}, target_y={exit_info.entry_y})"
        )

    # 맵 타입별 추가 필수 이벤트
    if spec.map_type == "town":
        lines.append("- 최소 2개 이상 NPC 이벤트 (마을 주민, 상점 등)")
        lines.append("- 선택: shop 이벤트 (여관/상점)")

    elif spec.map_type == "dungeon":
        lines.append("- 최소 1개 chest 이벤트 (보물 상자)")
        lines.append("- 선택: 보스 방 입구에 경고 NPC")

    elif spec.map_type == "boss":
        # 보스 캐릭터 찾기
        boss_enemies = [e for e in game_spec.enemies if e.tier == "boss"]
        if boss_enemies:
            boss = boss_enemies[0]
            troop_id = id_table.troops.get(f"{boss.name} × 1",
                       id_table.troops.get(boss.name, 1))
            lines.append(f"- battle 이벤트 필수: troop_id={troop_id} ({boss.name})")
            lines.append(f"  defeat_switch_id: {boss.name}_defeated")
            lines.append(f"- ending 이벤트 필수: condition_switch={boss.name}_defeated")
        else:
            lines.append("- battle 이벤트 필수 (보스 맵)")
            lines.append("- ending 이벤트 필수")

    return "\n".join(lines)
```

---

## `check_ending_reachable()` validator

```python
def check_ending_reachable(
    state: GenerationState,
) -> list[str]:
    """
    보스 맵에 도달 가능한 엔딩 이벤트가 있는지 확인.
    없으면 validator 오류 추가.
    """
    errors = []
    map_specs = state.get("map_specs", [])
    compiled  = state.get("compiled_events", {})
    id_table  = state["id_table"]

    boss_maps = [m for m in map_specs if m.map_type == "boss"]
    if not boss_maps:
        errors.append("보스 맵 없음 — 게임 엔딩 불가")
        return errors

    for boss_map in boss_maps:
        mid = id_table.get_id("maps", boss_map.name)
        events = compiled.get(mid, [])

        # 엔딩 이벤트 확인: code=354 (Return to Title) 또는 code=353 (Gameover) 포함 여부
        has_ending = any(
            any(cmd.get("code") in (353, 354) for cmd in event.get("pages", [{}])[0].get("list", []))
            for event in events
        )
        if not has_ending:
            errors.append(
                f"보스 맵 '{boss_map.name}'에 엔딩 이벤트(코드 353/354) 없음"
            )

    # 보스 처치 스위치 존재 확인
    switch_table = state["switch_table"]
    boss_switches = [n for n in switch_table.switches if "_defeated" in n]
    if not boss_switches:
        errors.append("보스 처치 스위치가 SwitchTable에 없음")

    return errors
```

---

## 통합: generation_validator에 추가

```python
async def run_generation_validator(state: GenerationState) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    project = state["final_project"]
    id_table = state["id_table"]

    errors += check_id_references(project, id_table)
    errors += check_null_at_index_0(project)
    errors += check_array_lengths(project)
    errors += check_start_position(project, state["map_tiles"])  # R16
    errors += check_troop_positions(project)                     # R17
    errors += check_map_id_consistency(project)                  # R18
    errors += check_resource_filenames(project)                  # R19
    errors += check_ending_reachable(state)                      # R23

    warnings += check_balance(project)
    warnings += check_event_coordinate_conflicts(state["compiled_events"])  # R22
    warnings += check_switch_semantic_conflicts(state["switch_table"])      # R20

    ...
```

---

## 테스트

```python
# agent/tests/generation/test_ending.py

def test_ending_event_compile_returns_code_354():
    event = EndingEvent(
        type="ending",
        name="엔딩",
        x=10, y=10,
        condition_switch="드래곤_defeated",
        lines=["드래곤이 쓰러졌다!", "평화가 찾아왔다."],
        action="title",
    )
    compiler = EventCompiler(id_table=mock_id_table, switch_table=mock_switch_table)
    result = compile_ending(event, compiler)
    page1_codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 101 in page1_codes   # ShowText
    assert 221 in page1_codes   # Fadeout
    assert 354 in page1_codes   # Return to Title
    assert result["pages"][0]["trigger"] == 3  # Auto-Run

def test_ending_trigger_is_auto_run():
    """엔딩 이벤트는 Auto-Run(3)이어야 함."""
    event = EndingEvent(type="ending", name="e", x=0, y=0,
                        condition_switch="boss_defeated", lines=["끝"], action="title")
    result = compile_ending(event, mock_compiler)
    assert result["pages"][0]["trigger"] == 3

def test_check_ending_reachable_no_ending(mock_state):
    """엔딩 이벤트 없으면 오류 반환."""
    mock_state["map_specs"] = [MapSpec(name="보스방", map_type="boss", ...)]  # 상세 MapSpec: map_type 필드 사용
    mock_state["compiled_events"] = {3: []}  # 빈 이벤트 목록
    errors = check_ending_reachable(mock_state)
    assert any("엔딩" in e for e in errors)

def test_check_ending_reachable_with_ending(mock_state_with_ending):
    errors = check_ending_reachable(mock_state_with_ending)
    assert errors == []
```
