# 이벤트 간 연동(Switch Chain) 문제 분석

> 작성일: 2026-04-10
> 실증 데이터: game_2ea48646 ("용사의 마왕 토벌 작전")
> 관련 코드: `agent/generation/compilers/`, `agent/generation/nodes/event_planner.py`
> 개선안: [event_interconnection_improvement.md](event_interconnection_improvement.md) 참조

---

## 1. 현재 구조

```
B. asset_planner     ─→  SwitchTable 사전 할당 (boss_defeated, act_N_started, dungeon_cleared, game_cleared)
                          │
F. event_planner     ─→  LLM이 YAML DSL 출력 (맵별 병렬 생성 → G에서 직렬 컴파일)
                          │
G. event_compiler    ─→  DSL → RPG Maker MZ event commands (switch 동적 할당)
                          │
H. integrator        ─→  System.json.switches에 최종 기록
```

### DSL 이벤트 타입별 스위치 지원 현황

| DSL 타입 | condition_switch (조건 확인) | set_switch (스위치 설정) | 비고 |
|----------|:-:|:-:|------|
| **npc** | O | O | alt_dialogue로 2페이지 분기 |
| **battle** | - | O (on_win.set_switch) | battle_switch로 1회 제한 |
| **chest** | - | - | chest_switch로 1회 제한 |
| **transfer** | **X** | O | 무조건 이동 |
| **shop** | **X** | **X** | 스위치 지원 없음 |
| **ending** | O | - | Auto-Run 트리거 |

### 실증 대상: game_2ea48646

- 맵 6개: 시작 마을 → 숲 → 던전 입구 → 던전 깊은 곳 → 보스 룸 → 마왕의 성
- 스위치 37개 할당, 이벤트 총 51개
- 전투 13개, NPC 11개, 보물상자 8개, 이동 8개, 상점 1개, 엔딩 2개

---

## 2. 문제 분석

### 문제 1: Transfer가 무조건 이동 — 스토리 게이트 불가

**코드 근거**:

`TransferEvent`에 `condition_switch` 필드가 없다 (`dsl_models.py:29-41`). 컴파일러도 항상 `_empty_conditions()`로 페이지를 생성한다 (`event_compiler.py:184`).

```python
# event_compiler.py:184
page = _make_page(cmds, _empty_conditions(), ...)  # 조건 없이 항상 활성
```

**실증 — game_2ea48646의 이동 이벤트 전수 조사**:

| 맵 | 이벤트 | 목적지 | 조건 | trigger |
|---|---|---|---|---|
| Map001 | 숲_이동 | Map002 | **없음** | player_touch |
| Map002 | 시작_마을_이동 | Map001 | **없음** | player_touch |
| Map002 | 던전_입구_이동 | Map003 | **없음** | player_touch |
| Map003 | 숲_이동 | Map002 | **없음** | player_touch |
| Map003 | 던전_깊은_곳_이동 | Map004 | **없음** | player_touch |
| Map004 | 던전_입구 | Map003 | **없음** | player_touch |
| Map004 | 보스_룸_이동 | Map005 | **없음** | player_touch |
| Map005 | 보스 룸_탈출 | Map006 | **없음** | player_touch |

**8개 이동 전부 무조건.** 게임 시작 직후 시작 마을 → 숲 → 던전 입구 → 던전 깊은 곳 → 보스 룸 → 마왕의 성으로 직행 가능. 스토리 진행이 이동을 제한하지 않는다.

**영향**: "던전을 클리어해야 보스 맵으로 이동" 같은 RPG의 기본 진행 게이트가 존재하지 않음.

---

### 문제 2: 스위치 이름 충돌 — 같은 ID를 여러 맵이 재사용

**코드 근거**:

`resolve_switch_id` (`event_compiler.py:87-91`)는 이름으로 조회하여 같은 이름이면 같은 ID를 반환한다. LLM이 다른 맵에서 같은 스위치 이름을 사용하면 의도치 않게 연동된다.

```python
# event_compiler.py:87-91
def resolve_switch_id(self, name: str) -> int:
    if name not in self.switch_table.switches:
        self.switch_table, _ = self.switch_table.allocate_switch(name)
    return self.switch_table.switches[name]
```

**실증 — 충돌하는 스위치**:

| 스위치 | ID | 사용하는 맵 | 문제 |
|---|---|---|---|
| 고블린_battle_01 | 22 | Map002, Map003, Map004 | Map002에서 잡으면 나머지 맵 고블린도 전부 사라짐 |
| 늑대_전투_01 | 17 | Map002, Map003, Map004 | 동일 |
| 트롤_battle_01 | 23 | Map002, Map003, Map004 | 동일 |
| chest_01 | 11 | Map004, Map005 | Map004에서 열면 Map005 상자도 이미 열림 |
| chest_1_02 | 25 | Map002, Map003 | 동일 |

**특히 심각한 사례**: Map001 NPC "토드"가 `set_switch: chest_01`(#11)을 설정한다. 토드에게 말을 걸면 Map004와 Map005의 보물상자가 이미 열린 것으로 처리된다.

```
Map001 [토드] → SET switch [11] chest_01 = ON
Map004 [보물상자_01] → CHECK switch [11] chest_01 == OFF → 이미 ON이므로 획득 불가
Map005 [보물상자_01] → CHECK switch [11] chest_01 == OFF → 이미 ON이므로 획득 불가
```

**영향**: 한 맵의 행동이 다른 맵의 이벤트를 의도치 않게 비활성화. LLM이 스위치 이름의 글로벌 범위를 이해하지 못함.

---

### 문제 3: 참조되지만 설정되지 않는 스위치 (유령 조건)

**코드 근거**:

`_validate_name_refs()` (`event_planner.py:203-239`)는 맵 이름, 트룹 이름, 아이템 이름을 검증하지만 **스위치 이름은 검증하지 않는다.** `resolve_switch_id`가 없는 스위치를 자동 할당하므로, 오타든 존재하지 않는 참조든 새 ID가 발급되어 영원히 OFF인 스위치가 생긴다.

**실증 — 스위치 28 (고블린_배틀_01)**:

```
Map003 [고블린 족장] page2 조건: switch1Id=28 (고블린_배틀_01) == ON
```

스위치 28을 ON으로 설정하는 이벤트가 게임 전체에 **단 하나도 없다.** → 고블린 족장의 page2 대화가 영원히 활성화되지 않음.

참고: 스위치 22 `고블린_battle_01`과 스위치 28 `고블린_배틀_01`은 같은 의미이나 한글/영문 표기 차이로 별도 ID가 할당됨. LLM이 같은 개념에 다른 이름을 사용한 전형적인 사례.

**영향**: 스위치 검증이 없어서 오류가 빌드 시 발견되지 않고 런타임에 "이벤트가 반응하지 않는" 형태로 발현.

---

### 문제 4: 사전 할당 스위치 대량 미사용

**코드 근거**:

`_build_switch_table` (`asset_planner.py:139-161`)이 `act_N_started`, `dungeon_cleared`, `game_cleared` 등을 사전 할당하지만, LLM이 이 스위치들을 이벤트에서 실제로 참조할지는 보장하지 않는다.

**실증 — 사전 할당되었으나 미사용 스위치**:

| ID | 이름 | SET | CHECK | 상태 |
|---|---|:-:|:-:|---|
| 6 | act_2_started | O (Map004 이동 시) | X | 설정만 되고 아무도 확인 안 함 |
| 7 | act_3_started | X | X | 완전 미사용 |
| 8 | 던전 입구_cleared | X | X | 완전 미사용 |
| 9 | 던전 깊은 곳_cleared | X | X | 완전 미사용 |
| 10 | game_cleared | X | X | 완전 미사용 |
| 12 | 다크 엘프_battle_01 | X | X | 완전 미사용 |
| 14 | 던전_깊은_곳_이동 | X | X | 완전 미사용 |
| 16 | 고블린_전투_01 | X | X | 완전 미사용 |
| 18 | chest_01_01 | X | X | 완전 미사용 |
| 20 | 다크 엘프_전투_01 | X | X | 완전 미사용 |

37개 스위치 중 **10개(27%)가 완전 미사용**, `act_2_started`는 설정만 되고 확인하는 이벤트 없음. `game_cleared`가 미사용이라 게임 클리어 상태 추적 자체가 안 됨.

**영향**: asset_planner가 의미 있는 스위치를 사전 할당하지만, event_planner(LLM)가 이를 무시하고 자체 스위치를 만듦. 사전 할당의 의미가 없어짐.

---

### 문제 5: 전투 troop ID 전부 0 (빈 적 그룹)

**코드 근거**: 이 문제는 스위치 연동과 직접 관련은 없으나 게임 플레이에 치명적이므로 함께 기록.

**실증 — 13개 전투 전수 조사**:

```
Map002 고블린_전투:       BATTLE troop=0
Map002 늑대_전투:         BATTLE troop=0
Map002 트롤_전투:         BATTLE troop=0
Map003 고블린_전투:       BATTLE troop=0
Map003 늑대_전투:         BATTLE troop=0
Map003 트롤_전투:         BATTLE troop=0
Map003 다크_엘프_전투:    BATTLE troop=0
Map003 마왕의 부하_전투:  BATTLE troop=0
Map004 고블린_전투_01:    BATTLE troop=0
Map004 늑대_전투_01:      BATTLE troop=0
Map005 마왕 고르곤_전투:  BATTLE troop=0
Map006 다크 엘프_전투:    BATTLE troop=0
...전부 troop=0
```

RPG Maker MZ의 Troops 배열은 `[null, troop1, troop2, ...]`이므로 index 0은 null. **전투가 시작되면 빈 적 그룹과 싸우게 된다.**

---

### 문제 6: Shop에 스위치 지원 없음

**코드 근거**: `ShopEvent` (`dsl_models.py:99-109`)에 스위치 관련 필드가 없다.

**실증**:

```
Map005 [무기상인] page1: trigger=action conditions=[none]
  SHOP
```

보스 룸(Map005)에 무기상인이 있는데, 조건 없이 항상 활성. 보스전 전이든 후든 동일하게 접근 가능. 스토리상 "보스를 만나기 전에 마지막 장비 정비" 같은 의도가 있어도 조건으로 표현할 수 없음.

---

### 문제 7: 엔딩 이벤트 중복 — 스위치 이름 불일치

**실증**:

| 맵 | 이벤트 | 확인 스위치 | 동작 |
|---|---|---|---|
| Map005 | 엔딩_이벤트 | #2 `마왕 고르곤_defeated` | RETURN_TO_TITLE |
| Map006 | 엔딩_이벤트 | #36 `마왕_ 고르곤_defeat` | RETURN_TO_TITLE |

같은 보스에 대한 엔딩인데 **스위치 이름이 다르다** (`마왕 고르곤_defeated` vs `마왕_ 고르곤_defeat`). 두 엔딩은 서로 독립적이다.

Map005의 전투에서 스위치 #2를 설정하고, Map006의 전투에서 스위치 #36을 설정한다. 즉 Map005에서 보스를 잡으면 Map005 엔딩만 트리거되고, Map006에서 잡으면 Map006 엔딩만 트리거된다. **같은 보스가 두 맵에 각각 존재하는 비정상 구조.**

---

### 문제 8: 프롬프트에 연동 가이드 부족

**코드 근거**: `event_planner_prompt.py`에서 스위치 관련 안내는 사전 할당 스위치 이름 목록을 나열하는 것이 전부. 연동 패턴 예시, 맵 간 스위치 흐름 설계 방법, 스위치 네이밍 규칙이 없다.

**실증 — 위 문제들의 공통 원인**:

| 현상 | 프롬프트 부재 |
|---|---|
| 스위치 이름 충돌 (문제 2) | 네이밍 규칙 없음 |
| 유령 스위치 (문제 3) | 한글/영문 혼용 경고 없음 |
| 사전 할당 미사용 (문제 4) | "이 스위치를 반드시 사용하라"는 지시 없음 |
| 엔딩 중복 (문제 7) | 맵 간 스위치 공유 가이드 없음 |

---

## 3. 스위치 흐름 전체 도식

### 맵 간 이동 (전부 무조건)

```
Map001 (시작 마을)
  ↕ 무조건
Map002 (숲)
  ↕ 무조건
Map003 (던전 입구)
  ↕ 무조건
Map004 (던전 깊은 곳)
  ↓ 무조건
Map005 (보스 룸)
  ↓ 무조건
Map006 (마왕의 성)
```

### 스위치 연동이 실제로 작동하는 체인

```
Map005 [마왕 고르곤_전투] ──SET #2──→ Map005 [엔딩_이벤트] page2 autorun → RETURN_TO_TITLE
Map005 [마왕 고르곤_전투] ──SET #2──→ Map005 [다크 엘프] page2 (대화 변경)
Map006 [마왕 고르곤_전투] ──SET #36─→ Map006 [엔딩_이벤트] page2 autorun → RETURN_TO_TITLE
Map006 [마왕 고르곤_전투] ──SET #36─→ Map006 [마왕의 부하] page2 (대화 변경)
Map006 [마왕 고르곤_전투] ──SET #36─→ Map006 [저주받은 기사] page2 (대화 변경)
Map001 [마르타]           ──SET #5──→ Map001 [토드] page2 (대화 변경)
Map001 [마르타]           ──SET #5──→ Map001 [엘라] page2 (대화 변경)
```

작동하는 체인은 **같은 맵 내 NPC↔NPC, 같은 맵 내 전투→엔딩** 뿐. 맵을 넘나드는 연동은 없음.

### 끊어진 체인

```
Map003 [고블린 족장] page2 ──CHECK #28 (고블린_배틀_01)──→ 설정하는 이벤트 없음 (끊김)
                                                              (실제 전투는 #22 고블린_battle_01 사용)

사전 할당 스위치:
  #8  던전 입구_cleared    → 아무도 SET/CHECK 안 함
  #9  던전 깊은 곳_cleared → 아무도 SET/CHECK 안 함
  #10 game_cleared         → 아무도 SET/CHECK 안 함
```

---

## 4. 문제 요약

| # | 문제 | 심각도 | 원인 계층 |
|---|---|---|---|
| 1 | Transfer 무조건 이동 (스토리 게이트 불가) | **높음** | DSL 설계 |
| 2 | 스위치 이름 충돌 (NPC가 chest 스위치 오염) | **높음** | 프롬프트 + 검증 |
| 3 | 유령 스위치 (CHECK만 있고 SET 없음) | **높음** | 프롬프트 + 검증 |
| 4 | 사전 할당 스위치 대량 미사용 (27%) | 중간 | 프롬프트 |
| 5 | 전투 troop ID 전부 0 (빈 적 그룹) | **높음** | 컴파일러 버그 |
| 6 | Shop 스위치 미지원 | 낮음 | DSL 설계 |
| 7 | 엔딩 중복 (동일 보스, 다른 스위치 이름) | 중간 | 프롬프트 |
| 8 | 프롬프트 연동 가이드 부재 | **높음** | 프롬프트 |

### 가능/불가능 매트릭스

| 원하는 연동 패턴 | 가능 | 실증 |
|---|:-:|---|
| 보스 처치 → 같은 맵 NPC 대화 변경 | **O** | Map005 전투→다크엘프 page2, Map006 전투→마왕의 부하 page2 |
| 보스 처치 → 같은 맵 엔딩 트리거 | **O** | Map005 #2→엔딩, Map006 #36→엔딩 |
| NPC 대화 → 같은 맵 다른 NPC 변경 | **O** | Map001 마르타 #5→토드/엘라 page2 |
| 보스 처치 → **다른 맵** 이벤트 변경 | **X** | 맵 간 연동 사례 0건 |
| 전투 승리 → 다음 맵 이동 허용 | **X** | transfer에 condition_switch 없음 |
| 퀘스트 완료 → 상점 해금 | **X** | shop에 스위치 없음 |
| 아이템 소지 → NPC 반응 변경 | **X** | 아이템 조건 미지원 |
| 던전 클리어 → 진행 게이트 | **X** | dungeon_cleared 스위치 미사용 |

---

## 5. 참고: RPG Maker MZ 이벤트 커맨드 활용 현황

| 커맨드 | code | 용도 | 사용 여부 |
|---|---|---|:-:|
| Conditional Branch: Switch | 111, params [0, swId, 0] | 스위치 ON 확인 | O |
| Conditional Branch: Item | 111, params [4, itemId] | 아이템 소지 확인 | **X** |
| Conditional Branch: Variable | 111, params [1, varId, 0, value, op] | 변수 비교 | **X** |
| Control Variables | 122 | 변수 값 변경 | **X** |
| Change Items | 126, params [itemId, 0, op, amount] | 아이템 증감 | O (chest/battle) |
| Control Switches | 121, params [swId, swId, 0] | 스위치 ON | O |
| Control Self-Switch | 123 | 이벤트 로컬 스위치 | **X** |
