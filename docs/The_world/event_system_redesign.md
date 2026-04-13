# 이벤트 시스템 재설계 계획

> 작성일: 2026-04-10
> 상태: 계획 수립
> 관련 분석: [event_interconnection_analysis.md](event_interconnection_analysis.md)

---

## 1. 설계 목표

### 플레이어 경험

```
마을 NPC "촌장"
  → "동굴에 마왕의 부하가 나타났소. 처치해주시오!" (퀘스트 부여)
  → quest_accepted ON

던전 입구 transfer
  → quest_accepted 확인 → 통과
  → 미확인 → "아직 마을에서 준비를 마치지 않았습니다."

던전 내부 battle
  → 승리 → boss_defeated ON
  → 패배 → game_over

마을 NPC "촌장" (다시 방문)
  → boss_defeated OFF → "부하가 동굴 깊은 곳에 있다고 합니다. 불 속성에 약해요." (힌트)
  → boss_defeated ON → "감사합니다! 이 검을 받으세요." (보상 + 다음 맵 게이트 해제)
```

### 핵심 원칙

1. **LLM은 창작만** — 대사, NPC 이름, 퀘스트 스토리, 아이템 선택
2. **코드가 구조를 강제** — 스위치 체인, 맵 이동 조건, 보상 지급, 이벤트 순서
3. **NPC 3단계 대화** — 퀘스트 부여 → 힌트 → 보상 (RPG Maker MZ 페이지로 구현)
4. **맵 게이트** — 조건 충족 없이 다음 맵 진행 불가
5. **보스 처치 → CommonEvent 엔딩** — 맵 독립적 엔딩

---

## 2. 아키텍처 변경

### 현재

```
story_planner(LLM) → event_planner(LLM) → event_compiler(코드)
  스토리 기획          이벤트 DSL 전체 생성    DSL → MZ JSON
```

**문제**: event_planner(LLM)가 구조(스위치 연결, 맵 게이트)까지 책임져야 해서 실패율이 높음.

### 변경

```
story_planner(LLM)     → event_scaffolder(코드)     → event_filler(LLM)     → event_compiler(코드)
  맵별 스토리/퀘스트 기획    이벤트 뼈대 + 스위치 체인     대사/디테일 창작 채우기     DSL → MZ JSON
```

| 노드 | 역할 | LLM? | 입력 | 출력 |
|---|---|---|---|---|
| story_planner | 맵별 퀘스트/NPC/보상 기획 | O | GameSpec, MapSpec[] | QuestScript (새 모델) |
| event_scaffolder | 이벤트 뼈대 + 스위치 체인 생성 | X | QuestScript, IdTable | EventSkeleton[] (DSL 뼈대) |
| event_filler | 대사, NPC 이름, 힌트 텍스트 채우기 | O | EventSkeleton[], GameSpec | DslEvent[] (완성된 DSL) |
| event_compiler | DSL → RPG Maker MZ JSON | X | DslEvent[] | compiled_events |

### 유지하는 것

- `event_compiler.py` — DSL → MZ JSON 변환 로직 (6개 컴파일 메서드)
- `dsl_models.py` — DSL 이벤트 모델 (NpcEvent, TransferEvent 등)
- `switch_table.py` — 스위치 ID 레지스트리
- `event_compiler_node.py` — 직렬 컴파일 오케스트레이션

### 변경/신규

- `models.py` — QuestScript 모델 추가 (MapStoryScript 대체)
- `story_planner.py` — 프롬프트 변경 (QuestScript 출력)
- `event_scaffolder.py` — **신규** (코드로 이벤트 뼈대 생성)
- `event_filler.py` — **신규** (LLM으로 대사 채우기)
- `event_planner.py` — 폐기 (scaffolder + filler로 분리)
- `integrator.py` — CommonEvent 엔딩 생성 추가

---

## 3. 새 데이터 모델

### QuestScript (story_planner 출력)

```python
class QuestStep(BaseModel):
    """퀘스트 1단계."""
    map_name: str                    # 이 단계가 발생하는 맵
    type: str                        # "talk" | "battle" | "collect" | "deliver"
    target: str                      # 대상 (NPC 이름 | 적 그룹 이름 | 아이템 이름)
    description: str                 # "촌장에게 말을 걸어 의뢰를 받는다"
    completion_switch: str           # 이 단계 완료 시 켜는 스위치

class Quest(BaseModel):
    """게임 내 퀘스트 1개."""
    name: str                        # "마왕 부하 토벌"
    steps: list[QuestStep]           # 순서대로 실행할 단계
    reward_item: str | None = None   # 완료 보상 아이템
    reward_switch: str | None = None # 완료 시 해제할 게이트 스위치

class MapQuestScript(BaseModel):
    """맵 1개의 퀘스트 정보."""
    map_id: int
    map_name: str
    map_type: str                    # town | dungeon | boss | field
    act_index: int                   # 3막 구조 (0, 1, 2)
    npcs: list[NpcRole]              # 이 맵의 NPC 역할 (이름은 LLM이 기획)
    gate_switch: str | None = None   # 이 맵 진입에 필요한 스위치 (이전 맵에서 SET)

class NpcRole(BaseModel):
    """NPC 1명의 역할."""
    name: str
    role: str                        # "퀘스트 부여자" | "상점" | "힌트 제공" | "가이드"
    quest_ref: str | None = None     # 연결된 Quest.name (퀘스트 NPC인 경우)

class GameQuestPlan(BaseModel):
    """게임 전체 퀘스트 계획 (story_planner 출력)."""
    quests: list[Quest]              # 메인/서브 퀘스트
    maps: list[MapQuestScript]       # 맵별 배치
    boss_name: str                   # 최종 보스 이름 (엔딩 트리거용)
```

### NPC 3페이지 패턴 (event_scaffolder가 생성)

```python
class NpcSkeleton(BaseModel):
    """NPC 이벤트 뼈대 — event_filler가 대사를 채움."""
    name: str
    x: int
    y: int
    role: str
    # Page 1: 퀘스트 부여 (조건 없음)
    quest_dialogue: list[str]        # ["_FILL_: 퀘스트 부여 대사"]  ← LLM이 채울 곳
    set_switch: str | None = None    # 퀘스트 수락 스위치
    give_item: str | None = None     # 기본 아이템 제공 (포션 등)
    # Page 2: 힌트 (quest_accepted ON, quest_complete OFF)
    hint_dialogue: list[str]         # ["_FILL_: 힌트 대사"]
    hint_switch: str | None = None   # quest_accepted 스위치
    # Page 3: 보상 (quest_complete ON)
    reward_dialogue: list[str]       # ["_FILL_: 보상 대사"]
    reward_switch: str | None = None # quest_complete 스위치
    reward_item: str | None = None   # 보상 아이템/무기
    unlock_switch: str | None = None # 다음 맵 게이트 해제
```

---

## 4. event_scaffolder 동작 (코드, LLM 없음)

### 맵 타입별 이벤트 뼈대 생성 규칙

#### town 맵

```python
def scaffold_town(map_script, quests, id_table, connection_info):
    events = []

    # 1. 가이드 NPC (첫 번째 NPC = 퀘스트 부여)
    quest = find_quest_starting_at(quests, map_script.map_name)
    events.append(NpcSkeleton(
        role="퀘스트 부여자",
        quest_dialogue=["_FILL_"],
        set_switch=f"{map_script.map_name}_quest_accepted",
        hint_dialogue=["_FILL_"],
        hint_switch=f"{map_script.map_name}_quest_accepted",
        reward_dialogue=["_FILL_"],
        reward_switch=quest.steps[-1].completion_switch,  # 퀘스트 마지막 단계
        reward_item=quest.reward_item,
        unlock_switch=quest.reward_switch,  # 다음 맵 게이트
    ))

    # 2. 상점 NPC
    events.append(ShopSkeleton(...))

    # 3. 힌트 NPC (추가 정보 제공)
    events.append(NpcSkeleton(role="마을 주민", ...))

    # 4. 맵 이동 (gate_switch 조건부)
    for exit in connection_info.exit_tiles:
        next_map = get_next_map(exit)
        events.append(TransferSkeleton(
            condition_switch=next_map.gate_switch,  # 코드가 자동 연결
            blocked_dialogue=["_FILL_"],            # LLM이 채울 힌트
        ))

    # 5. 보물상자 (선택, 퀘스트 보상으로)
    return events
```

#### dungeon 맵

```python
def scaffold_dungeon(map_script, quests, id_table, connection_info):
    events = []

    # 1. 입구 transfer (gate_switch 조건부)
    # 2. 전투 2~3개 (자동 배치, battle_switch 코드 생성)
    for i, troop in enumerate(select_troops(map_script, id_table)):
        battle_switch = f"{map_script.map_name}_battle_{i+1}"
        events.append(BattleSkeleton(
            troop=troop,
            battle_switch=battle_switch,
            on_win_switch=f"{map_script.map_name}_clear_{i+1}",
        ))

    # 3. 보물상자 (전투 승리 조건)
    events.append(ChestSkeleton(
        condition_switch=f"{map_script.map_name}_battle_1",  # 첫 전투 승리 후 출현
        item=select_item(id_table),
    ))

    # 4. 출구 transfer (모든 전투 승리 조건)
    events.append(TransferSkeleton(
        condition_switch=f"{map_script.map_name}_cleared",
        blocked_dialogue=["_FILL_"],
    ))

    # 5. 힌트 NPC (선택)
    events.append(NpcSkeleton(role="경고자", ...))

    return events
```

#### boss 맵

```python
def scaffold_boss(map_script, quests, id_table, boss_name):
    events = []

    # 1. 보스 전투
    events.append(BattleSkeleton(
        troop=f"{boss_name}_단독",
        battle_switch=f"{boss_name}_battle",
        on_win_switch=f"{boss_name}_defeated",
    ))

    # 2. 보스 전 NPC (경고/스토리)
    events.append(NpcSkeleton(role="보스 전 대화", ...))

    # 3. 탈출 transfer

    # 4. 엔딩은 CommonEvent로 처리 (맵 이벤트 아님)
    #    → integrator가 CommonEvents.json에 추가

    return events
```

### 스위치 체인 자동 연결 (핵심)

```python
def build_switch_chain(maps: list[MapQuestScript], quests: list[Quest]):
    """맵 순서대로 gate_switch를 자동 연결."""
    chain = {}
    for i, m in enumerate(maps):
        if i == 0:
            m.gate_switch = None  # 첫 맵은 무조건 진입
        else:
            prev_map = maps[i-1]
            # 이전 맵의 마지막 이벤트 완료 스위치 → 다음 맵 gate
            m.gate_switch = f"{prev_map.map_name}_cleared"
    return chain
```

---

## 5. event_filler 동작 (LLM)

scaffolder가 만든 뼈대의 `_FILL_` 부분만 LLM이 채움.

### LLM 입력

```yaml
## 맵: 시작 마을 (town, 1막)
테마: 중세 판타지
퀘스트: "마왕 부하 토벌" — 동굴에 나타난 마왕의 부하를 처치

### NPC 1: 퀘스트 부여자
역할: 마을 촌장, 용사에게 의뢰
- 퀘스트 부여 대사 (2~3문장): ___
- 힌트 대사 (퀘스트 진행 중, 1~2문장): ___
- 보상 대사 (퀘스트 완료, 1~2문장): ___
- NPC 이름: ___

### NPC 2: 상점 주인
역할: 무기/포션 판매
- 인사 대사 (1문장): ___
- NPC 이름: ___

### Transfer 1: 북쪽 들판 → 차단 시 메시지
- 차단 대사 (조건 미충족 시, 1문장): ___
```

### LLM 출력

```yaml
npc_1:
  name: "마르타 촌장"
  quest_dialogue:
    - "용사여, 동굴에 마왕의 부하가 나타났소!"
    - "마을 사람들이 두려워하고 있소. 부디 처치해주시오."
  hint_dialogue:
    - "마왕의 부하는 동굴 깊은 곳에 있다고 합니다. 불 속성에 약하니 마법사를 데려가시오."
  reward_dialogue:
    - "대단하오! 이 검으로 앞으로의 여정에 도움이 될 거요."
npc_2:
  name: "도마스 상인"
  greeting: "어서오세요! 좋은 물건 많습니다."
transfer_1:
  blocked_message: "아직 촌장과 이야기를 나누지 않았습니다."
```

**LLM은 구조를 모름** — 대사만 채우면 scaffolder가 만든 뼈대에 합쳐져서 완전한 DSL이 됨.

---

## 6. CommonEvent 엔딩

### 현재 문제
- 엔딩이 맵 이벤트로 구현 → 보스 맵에만 존재
- 보스가 여러 맵에 나오면 엔딩 중복

### 변경
- `integrator.py`에서 CommonEvents.json에 엔딩 이벤트 추가
- 보스 처치 스위치(예: `마왕_defeated`) → CommonEvent autorun → 엔딩 시퀀스
- 어느 맵에서든 보스를 잡으면 엔딩 트리거

```python
# integrator.py에 추가
def build_ending_common_event(boss_switch: str, ending_lines: list[str]) -> dict:
    return {
        "id": 1,
        "name": "엔딩",
        "switchId": boss_switch_id,  # 트리거 스위치
        "trigger": 2,  # Autorun (0=None, 1=Autorun... RPG MZ CommonEvent는 trigger 다름)
        "list": [
            # 페이드아웃 → 대사 → Return to Title
        ]
    }
```

---

## 7. 구현 순서

### Phase 1: 데이터 모델 + event_scaffolder (코드만)
1. `models.py`에 QuestScript/NpcSkeleton 등 새 모델 추가
2. `event_scaffolder.py` 신규 — 맵 타입별 뼈대 생성 + 스위치 체인 자동 연결
3. 테스트: scaffolder가 올바른 뼈대를 생성하는지 검증

### Phase 2: NPC 3페이지 컴파일러
1. `dsl_models.py`에 NpcEvent 확장 (3페이지 지원)
2. `event_compiler.py` _compile_npc 리팩토링 (1~3페이지)
3. 테스트: 3페이지 NPC 컴파일 검증

### Phase 3: event_filler (LLM 대사 채우기)
1. `event_filler.py` 신규 — 뼈대의 `_FILL_` 부분을 LLM으로 채우기
2. 프롬프트 설계 (구조 무시, 창작만)
3. 테스트: filler가 뼈대를 완성하는지 검증

### Phase 4: CommonEvent 엔딩
1. `integrator.py`에 CommonEvent 엔딩 생성 추가
2. EndingEvent를 맵 이벤트에서 제거
3. 테스트: CommonEvents.json에 엔딩이 들어가는지 검증

### Phase 5: 워크플로우 연결
1. `workflow.py`에 event_scaffolder → event_filler 노드 추가
2. event_planner 노드 제거 (scaffolder + filler로 대체)
3. story_planner 프롬프트를 QuestScript 출력으로 변경
4. 통합 테스트

### Phase 6: 실증 + 문서
1. 게임 생성 실행
2. 게임 데이터 분석 (스위치 체인, NPC 대화 흐름 검증)
3. 문서 업데이트

---

## 8. 리스크

| 리스크 | 대응 |
|---|---|
| story_planner가 QuestScript를 제대로 못 만듦 | 폴백: 맵 타입 기반 기본 퀘스트 자동 생성 |
| event_filler가 대사를 이상하게 채움 | 뼈대 구조는 코드가 보장하므로 최악의 경우 기본 대사 사용 |
| NPC 3페이지가 RPG Maker MZ에서 제대로 동작 안 함 | Phase 2에서 실제 MZ 엔진 테스트 선행 |
| CommonEvent 엔딩 트리거가 다른 이벤트와 충돌 | CommonEvent trigger 우선순위 확인 필요 |
