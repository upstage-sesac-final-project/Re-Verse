# Re:Verse 이벤트 시스템 구현 가이드

> 최종 업데이트: 2026-04-13
> 대상 브랜치: `feat/hj/world_compiler_event`
> 참고 게임: `game_e6cbb065` (2026-04-13 생성)

---

## 목차

1. [이벤트 시스템 개요](#1-이벤트-시스템-개요)
2. [이벤트 생성 파이프라인 흐름](#2-이벤트-생성-파이프라인-흐름)
3. [이벤트 타입별 구현 방식](#3-이벤트-타입별-구현-방식)
4. [스위치 네임스페이스 설계](#4-스위치-네임스페이스-설계)
5. [구현 중 발생한 문제와 개선 내역](#5-구현-중-발생한-문제와-개선-내역)
6. [현재 잔존하는 문제 및 개선 방향](#6-현재-잔존하는-문제-및-개선-방향)

---

## 1. 이벤트 시스템 개요

Re:Verse는 사용자의 자연어 입력을 받아 RPG Maker MZ 게임을 자동 생성합니다.
이벤트 시스템은 **LLM이 생성한 YAML DSL → Python 컴파일러 → RPG Maker MZ JSON** 변환 구조입니다.

### 핵심 설계 원칙

- **스위치 기반 진행**: 모든 게임 진행 조건은 RPG Maker MZ의 스위치(ON/OFF)로 관리
- **이동 이벤트 코드 생성**: gate/transfer 이벤트는 LLM이 아닌 코드가 직접 생성 (LLM 출력은 폐기)
- **3중 방어 구조**: LLM 프롬프트 → 후처리 검증 → 컴파일러 폴백 순으로 버그 방지

---

## 2. 이벤트 생성 파이프라인 흐름

```
[사용자 입력]
      │
      ▼
[game_designer]         GameSpec 생성 (맵 구조, 스토리, 적/아이템 목록)
      │
      ▼
[asset_planner]         스위치 사전 할당 (SwitchTable 구성)
      │                 └─ {enemy}_defeated, {item}_chest, {map}_npc{n}_talked
      │                 └─ {item}_battle_won  ← 배틀 퀘스트 전용 독립 스위치
      │
      ▼
[story_planner]         맵별 MapScreenplay 생성 (대본 + 이벤트 체크리스트)
      │                 └─ npcs: NPC 목록 + set_switch
      │                 └─ acquisitions: 아이템 목록 + chest_switch
      │                 └─ moves: forward/backward 이동 정보
      │
      ▼
[event_planner]         맵별 YAML DSL 생성 (LLM, 병렬 처리)
      │                 후처리 순서:
      │                 1. _strip_llm_move_events()        — LLM 생성 gate/transfer 폐기
      │                 2. _filter_extra_quest_chests()    — 체크리스트 외 quest_chest 제거
      │                 3. _ensure_acquisition_events()    — 누락 quest_chest 자동 삽입
      │                 4. _fix_battle_quest_switch_collision() — 스위치 충돌 수정
      │                 5. _fix_npc_defeated_conditions()  — 잘못된 defeated 스위치 교체
      │                 6. _build_move_events()            — gate/transfer 코드 직접 생성
      │
      ▼
[event_compiler]        DSL → RPG Maker MZ JSON 변환
      │
      ▼
[generation_validator]  불변식 검증 + auto_repair (고립 맵 자동 연결)
      │
      ▼
[Map*.json 파일 출력]
```

---

## 3. 이벤트 타입별 구현 방식

### 3.1 NpcEvent

```yaml
type: npc
name: "촌장"
set_switch: "마을_npc1_talked"   # 대화 후 ON → quest_chest 조건 활성화
condition_switch: "보스명_defeated"  # 보스 처치 후 alt_dialogue 표시
```

**RPG Maker MZ 구조:**
- Page 1 (무조건): 대화 → `set_switch` ON
- Page 2 (condition_switch ON): `alt_dialogue` 표시

**주의:**
- `set_switch` ≠ `condition_switch` 이어야 함 (같으면 대화 즉시 alt_dialogue 표시)
- `_defeated` suffix 스위치는 NpcEvent의 `set_switch`로 사용 금지

---

### 3.2 QuestChestEvent

가장 복잡한 이벤트 타입. **퀘스트 조건 충족 후 보물상자로 전환**되는 구조.

#### npc 타입 (마을/보스 맵)

```
Page 1 (quest_switch OFF):  NPC 스프라이트 표시
                            → 대사만 출력 (quest_switch는 별도 NpcEvent가 ON)
Page 2 (quest_switch ON):   보물상자 스프라이트
                            → 아이템 지급 + chest_switch ON
```

**스위치 흐름:**
```
NpcEvent 대화 → npc1_talked ON → QuestChest page2 활성화 → 아이템 획득 → chest_switch ON
                                                                              ↓
                                                              GateEvent 조건 달성 → 다음 맵
```

#### battle 타입 (던전/필드 맵)

```
Page 1 (quest_switch OFF):  Monster 스프라이트 표시
                            → 전투 시작 (code 301)
                            → 승리 시: {item}_battle_won ON
                            → 도망/패배 시: 아무것도 안 함 (몬스터 유지)
Page 2 (quest_switch ON):   보물상자 스프라이트
                            → 아이템 지급 + chest_switch ON
```

**스위치 흐름:**
```
QuestChest 상호작용 → 전투 → 승리 → {item}_battle_won ON → page2 활성화
                                                              → 아이템 획득 → chest_switch ON
                                                                              ↓
                                                              GateEvent 조건 달성 → 다음 맵
```

**핵심:** `{item}_battle_won` 스위치는 `asset_planner`에서 사전 할당된 독립 스위치이며,
NPC talked 스위치와 절대 공유하지 않음.

---

### 3.3 GateEvent

조건 충족 전까지 NPC로 표시되어 힌트를 주고, 조건 충족 시 워프 포털로 전환.

```
Page 1 (conditions NOT ALL ON):  NPC 스프라이트
                                 → 미충족 조건에 해당하는 stage_dialogues 표시
Page 2 (ALL conditions ON):      크리스탈 포털 스프라이트
                                 → 자동 워프
```

**조건 스위치:** 이 맵의 `acquisitions[].chest_switch` 목록이 자동으로 설정됨
(LLM이 condition_switches를 지정해도 폐기되고 코드가 강제 구성)

---

### 3.4 BattleEvent

일회성 전투 이벤트 (랜덤 인카운터 형태가 아닌 맵 배치 이벤트).

```
IF battle_switch OFF:
  전투 시작
  IF 승리:
    on_win 액션 실행 (set_switch 등)
    battle_switch ON  ← 재전투 방지
  IF 도망:
    (아무것도 안 함)
  IF 패배:
    (game_over 또는 continue)
END IF
```

**주의:** `battle_switch`(일회성 제어)와 `{item}_battle_won`(퀘스트 완료)은 다른 스위치임.

---

## 4. 스위치 네임스페이스 설계

`asset_planner._build_switch_table()`에서 모든 스위치를 **게임 생성 전에** 사전 할당.

| 스위치 패턴 | 용도 | 할당 주체 |
|---|---|---|
| `{enemy}_defeated` | 보스/elite 처치 | `asset_planner` |
| `act_{n}_started` | 막 진행 | `asset_planner` |
| `{map}_cleared` | 던전 클리어 | `asset_planner` |
| `game_cleared` | 게임 클리어 | `asset_planner` |
| `{item}_chest` | 아이템 상자 열림 (gate 조건) | `asset_planner` |
| `{map}_npc{n}_talked` | NPC 대화 완료 (npc quest_switch) | `asset_planner` |
| `{item}_battle_won` | 배틀 퀘스트 완료 (battle quest_switch) | `asset_planner` |

### 스위치 할당 규칙

```
QuestChest quest_switch 규칙:
  boss 맵  → {boss_name}_defeated       (npc 타입)
  town 맵  → {map}_npc{n}_talked        (npc 타입)
  dungeon/field 맵 → {item}_battle_won  (battle 타입) ← NPC set_switch와 절대 분리
```

---

## 5. 구현 중 발생한 문제와 개선 내역

### 5.1 battle quest_switch ↔ NPC set_switch 충돌

**증상:** NPC 대화만 해도 battle quest_chest의 상자가 열려 전투 없이 아이템 획득 가능.

**원인:** LLM이 `battle quest_chest.quest_switch`에 `{item}_battle_won` 대신
NPC의 `set_switch`(`{map}_npc1_talked`)를 재사용. NPC 대화 시 set_switch ON →
quest_switch도 같이 ON → 상자 즉시 활성화.

**해결:**
1. `asset_planner`에 `{item}_battle_won` 스위치 사전 할당 (네임스페이스 물리적 분리)
2. `event_planner_prompt`에 명시적 지시 추가: "던전/필드는 `{item}_battle_won` 필수"
3. `_fix_battle_quest_switch_collision()` 후처리 추가:
   - 1차: battle quest_chest.quest_switch가 NPC set_switch와 충돌 → `{item}_battle_won`으로 교체
   - 2차: 여전히 충돌하면 NPC set_switch를 None으로 제거

---

### 5.2 battle quest_chest troop 없음 시 즉시 상자 열림

**증상:** `quest_type=battle`이지만 troop을 지정하지 않은 quest_chest에서
page1에 접근하면 즉시 `quest_switch`가 ON되어 상자가 열림.

**원인:** 컴파일러의 troop 없음 폴백 코드:
```python
# 수정 전 (버그)
npc_cmds.append({"code": 121, ...})  # quest_switch 즉시 ON
```

**해결 (event_compiler.py):**
```python
# 수정 후 — quest_switch ON 제거, 힌트 대사만 출력
npc_cmds = _build_dialogue_commands("이 상자를 지키는 무언가가 있다. 힘으로 제압해야...")
# SET_SWITCH 명령 없음
```

---

### 5.3 chest 이벤트 + quest_chest 이벤트 중복 삽입

**증상:** 동일 아이템에 대해 `chest` 이벤트와 `quest_chest` 이벤트가 맵에 공존.

**원인:** `_ensure_acquisition_events()`가 중복 체크 시 `quest_chest` 타입만 확인하고
`chest` 타입(일반 상자)은 확인하지 않아 LLM이 `chest`로 생성한 경우 자동 삽입이 추가 발생.

**해결 (event_planner.py):**
```python
# 수정 전: quest_chest만 체크
for e in events:
    if e.type == "quest_chest" ...:
        existing_chest_switches.add(e.chest_switch)

# 수정 후: chest 타입도 포함
for e in events:
    if e.type == "chest" and getattr(e, "chest_switch", None):
        existing_chest_switches.add(e.chest_switch)  # ← 추가
    elif e.type == "quest_chest" ...:
        existing_chest_switches.add(e.chest_switch)
```

---

### 5.4 battle quest_chest 자동 삽입 시 troop 미지정

**증상:** `_ensure_acquisition_events()`가 battle quest_chest를 자동 삽입할 때
troop 없이 생성 → 컴파일러에서 troop 없음 폴백 → 상자가 영구히 잠김.

**해결 (event_planner.py):**
```python
# 맵의 기존 BattleEvent에서 troop 목록 수집
available_troops = [
    e.troop for e in events
    if e.type == "battle" and getattr(e, "troop", None)
]
# battle quest_chest 삽입 시 troop 임베드
troop_for_battle = available_troops[len(added) % len(available_troops)]
```
troop이 없으면 npc 타입으로 자동 폴백.

---

### 5.5 item_type 한국어 출력

**증상:** LLM이 item_type을 `"무기"`, `"방어구"`, `"아이템"` 등 한국어로 출력.
컴파일러가 영문 `"weapon"`, `"armor"`, `"item"` 만 인식하므로 오류 발생.

**해결 (story_planner.py):**
```python
correct_type = (
    "item" if acq.item_name in id_table.items else
    "weapon" if acq.item_name in id_table.weapons else
    "armor"
)
if acq.item_type != correct_type:
    acq = acq.model_copy(update={"item_type": correct_type})
```
아이템 이름으로 카테고리를 역추론해 자동 보정.

---

### 5.6 forward move 폴백이 역방향으로 삽입

**증상:** Map3에서 forward move 누락 시 폴백이 이미 지나온 맵(Map2)으로 삽입되어
게임 진행 불가.

**원인:** `map_type` 기반으로 방향 판단 (dungeon → forward로 가정)했으나,
Map ID가 작은 방향도 dungeon일 수 있음.

**해결:** `ex.to_map_id > ms.map_id` 조건으로 방향 판단:
```python
direction = "forward" if ex.to_map_id > s.map_id else "backward"
```

---

### 5.7 `_make_conditions` NameError로 생성 완전 실패

**증상:** 모든 게임 생성이 `NameError: name '_make_conditions' is not defined` 로 실패.

**원인:** 폴백 코드 수정 중 존재하지 않는 함수명 `_make_conditions()` 사용.
실제 함수명: `_make_switch_condition(switch_id)`.

**해결:** 해당 호출부를 `_make_switch_condition(quest_sw_id)`로 수정.

---

### 5.8 NPC condition_switch에 존재하지 않는 _defeated 스위치

**증상:** NpcEvent의 condition_switch가 `알고리즘_관리자_defeated` 등
switch_table에 없는 스위치를 참조 → 컴파일 실패.

**원인:** LLM이 보스 이름을 GameSpec과 다르게 기억하거나 변형하여 잘못된
_defeated 스위치를 지정.

**해결 (event_planner.py):**
```python
# _fix_npc_defeated_conditions()
# switch_table에 실제 존재하는 _defeated 스위치로 교체
# 없으면 condition_switch/alt_dialogue 제거
```

---

### 5.9 field 맵에서 boss 티어 적 등장

**증상:** field 맵에 보스급 적이 배치되어 게임 밸런스 붕괴.

**해결:** `_filter_troops_for_map()`에서 dungeon/field 맵에 boss 티어 제외:
```python
elif map_type in ("dungeon", "field"):
    filtered = [t for t in all_troops
                if enemy_tier.get(...) in ("weak", "normal", "elite")]
```

---

## 6. 현재 잔존하는 문제 및 개선 방향

### 6.1 [Critical] 고립 맵 auto_repair 의존

**현상:** `game_e6cbb065` Map003, Map006, Map007이 story_planner 단계에서 맵 연결이 누락되어
generation_validator의 auto_repair가 조건 없는 무조건 워프를 삽입.

```
[로그] generation_validator: 고립 맵 ['지하 터널', '화산 구역', '최종 제어실'] → auto_repair 실행
[로그] auto_repair: Map3 → '착륙 지점' 워프 이벤트 삽입 (20,1)
```

auto_repair 워프는 chest_switch 조건이 없어 아이템 획득 전에도 이동 가능해집니다.

**개선 방향:**
- `game_designer`의 맵 연결 구조 검증 강화 (단방향 연결 → 경고 → 재생성)
- `story_planner`에서 실제 exit_tile 위치 정보를 tile_generator로부터 전달받아
  존재하지 않는 출구로의 move 생성 방지

---

### 6.2 [High] battle quest_chest troop 없음 → 상자 영구 잠김

**현상:** troop 없는 battle quest_chest는 page1이 힌트만 출력하고
quest_switch를 ON할 방법이 없어 상자가 영구히 잠김.

```
[로그] QuestChestEvent '비상 통신기_chest': quest_type=battle이지만 troop 없음
       → npc 힌트 전용 폴백 (quest_switch ON 없음)
```

이 경우 chest_switch도 ON 안 되어 GateEvent 조건 미달성 → 게임 진행 불가.

**개선 방향:**
- `_ensure_acquisition_events()`의 troop 임베드 로직 강화:
  현재는 `e.troop` (사후 보정된 값)을 사용하지만, 맵에 BattleEvent가 없는 경우 폴백이 필요
- 컴파일러에서 troop 없는 battle quest_chest를 감지할 경우
  `generation_validator`에 오류를 전파하여 재생성 트리거

---

### 6.3 [High] chest + quest_chest 중복 공존

**현상:** LLM이 `chest` 타입으로 이미 생성한 아이템에 대해 `_ensure_acquisition_events()`가
`quest_chest`를 추가 삽입하는 경우가 아직 발생.

```
[로그] Map2('정글') acquisition '비상 통신기' quest_chest 누락 → 자동 삽입 ...
```
→ Map002에 `비상 통신기_chest`(LLM)와 `비상 통신기_퀘스트상자`(자동 삽입) 공존.

**개선 방향:**
- `_filter_extra_quest_chests()` 확장: `chest` 타입도 필터링 대상에 포함
  (아이템 배분은 반드시 quest_chest로만 처리하도록 강제)
- event_planner_prompt에서 chest 타입 사용 금지 명시:
  "무기/방어구/핵심 아이템은 반드시 quest_chest 사용, chest 타입 사용 금지"

---

### 6.4 [Medium] 게임 불변식 자동 검증 부재

**현상:** 컴파일 후 Map JSON 레벨에서 스위치 흐름 검증이 없어
버그가 `is_success=True`로 통과.

**개선 방향:** `generation_validator`에 다음 검사 추가:

```python
def _check_switch_flow(event_dsl, switch_table):
    for map_id, events in event_dsl.items():
        for e in events:
            if e.type == "quest_chest" and e.quest_type == "battle":
                # battle quest_switch를 ON할 수 있는 BattleEvent가 맵에 있는지 검증
                assert any_battle_sets(e.quest_switch, events), \
                    f"Map{map_id}: {e.name}의 quest_switch를 ON할 battle 이벤트 없음"
            if e.type == "gate":
                # gate의 condition_switches가 달성 가능한지 검증
                for sw in e.condition_switches:
                    assert can_be_activated(sw, events), \
                        f"Map{map_id}: gate 조건 '{sw}' 달성 불가"
```

---

### 6.5 [Medium] item_type 한국어 출력 반복

**현상:** LLM이 item_type을 매번 한국어로 출력 (`"무기"`, `"방어구"`).
자동 보정이 동작하나 로그 노이즈 발생.

```
[로그] story_planner: map_id=1 acquisition '경량 우주복' item_type '방어구'→'armor' 자동 보정
```

**개선 방향:** story_planner 프롬프트에 item_type 제약 추가:
```
item_type: 반드시 영문만 사용 — "item" | "weapon" | "armor"
```

---

### 6.6 [Low] BattleEvent one_time 페이지 미설정

**현상:** 일부 BattleEvent가 1페이지만 가져 전투 완료 후에도 이벤트가 맵에 남음.
내부 조건분기로 재전투는 방지되지만 시각적 잔재가 남음.

**개선 방향:** 전투 완료 후 이벤트를 투명 스프라이트(page2)로 전환:
```
Page 1 (battle_switch OFF): 몬스터 스프라이트 → 전투
Page 2 (battle_switch ON):  투명 스프라이트 → 아무것도 안 함
```

---

## 참고: 주요 관련 파일

| 파일 | 역할 |
|---|---|
| `agent/generation/nodes/asset_planner.py` | 스위치 사전 할당 (`_build_switch_table`) |
| `agent/generation/nodes/story_planner.py` | MapScreenplay 생성 + 검증 |
| `agent/generation/prompts/story_planner_prompt.py` | story_planner LLM 프롬프트 |
| `agent/generation/nodes/event_planner.py` | YAML DSL 생성 + 후처리 파이프라인 |
| `agent/generation/prompts/event_planner_prompt.py` | event_planner LLM 프롬프트 |
| `agent/generation/compilers/event_compiler.py` | DSL → RPG Maker MZ JSON |
| `agent/generation/compilers/dsl_models.py` | DSL Pydantic 모델 정의 |
| `agent/generation/nodes/generation_validator.py` | 불변식 검증 + auto_repair |
