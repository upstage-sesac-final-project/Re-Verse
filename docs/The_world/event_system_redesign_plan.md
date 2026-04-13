# 이벤트 시스템 재설계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM은 창작(대사/퀘스트 스토리)만 담당하고, 코드가 이벤트 구조(스위치 체인, 맵 게이트, NPC 3단계 대화, 보상 연동)를 강제하는 이벤트 시스템으로 재설계한다.

**Architecture:** `story_planner(LLM)` → `event_scaffolder(코드)` → `event_filler(LLM)` → `event_compiler(코드)`. scaffolder가 맵 타입별 이벤트 뼈대+스위치 체인을 결정론적으로 생성하고, filler가 대사만 채운다. 엔딩은 CommonEvent로 맵 독립 처리.

**Tech Stack:** Python 3.12, Pydantic, LangGraph, LangChain (Solar Pro 2), pytest, YAML

**기존 유지:** 이미지 매핑 (`_build_troop_sprite_map`, `_BATTLER_TO_MAP_SPRITE`, `_fix_battle_sprites` — `event_planner.py:401-613`)은 그대로 보존하여 새 모듈로 분리.

---

## 파일 구조

### 신규 생성

| 파일 | 역할 |
|---|---|
| `agent/generation/nodes/event_scaffolder.py` | 이벤트 뼈대 + 스위치 체인 생성 (코드, LLM 없음) |
| `agent/generation/nodes/event_filler.py` | 뼈대의 대사를 LLM으로 채우기 |
| `agent/generation/prompts/event_filler_prompt.py` | event_filler LLM 프롬프트 |
| `agent/generation/sprite_mapping.py` | 스프라이트 매핑 로직 분리 (event_planner.py:401-613에서 추출) |
| `agent/tests/generation/test_event_scaffolder.py` | scaffolder 테스트 |
| `agent/tests/generation/test_event_filler.py` | filler 테스트 |

### 수정

| 파일 | 변경 내용 |
|---|---|
| `agent/generation/models.py` | QuestScript 모델 추가, MapStoryScript는 유지 (하위 호환) |
| `agent/generation/compilers/dsl_models.py` | NpcEvent에 3페이지 필드 추가 |
| `agent/generation/compilers/event_compiler.py` | _compile_npc 3페이지 지원 |
| `agent/generation/nodes/integrator.py` | CommonEvent 엔딩 생성 추가 |
| `agent/generation/workflow.py` | event_planner → scaffolder+filler 교체 |
| `agent/generation/state.py` | event_skeleton 필드 추가 |
| `agent/generation/prompts/story_planner_prompt.py` | QuestScript 출력 유도 |
| `agent/generation/nodes/story_planner.py` | QuestScript 파싱 + 폴백 |
| `agent/tests/generation/test_event_compiler.py` | NPC 3페이지 테스트 추가 |

### 삭제/비활성화

| 파일 | 처리 |
|---|---|
| `agent/generation/nodes/event_planner.py` | 스프라이트 매핑 코드만 `sprite_mapping.py`로 추출 후 삭제 |
| `agent/generation/prompts/event_planner_prompt.py` | 삭제 (filler 프롬프트로 대체) |

---

## Phase 1: 데이터 모델 + event_scaffolder (코드만)

### Task 1: QuestScript 모델 정의

**Files:**
- Modify: `agent/generation/models.py`
- Test: `agent/tests/generation/test_event_scaffolder.py`

- [ ] **Step 1: 테스트 파일 생성 + 모델 임포트 테스트**

`agent/tests/generation/test_event_scaffolder.py` 생성:

```python
"""event_scaffolder 유닛 테스트."""

from agent.generation.models import (
    GameQuestPlan,
    MapQuestScript,
    NpcRole,
    Quest,
    QuestStep,
)


def test_quest_step_model() -> None:
    step = QuestStep(
        map_name="동굴",
        type="battle",
        target="고블린_단독",
        description="고블린 대장을 처치한다",
        completion_switch="동굴_battle_1",
    )
    assert step.completion_switch == "동굴_battle_1"


def test_quest_model() -> None:
    quest = Quest(
        name="마왕 부하 토벌",
        steps=[
            QuestStep(
                map_name="마을",
                type="talk",
                target="촌장",
                description="촌장에게 의뢰를 받는다",
                completion_switch="마을_quest_accepted",
            ),
            QuestStep(
                map_name="동굴",
                type="battle",
                target="고블린_단독",
                description="고블린을 처치한다",
                completion_switch="동굴_고블린_defeated",
            ),
        ],
        reward_item="강철 검",
        reward_switch="동굴_cleared",
    )
    assert len(quest.steps) == 2
    assert quest.reward_item == "강철 검"


def test_game_quest_plan_model() -> None:
    plan = GameQuestPlan(
        quests=[
            Quest(
                name="메인 퀘스트",
                steps=[
                    QuestStep(
                        map_name="마을", type="talk", target="촌장",
                        description="시작", completion_switch="quest_start",
                    )
                ],
                reward_switch="마을_cleared",
            )
        ],
        maps=[
            MapQuestScript(
                map_id=1, map_name="마을", map_type="town", act_index=0,
                npcs=[NpcRole(name="촌장", role="퀘스트 부여자", quest_ref="메인 퀘스트")],
            ),
        ],
        boss_name="마왕",
    )
    assert plan.boss_name == "마왕"
    assert plan.maps[0].npcs[0].quest_ref == "메인 퀘스트"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest agent/tests/generation/test_event_scaffolder.py -v`
Expected: FAIL (모델 미정의)

- [ ] **Step 3: models.py에 QuestScript 모델 추가**

`agent/generation/models.py` 끝에 추가:

```python
# ── 이벤트 재설계: QuestScript 모델 ──────────────────────────────────────────


class QuestStep(BaseModel):
    """퀘스트 1단계."""

    map_name: str
    type: str  # "talk" | "battle" | "collect" | "deliver"
    target: str  # NPC 이름 | 적 그룹 이름 | 아이템 이름
    description: str
    completion_switch: str


class Quest(BaseModel):
    """게임 내 퀘스트 1개."""

    name: str
    steps: list[QuestStep]
    reward_item: str | None = None
    reward_switch: str | None = None  # 완료 시 해제할 게이트 스위치


class NpcRole(BaseModel):
    """NPC 1명의 역할."""

    name: str
    role: str  # "퀘스트 부여자" | "상점" | "힌트 제공" | "가이드"
    quest_ref: str | None = None  # 연결된 Quest.name


class MapQuestScript(BaseModel):
    """맵 1개의 퀘스트 배치."""

    map_id: int
    map_name: str
    map_type: str  # town | dungeon | boss | field
    act_index: int = 0
    npcs: list[NpcRole] = []
    gate_switch: str | None = None  # 이 맵 진입에 필요한 스위치


class GameQuestPlan(BaseModel):
    """게임 전체 퀘스트 계획 (story_planner 출력)."""

    quests: list[Quest]
    maps: list[MapQuestScript]
    boss_name: str
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_scaffolder.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add agent/generation/models.py agent/tests/generation/test_event_scaffolder.py
git commit -m "feat: QuestScript 모델 추가 (이벤트 재설계 Phase 1)"
```

---

### Task 2: event_scaffolder 핵심 로직 구현

**Files:**
- Create: `agent/generation/nodes/event_scaffolder.py`
- Test: `agent/tests/generation/test_event_scaffolder.py`

- [ ] **Step 1: scaffolder 테스트 추가**

`test_event_scaffolder.py`에 추가:

```python
from agent.generation.compilers.dsl_models import (
    BattleEvent,
    ChestEvent,
    EndingEvent,
    NpcEvent,
    ShopEvent,
    TransferEvent,
)
from agent.generation.models import (
    ExitSpec,
    GameQuestPlan,
    GameSpec,
    LandmarkSpec,
    MapQuestScript,
    MapSpec,
    NpcRole,
    Quest,
    QuestStep,
)
from agent.generation.nodes.event_scaffolder import scaffold_map_events
from agent.generation.registry.id_table import IdTable


def _make_id_table() -> IdTable:
    return IdTable(
        actors={"용사": 1},
        items={"회복 포션": 1, "강철 검": 2},
        weapons={"나무 검": 1, "강철 검": 2},
        armors={"가죽 갑옷": 1},
        enemies={"고블린": 1, "마왕": 2},
        troops={"고블린×1": 1, "고블린×2": 2, "마왕_단독": 3},
        maps={"시작 마을": 1, "어둠의 동굴": 2, "마왕의 성": 3},
    )


def _make_map_spec(
    map_id: int, name: str, map_type: str, exits: list[ExitSpec] | None = None,
) -> MapSpec:
    return MapSpec(
        map_id=map_id, name=name, map_type=map_type,
        width=30, height=30, tileset_id=1, bgm="Town1",
        atmosphere="평화로운", landmarks=[], spawn_point=(15, 15),
        exits=exits or [],
    )


def _make_quest_plan() -> GameQuestPlan:
    return GameQuestPlan(
        quests=[
            Quest(
                name="고블린 토벌",
                steps=[
                    QuestStep(
                        map_name="시작 마을", type="talk", target="촌장",
                        description="촌장에게 의뢰를 받는다",
                        completion_switch="시작_마을_quest_accepted",
                    ),
                    QuestStep(
                        map_name="어둠의 동굴", type="battle", target="고블린×2",
                        description="고블린을 처치한다",
                        completion_switch="어둠의_동굴_고블린_defeated",
                    ),
                ],
                reward_item="강철 검",
                reward_switch="어둠의_동굴_cleared",
            ),
        ],
        maps=[
            MapQuestScript(
                map_id=1, map_name="시작 마을", map_type="town", act_index=0,
                npcs=[NpcRole(name="촌장", role="퀘스트 부여자", quest_ref="고블린 토벌")],
            ),
            MapQuestScript(
                map_id=2, map_name="어둠의 동굴", map_type="dungeon", act_index=1,
                npcs=[NpcRole(name="모험가", role="힌트 제공")],
                gate_switch="시작_마을_quest_accepted",
            ),
            MapQuestScript(
                map_id=3, map_name="마왕의 성", map_type="boss", act_index=2,
                npcs=[],
                gate_switch="어둠의_동굴_cleared",
            ),
        ],
        boss_name="마왕",
    )


def test_scaffold_town_has_quest_npc() -> None:
    """town 맵: 퀘스트 NPC가 3페이지 (부여/힌트/보상) 구조를 가짐."""
    id_table = _make_id_table()
    plan = _make_quest_plan()
    map_spec = _make_map_spec(
        1, "시작 마을", "town",
        exits=[ExitSpec(direction="north", to_map_id=2, label="어둠의 동굴")],
    )

    events = scaffold_map_events(map_spec, plan, id_table)

    # NPC 이벤트 확인
    npcs = [e for e in events if isinstance(e, NpcEvent)]
    assert len(npcs) >= 1
    quest_npc = npcs[0]
    # 3페이지 NPC는 hint_switch + reward_switch가 있어야 함
    assert quest_npc.set_switch is not None  # 퀘스트 수락 스위치
    assert quest_npc.condition_switch is not None  # 보상 조건 스위치
    assert quest_npc.alt_dialogue is not None  # 보상 대사

    # Transfer 확인 (게이트)
    transfers = [e for e in events if isinstance(e, TransferEvent)]
    assert len(transfers) >= 1


def test_scaffold_dungeon_has_gated_transfer() -> None:
    """dungeon 맵: 입구 transfer에 gate_switch 조건이 걸림."""
    id_table = _make_id_table()
    plan = _make_quest_plan()
    map_spec = _make_map_spec(
        2, "어둠의 동굴", "dungeon",
        exits=[
            ExitSpec(direction="south", to_map_id=1, label="시작 마을"),
            ExitSpec(direction="north", to_map_id=3, label="마왕의 성"),
        ],
    )

    events = scaffold_map_events(map_spec, plan, id_table)

    # 전투 이벤트 확인
    battles = [e for e in events if isinstance(e, BattleEvent)]
    assert len(battles) >= 1
    assert battles[0].battle_switch is not None
    assert battles[0].on_win  # on_win 액션이 있어야 함

    # 보물상자 확인 (전투 승리 조건)
    chests = [e for e in events if isinstance(e, ChestEvent)]
    assert len(chests) >= 1
    assert chests[0].condition_switch is not None  # 전투 승리 후 출현


def test_scaffold_boss_has_battle_and_no_ending_event() -> None:
    """boss 맵: 보스 전투가 있고 ending 이벤트는 없음 (CommonEvent로 처리)."""
    id_table = _make_id_table()
    plan = _make_quest_plan()
    map_spec = _make_map_spec(
        3, "마왕의 성", "boss",
        exits=[ExitSpec(direction="south", to_map_id=2, label="어둠의 동굴")],
    )

    events = scaffold_map_events(map_spec, plan, id_table)

    battles = [e for e in events if isinstance(e, BattleEvent)]
    assert len(battles) == 1
    assert "마왕" in battles[0].troop

    # 엔딩은 CommonEvent로 처리 → 맵 이벤트에 EndingEvent 없음
    endings = [e for e in events if isinstance(e, EndingEvent)]
    assert len(endings) == 0

    # 이벤트 수 상한
    assert len(events) <= 10
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest agent/tests/generation/test_event_scaffolder.py::test_scaffold_town_has_quest_npc -v`
Expected: FAIL (scaffold_map_events 미정의)

- [ ] **Step 3: event_scaffolder.py 구현**

`agent/generation/nodes/event_scaffolder.py` 생성:

```python
"""이벤트 뼈대 생성 — 맵 타입별 이벤트 구조 + 스위치 체인을 코드로 강제.

LLM 호출 없음. 결정론적 로직으로 이벤트 뼈대를 생성하고,
event_filler가 대사를 채운다.
"""

import logging
import random
from typing import Any

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    BattleOnWinAction,
    ChestEvent,
    NpcEvent,
    ShopEvent,
    TransferEvent,
)
from agent.generation.models import (
    GameQuestPlan,
    MapQuestScript,
    MapSpec,
    Quest,
)
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import normalize_switch_name
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_FILL = "_FILL_"  # event_filler가 채울 플레이스홀더


def scaffold_map_events(
    map_spec: MapSpec,
    quest_plan: GameQuestPlan,
    id_table: IdTable,
) -> list:
    """맵 1개의 이벤트 뼈대를 생성한다.

    Returns:
        list[DslEvent] — 대사가 _FILL_ 플레이스홀더인 DSL 이벤트 목록
    """
    map_script = _find_map_script(quest_plan, map_spec.name)
    quest = _find_quest_for_map(quest_plan, map_spec.name)
    prefix = normalize_switch_name(map_spec.name)

    match map_spec.map_type:
        case "town":
            return _scaffold_town(map_spec, map_script, quest, id_table, prefix)
        case "dungeon" | "field":
            return _scaffold_dungeon(map_spec, map_script, quest, id_table, prefix)
        case "boss":
            return _scaffold_boss(map_spec, map_script, quest, id_table, prefix, quest_plan)
        case _:
            return _scaffold_dungeon(map_spec, map_script, quest, id_table, prefix)


def _find_map_script(plan: GameQuestPlan, map_name: str) -> MapQuestScript | None:
    for m in plan.maps:
        if m.map_name == map_name:
            return m
    return None


def _find_quest_for_map(plan: GameQuestPlan, map_name: str) -> Quest | None:
    """이 맵에서 시작하거나 진행하는 퀘스트를 찾는다."""
    for q in plan.quests:
        for step in q.steps:
            if step.map_name == map_name:
                return q
    return None


# ── 좌표 생성 ──────────────────────────────────────────────────────────────


def _safe_coords(
    w: int, h: int, used: set[tuple[int, int]], margin: int = 2,
) -> tuple[int, int]:
    """사용되지 않은 좌표를 반환한다. 맵 가장자리 margin만큼 여백."""
    for _ in range(100):
        x = random.randint(margin, w - margin - 1)
        y = random.randint(margin, h - margin - 1)
        if (x, y) not in used:
            used.add((x, y))
            return x, y
    # fallback
    x, y = w // 2, h // 2
    while (x, y) in used:
        x += 1
    used.add((x, y))
    return x, y


def _exit_coords(
    spec: MapSpec, direction: str,
) -> tuple[int, int]:
    """출구 방향에 따른 맵 가장자리 좌표."""
    cx, cy = spec.width // 2, spec.height // 2
    return {
        "north": (cx, 1),
        "south": (cx, spec.height - 2),
        "east": (spec.width - 2, cy),
        "west": (1, cy),
    }.get(direction, (cx, cy))


# ── Town ────────────────────────────────────────────────────────────────────


def _scaffold_town(
    spec: MapSpec,
    map_script: MapQuestScript | None,
    quest: Quest | None,
    id_table: IdTable,
    prefix: str,
) -> list:
    events: list = []
    used: set[tuple[int, int]] = set()

    # 1. 퀘스트 NPC (3페이지: 부여/힌트/보상)
    if quest:
        x, y = _safe_coords(spec.width, spec.height, used)
        quest_accept_sw = f"{prefix}_quest_accepted"
        quest_complete_sw = quest.steps[-1].completion_switch if quest.steps else None
        events.append(NpcEvent(
            type="npc",
            name=map_script.npcs[0].name if map_script and map_script.npcs else "촌장",
            x=x, y=y,
            dialogue=[_FILL],  # Page 1: 퀘스트 부여
            set_switch=quest_accept_sw,
            give_item=quest.reward_item if quest.reward_item and quest.reward_item in id_table.items else None,
            # Page 2/3은 condition_switch + alt_dialogue로 구현
            # hint: quest_accepted ON + quest_complete OFF → 힌트
            # reward: quest_complete ON → 보상
            condition_switch=quest_complete_sw,
            alt_dialogue=[_FILL],  # Page 2: 보상 대사
            # hint는 별도 NPC로 분리 (RPG Maker MZ 2페이지 제한 때문)
        ))

    # 2. 힌트 NPC (퀘스트 진행 중일 때 힌트)
    if quest:
        x, y = _safe_coords(spec.width, spec.height, used)
        quest_accept_sw = f"{prefix}_quest_accepted"
        events.append(NpcEvent(
            type="npc",
            name=map_script.npcs[1].name if map_script and len(map_script.npcs) > 1 else "마을 주민",
            x=x, y=y,
            dialogue=[_FILL],  # 일반 대사
            condition_switch=quest_accept_sw,
            alt_dialogue=[_FILL],  # 퀘스트 수락 후 힌트
        ))

    # 3. 상점 NPC
    shop_items = _select_shop_items(id_table)
    if shop_items:
        x, y = _safe_coords(spec.width, spec.height, used)
        events.append(ShopEvent(
            type="shop",
            name="상인",
            x=x, y=y,
            dialogue=_FILL,
            items=shop_items,
        ))

    # 4. Transfer 이벤트 (다음 맵으로 — 게이트 조건부)
    for exit_spec in spec.exits:
        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))
        # 다음 맵의 gate_switch 확인
        next_gate = None
        if map_script:
            # quest_accepted가 있으면 그걸 게이트로
            next_gate = f"{prefix}_quest_accepted" if quest else None
        events.append(TransferEvent(
            type="transfer",
            name=f"{exit_spec.label}_이동",
            x=ex, y=ey,
            to_map=exit_spec.label,
            to_x=spec.width // 2,
            to_y=spec.height // 2,
            condition_switch=next_gate,
            blocked_dialogue=_FILL if next_gate else None,
        ))

    return events


# ── Dungeon / Field ─────────────────────────────────────────────────────────


def _scaffold_dungeon(
    spec: MapSpec,
    map_script: MapQuestScript | None,
    quest: Quest | None,
    id_table: IdTable,
    prefix: str,
) -> list:
    events: list = []
    used: set[tuple[int, int]] = set()

    # 1. 전투 이벤트 (2~3개)
    troops = _select_troops_for_map(spec.map_type, id_table)
    battle_switches: list[str] = []
    for i, troop in enumerate(troops[:3]):
        x, y = _safe_coords(spec.width, spec.height, used)
        battle_sw = f"{prefix}_battle_{i + 1}"
        win_sw = f"{prefix}_clear_{i + 1}"
        battle_switches.append(win_sw)
        events.append(BattleEvent(
            type="battle",
            name=f"{troop.split('×')[0].split('_')[0]}_전투",
            x=x, y=y,
            troop=troop,
            battle_switch=battle_sw,
            one_time=True,
            on_win=[BattleOnWinAction(set_switch=win_sw)],
        ))

    # 2. 보물상자 (첫 전투 승리 후 출현)
    if battle_switches:
        x, y = _safe_coords(spec.width, spec.height, used)
        item_name = _select_chest_item(id_table)
        item_type = _resolve_item_type(item_name, id_table)
        events.append(ChestEvent(
            type="chest",
            name=f"{prefix}_보물상자",
            x=x, y=y,
            item=item_name,
            item_type=item_type,
            condition_switch=battle_switches[0],
            chest_switch=f"{prefix}_chest_1",
            one_time=True,
        ))

    # 3. 힌트 NPC
    if map_script and map_script.npcs:
        x, y = _safe_coords(spec.width, spec.height, used)
        events.append(NpcEvent(
            type="npc",
            name=map_script.npcs[0].name,
            x=x, y=y,
            dialogue=[_FILL],
        ))

    # 4. Transfer (입구/출구)
    cleared_sw = f"{prefix}_cleared"
    for exit_spec in spec.exits:
        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))
        events.append(TransferEvent(
            type="transfer",
            name=f"{exit_spec.label}_이동",
            x=ex, y=ey,
            to_map=exit_spec.label,
            to_x=spec.width // 2,
            to_y=spec.height // 2,
        ))

    # 5. 던전 클리어 스위치 설정 (마지막 전투 승리 시)
    if battle_switches and events:
        for e in events:
            if isinstance(e, BattleEvent) and e == events[len(battle_switches) - 1 if battle_switches else 0]:
                e.on_win.append(BattleOnWinAction(set_switch=cleared_sw))
                break

    return events


# ── Boss ────────────────────────────────────────────────────────────────────


def _scaffold_boss(
    spec: MapSpec,
    map_script: MapQuestScript | None,
    quest: Quest | None,
    id_table: IdTable,
    prefix: str,
    quest_plan: GameQuestPlan,
) -> list:
    events: list = []
    used: set[tuple[int, int]] = set()
    boss_name = quest_plan.boss_name
    boss_troop = _find_boss_troop(boss_name, id_table)
    defeated_sw = normalize_switch_name(f"{boss_name}_defeated")

    # 1. 보스 전투
    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(BattleEvent(
        type="battle",
        name=f"{boss_name}_전투",
        x=x, y=y,
        troop=boss_troop,
        battle_switch=f"{prefix}_boss_battle",
        one_time=True,
        lose_condition="game_over",
        on_win=[BattleOnWinAction(set_switch=defeated_sw)],
    ))

    # 2. 보스 전 NPC (스토리 대사)
    if map_script and map_script.npcs:
        x, y = _safe_coords(spec.width, spec.height, used)
        events.append(NpcEvent(
            type="npc",
            name=map_script.npcs[0].name,
            x=x, y=y,
            dialogue=[_FILL],
            condition_switch=defeated_sw,
            alt_dialogue=[_FILL],
        ))

    # 3. 탈출 Transfer
    for exit_spec in spec.exits:
        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))
        events.append(TransferEvent(
            type="transfer",
            name=f"{exit_spec.label}_이동",
            x=ex, y=ey,
            to_map=exit_spec.label,
            to_x=spec.width // 2,
            to_y=spec.height // 2,
        ))

    # 엔딩은 CommonEvent로 처리 — 맵 이벤트에 EndingEvent 없음
    return events


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _select_troops_for_map(map_type: str, id_table: IdTable) -> list[str]:
    """맵 타입에 맞는 적 그룹을 선택한다."""
    all_troops = list(id_table.troops.keys())
    # boss 전용 troop 제외 (이름에 _단독 포함)
    if map_type in ("dungeon", "field"):
        return [t for t in all_troops if "_단독" not in t][:3]
    return all_troops[:2]


def _find_boss_troop(boss_name: str, id_table: IdTable) -> str:
    """보스 이름으로 troop을 찾는다."""
    for troop_name in id_table.troops:
        if boss_name in troop_name:
            return troop_name
    return f"{boss_name}_단독"


def _select_shop_items(id_table: IdTable) -> list:
    """상점 아이템 목록을 생성한다."""
    from agent.generation.compilers.dsl_models import ShopItem

    items = []
    for name in list(id_table.items.keys())[:3]:
        items.append(ShopItem(item=name, item_type="item"))
    for name in list(id_table.weapons.keys())[:2]:
        items.append(ShopItem(item=name, item_type="weapon"))
    return items[:5]


def _select_chest_item(id_table: IdTable) -> str:
    """보물상자에 넣을 아이템을 선택한다."""
    if id_table.items:
        return list(id_table.items.keys())[0]
    if id_table.weapons:
        return list(id_table.weapons.keys())[0]
    return "회복 포션"


def _resolve_item_type(item_name: str, id_table: IdTable) -> str:
    if item_name in id_table.items:
        return "item"
    if item_name in id_table.weapons:
        return "weapon"
    if item_name in id_table.armors:
        return "armor"
    return "item"


# ── 워크플로우 노드 ────────────────────────────────────────────────────────


async def event_scaffolder(state: GenerationState) -> dict:
    """이벤트 뼈대 생성 노드 (LLM 없음)."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    quest_plan: GameQuestPlan | None = state.get("quest_plan")  # type: ignore[assignment]

    if quest_plan is None:
        quest_plan = _fallback_quest_plan(map_specs, id_table)

    await publish_progress(
        gen_id,
        {"type": "progress", "phase": "event_scaffold", "progress": 65, "message": "이벤트 뼈대 생성 중..."},
    )

    event_skeletons: dict[int, list] = {}
    for spec in map_specs:
        events = scaffold_map_events(spec, quest_plan, id_table)
        event_skeletons[spec.map_id] = events

    logger.info("event_scaffolder 완료: %d개 맵", len(event_skeletons))

    await publish_progress(
        gen_id,
        {"type": "phase_complete", "phase": "event_scaffold", "summary": f"{len(event_skeletons)}개 맵 이벤트 뼈대 생성"},
    )

    completed = list(state.get("completed_phases", []))
    completed.append("event_scaffold")
    return {"event_skeletons": event_skeletons, "completed_phases": completed}


def _fallback_quest_plan(map_specs: list[MapSpec], id_table: IdTable) -> GameQuestPlan:
    """story_planner 실패 시 기본 퀘스트 계획."""
    from agent.generation.models import Quest, QuestStep, MapQuestScript, NpcRole

    maps = []
    quests = []
    boss_name = "보스"

    # 적 이름에서 보스 찾기
    for troop_name in id_table.troops:
        if "_단독" in troop_name:
            candidate = troop_name.replace("_단독", "")
            boss_name = candidate
            break

    prev_cleared: str | None = None
    for i, spec in enumerate(map_specs):
        prefix = normalize_switch_name(spec.name)
        gate = prev_cleared
        maps.append(MapQuestScript(
            map_id=spec.map_id,
            map_name=spec.name,
            map_type=spec.map_type,
            act_index=min(i, 2),
            npcs=[NpcRole(name=f"NPC_{i+1}", role="가이드")],
            gate_switch=gate,
        ))
        prev_cleared = f"{prefix}_cleared"

    return GameQuestPlan(quests=quests, maps=maps, boss_name=boss_name)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_scaffolder.py -v`
Expected: PASS

- [ ] **Step 5: ruff + 전체 generation 테스트**

Run: `uv run ruff check agent/generation/nodes/event_scaffolder.py && uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add agent/generation/nodes/event_scaffolder.py agent/tests/generation/test_event_scaffolder.py
git commit -m "feat: event_scaffolder 구현 — 맵 타입별 이벤트 뼈대 + 스위치 체인 (Phase 1)"
```

---

## Phase 2: NPC 3페이지 컴파일러

### Task 3: NPC 힌트 페이지 지원 (hint_switch + hint_dialogue)

**Files:**
- Modify: `agent/generation/compilers/dsl_models.py` (NpcEvent)
- Modify: `agent/generation/compilers/event_compiler.py` (_compile_npc)
- Test: `agent/tests/generation/test_event_compiler.py`

- [ ] **Step 1: 테스트 추가**

`test_event_compiler.py`에 추가:

```python
def test_compile_npc_three_pages(compiler: EventCompiler) -> None:
    """NPC 3페이지: page1=퀘스트부여, page2=힌트, page3=보상."""
    event = NpcEvent(
        type="npc", name="촌장", x=5, y=5,
        dialogue=["마왕을 처치해주세요!"],  # page1: 퀘스트 부여
        set_switch="quest_accepted",
        hint_switch="quest_accepted",  # page2 조건: 수락 후
        hint_dialogue=["마왕은 동굴 깊은 곳에 있어요."],
        condition_switch="boss_defeated",  # page3 조건: 완료 후
        alt_dialogue=["감사합니다! 이 보물을 받으세요."],
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 3
    # page1: 조건 없음 (퀘스트 부여)
    assert result["pages"][0]["conditions"]["switch1Valid"] is False
    # page2: quest_accepted ON (힌트)
    assert result["pages"][1]["conditions"]["switch1Valid"] is True
    # page3: boss_defeated ON (보상)
    assert result["pages"][2]["conditions"]["switch1Valid"] is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py::test_compile_npc_three_pages -v`
Expected: FAIL (hint_switch 필드 없음)

- [ ] **Step 3: NpcEvent에 hint 필드 추가**

`dsl_models.py`의 NpcEvent에 추가:

```python
class NpcEvent(BaseModel):
    type: Literal["npc"]
    name: str
    x: int
    y: int
    trigger: Literal["action_button"] = "action_button"
    character_name: str = "People1"
    character_index: int = 0
    face_image: str = ""
    face_index: int = 0
    dialogue: list[str]
    condition_switch: str | None = None
    alt_dialogue: list[str] | None = None
    set_switch: str | None = None
    required_item: str | None = None
    consume_item: bool = False
    give_item: str | None = None          # 추가: 대화 후 아이템 지급
    hint_switch: str | None = None        # 추가: 힌트 페이지 조건 스위치
    hint_dialogue: list[str] | None = None  # 추가: 힌트 대사
    unlock_switch: str | None = None      # 추가: 보상 시 해제할 게이트 스위치
```

- [ ] **Step 4: _compile_npc 3페이지 구현**

`event_compiler.py`의 `_compile_npc` 메서드를 수정. 기존 1~2페이지 로직을 유지하면서, `hint_switch + hint_dialogue`가 있으면 3페이지 구성:

```python
    def _compile_npc(self, event: NpcEvent) -> dict:
        pages = []

        # ── Page 1: 기본 대화 (조건 없음) ──
        page1_cmds = _build_dialogue_commands(
            event.face_image, event.face_index, event.name, event.dialogue
        )
        if event.set_switch:
            sw_id = self.resolve_switch_id(event.set_switch)
            page1_cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})
        if event.give_item:
            try:
                item_id = self.resolve_item_id(event.give_item)
                page1_cmds.append({"code": 126, "indent": 0, "parameters": [item_id, 0, 0, 1]})
            except CompileError:
                logger.warning("NPC '%s' give_item '%s' 찾을 수 없음", event.name, event.give_item)
        page1_cmds.append({"code": 0, "indent": 0, "parameters": []})
        pages.append(
            _make_page(page1_cmds, _empty_conditions(), _trigger_code(event.trigger),
                       character_name=event.character_name, character_index=event.character_index)
        )

        # ── Page 2: 힌트 (hint_switch ON) ──
        if event.hint_switch and event.hint_dialogue:
            hint_sw_id = self.resolve_switch_id(event.hint_switch)
            page2_cmds = _build_dialogue_commands(
                event.face_image, event.face_index, event.name, event.hint_dialogue
            )
            page2_cmds.append({"code": 0, "indent": 0, "parameters": []})
            pages.append(
                _make_page(page2_cmds, _make_switch_condition(hint_sw_id), _trigger_code(event.trigger),
                           character_name=event.character_name, character_index=event.character_index)
            )

        # ── Page 3 (또는 Page 2): 보상/조건부 대화 (condition_switch ON) ──
        if event.condition_switch and event.alt_dialogue:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)
            page3_cmds = _build_dialogue_commands(
                event.face_image, event.face_index, event.name, event.alt_dialogue
            )
            # 보상 아이템 지급 (required_item 소비 또는 unlock_switch)
            if event.consume_item and event.required_item:
                try:
                    item_id = self.resolve_item_id(event.required_item)
                    page3_cmds.append({"code": 126, "indent": 0, "parameters": [item_id, 0, 1, 1]})
                except CompileError:
                    pass
            if event.unlock_switch:
                unlock_id = self.resolve_switch_id(event.unlock_switch)
                page3_cmds.append({"code": 121, "indent": 0, "parameters": [unlock_id, unlock_id, 0]})
            page3_cmds.append({"code": 0, "indent": 0, "parameters": []})

            # required_item 조건이면 itemValid, 아니면 switchValid
            if event.required_item and not event.hint_switch:
                # 2페이지 아이템 조건 (기존 호환)
                item_id = self.resolve_item_id(event.required_item)
                conditions = _make_item_condition(item_id)
            else:
                conditions = _make_switch_condition(cond_sw_id)

            pages.append(
                _make_page(page3_cmds, conditions, _trigger_code(event.trigger),
                           character_name=event.character_name, character_index=event.character_index)
            )

        return _make_event(event.name, event.x, event.y, pages)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_compiler.py -v`
Expected: 전체 PASS (기존 + 신규)

- [ ] **Step 6: 커밋**

```bash
git add agent/generation/compilers/dsl_models.py agent/generation/compilers/event_compiler.py agent/tests/generation/test_event_compiler.py
git commit -m "feat: NPC 3페이지 컴파일 (퀘스트부여/힌트/보상) — Phase 2"
```

---

## Phase 3: event_filler (LLM 대사 채우기)

### Task 4: event_filler 프롬프트 + 노드 구현

**Files:**
- Create: `agent/generation/prompts/event_filler_prompt.py`
- Create: `agent/generation/nodes/event_filler.py`
- Test: `agent/tests/generation/test_event_filler.py`

- [ ] **Step 1: 프롬프트 구현**

`agent/generation/prompts/event_filler_prompt.py`:

```python
"""event_filler 프롬프트 — 이벤트 뼈대의 대사를 채운다.

LLM은 구조(스위치, 좌표, 아이템)를 변경하지 않고 대사만 작성한다.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec

_SYSTEM = """\
당신은 RPG 대사 작가입니다.
이벤트 뼈대의 빈 대사(_FILL_)를 자연스러운 한국어 게임 대사로 채워주세요.

## 규칙
1. _FILL_ 부분만 대체하세요. 다른 필드(x, y, switch 등)는 절대 변경하지 마세요.
2. 각 대사는 1~2문장, 마침표/느낌표/물음표로 끝맺음하세요.
3. NPC 역할에 맞는 어투를 사용하세요:
   - 촌장/장로: 존대, 진지한 어투
   - 상인: 친근한 어투
   - 모험가: 격식 없는 어투
   - 경비병: 짧고 단호한 어투
4. 힌트 대사는 퀘스트 목표를 간접적으로 알려주세요 (직접적 스포일러 금지).
5. 보상 대사는 감사와 축하의 느낌으로 작성하세요.
6. 차단 대사는 "아직 ~하지 않았습니다" 형태로 짧게 작성하세요.

## 출력 형식
YAML만 출력하세요. 설명 불필요. 기존 뼈대 그대로 유지하면서 _FILL_ 부분만 교체:
"""


def build_event_filler_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    skeleton_yaml: str,
) -> list[BaseMessage]:
    human = f"""\
## 게임 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}

## 맵: {map_spec.name} ({map_spec.map_type})
분위기: {map_spec.atmosphere}

## 이벤트 뼈대 (아래 _FILL_ 부분만 채워주세요)
```yaml
{skeleton_yaml}
```

위 YAML에서 _FILL_ 부분만 자연스러운 대사로 교체하고, 나머지는 그대로 출력하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
```

- [ ] **Step 2: event_filler 노드 구현**

`agent/generation/nodes/event_filler.py`:

```python
"""event_filler — 이벤트 뼈대의 대사를 LLM으로 채운다.

event_scaffolder가 생성한 _FILL_ 플레이스홀더를 자연스러운 대사로 교체.
구조(스위치, 좌표)는 변경하지 않음.
"""

import logging
import re
from typing import Any, cast

import yaml
from pydantic import TypeAdapter, ValidationError

from agent.core.llm_client import invoke_llm
from agent.generation.compilers.dsl_models import DslEvent
from agent.generation.models import GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.prompts.event_filler_prompt import build_event_filler_prompt
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7
_FILL = "_FILL_"
_dsl_event_adapter: TypeAdapter = TypeAdapter(DslEvent)


async def event_filler(state: GenerationState) -> dict:
    """이벤트 대사 채우기 노드."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    skeletons: dict[int, list] = state.get("event_skeletons") or {}

    await publish_progress(
        gen_id,
        {"type": "progress", "phase": "event_fill", "progress": 72, "message": "이벤트 대사 작성 중..."},
    )

    event_dsl: dict[int, list] = {}
    for spec in map_specs:
        map_id = spec.map_id
        skeleton_list = skeletons.get(map_id, [])
        if not skeleton_list:
            event_dsl[map_id] = []
            continue

        filled = await _fill_single_map(spec, game_spec, skeleton_list)
        event_dsl[map_id] = filled

    logger.info("event_filler 완료: %d개 맵", len(event_dsl))

    await publish_progress(
        gen_id,
        {"type": "phase_complete", "phase": "event_fill", "summary": f"{len(event_dsl)}개 맵 대사 작성 완료"},
    )

    completed = list(state.get("completed_phases", []))
    completed.append("event_fill")
    return {"event_dsl": event_dsl, "completed_phases": completed}


async def _fill_single_map(
    map_spec: MapSpec,
    game_spec: GameSpec,
    skeletons: list,
) -> list:
    """맵 1개의 뼈대에 대사를 채운다."""
    # _FILL_이 없으면 그대로 반환
    skeleton_dicts = [e.model_dump() for e in skeletons]
    skeleton_yaml = yaml.dump({"events": skeleton_dicts}, allow_unicode=True, default_flow_style=False)

    if _FILL not in skeleton_yaml:
        return skeletons

    for attempt in range(2):
        try:
            prompt = build_event_filler_prompt(map_spec, game_spec, skeleton_yaml)
            raw = cast(str, await invoke_llm(prompt, temperature=_TEMPERATURE))
            filled = _parse_filled_yaml(raw, skeletons)
            if filled is not None:
                return filled
        except Exception as e:
            logger.warning("Map%d 대사 채우기 시도 %d 실패: %s", map_spec.map_id, attempt + 1, e)

    # 폴백: _FILL_을 기본 대사로 교체
    logger.warning("Map%d 대사 채우기 실패 → 기본 대사 사용", map_spec.map_id)
    return _apply_default_dialogue(skeletons)


def _parse_filled_yaml(raw: str, originals: list) -> list | None:
    """LLM 응답을 파싱하고, 구조가 원본과 일치하는지 확인."""
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = yaml.safe_load(text)
        if not isinstance(data, dict) or "events" not in data:
            return None

        events = data["events"] or []
        if len(events) != len(originals):
            logger.warning("LLM 출력 이벤트 수 불일치: %d vs %d", len(events), len(originals))

        # 구조 보존: 원본의 type, x, y, switch 등은 원본 값 유지, dialogue만 교체
        result = []
        for i, orig in enumerate(originals):
            if i < len(events):
                filled_event = events[i]
                merged = _merge_dialogue_only(orig.model_dump(), filled_event)
                result.append(_dsl_event_adapter.validate_python(merged))
            else:
                result.append(orig)

        return result
    except (yaml.YAMLError, ValidationError) as e:
        logger.warning("filled YAML 파싱 실패: %s", e)
        return None


def _merge_dialogue_only(original: dict, filled: dict) -> dict:
    """filled에서 대사 필드만 가져오고 나머지는 original 유지."""
    dialogue_fields = {"dialogue", "alt_dialogue", "hint_dialogue", "blocked_dialogue", "lines"}
    merged = dict(original)
    for field in dialogue_fields:
        if field in filled and filled[field] and filled[field] != [_FILL] and filled[field] != _FILL:
            merged[field] = filled[field]
    # shop dialogue (str)
    if "dialogue" in filled and isinstance(filled.get("dialogue"), str) and filled["dialogue"] != _FILL:
        merged["dialogue"] = filled["dialogue"]
    return merged


def _apply_default_dialogue(skeletons: list) -> list:
    """_FILL_을 기본 대사로 교체."""
    defaults = {
        "npc": {"dialogue": ["..."], "alt_dialogue": ["감사합니다."], "hint_dialogue": ["잘 찾아보세요."]},
        "shop": {"dialogue": "어서오세요."},
        "transfer": {"blocked_dialogue": "아직 갈 수 없습니다."},
    }
    result = []
    for skeleton in skeletons:
        d = skeleton.model_dump()
        event_type = d.get("type", "npc")
        type_defaults = defaults.get(event_type, {})
        for field, default_val in type_defaults.items():
            if field in d and (d[field] == [_FILL] or d[field] == _FILL):
                d[field] = default_val
        result.append(_dsl_event_adapter.validate_python(d))
    return result
```

- [ ] **Step 3: 테스트 추가**

`agent/tests/generation/test_event_filler.py`:

```python
"""event_filler 유닛 테스트 — LLM mock으로 대사 채우기 검증."""

import pytest

from agent.generation.compilers.dsl_models import NpcEvent, TransferEvent
from agent.generation.nodes.event_filler import _apply_default_dialogue, _merge_dialogue_only

_FILL = "_FILL_"


def test_merge_dialogue_only_preserves_structure() -> None:
    original = {"type": "npc", "name": "촌장", "x": 5, "y": 5, "dialogue": [_FILL], "set_switch": "quest"}
    filled = {"type": "npc", "name": "다른이름", "x": 99, "y": 99, "dialogue": ["안녕하세요!"], "set_switch": "변경됨"}
    result = _merge_dialogue_only(original, filled)
    assert result["dialogue"] == ["안녕하세요!"]  # 대사만 교체
    assert result["name"] == "촌장"  # 이름 유지
    assert result["x"] == 5  # 좌표 유지
    assert result["set_switch"] == "quest"  # 스위치 유지


def test_apply_default_dialogue_replaces_fill() -> None:
    skeletons = [
        NpcEvent(type="npc", name="NPC", x=1, y=1, dialogue=[_FILL]),
        TransferEvent(
            type="transfer", name="이동", x=2, y=2,
            to_map="마을", to_x=5, to_y=5,
            blocked_dialogue=_FILL, condition_switch="gate",
        ),
    ]
    result = _apply_default_dialogue(skeletons)
    assert result[0].dialogue == ["..."]
    assert result[1].blocked_dialogue == "아직 갈 수 없습니다."
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest agent/tests/generation/test_event_filler.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add agent/generation/prompts/event_filler_prompt.py agent/generation/nodes/event_filler.py agent/tests/generation/test_event_filler.py
git commit -m "feat: event_filler 구현 — LLM으로 대사만 채우기 (Phase 3)"
```

---

## Phase 4: CommonEvent 엔딩

### Task 5: integrator에 CommonEvent 엔딩 생성 추가

**Files:**
- Modify: `agent/generation/nodes/integrator.py`
- Test: `agent/tests/generation/test_integrator.py`

- [ ] **Step 1: 테스트 추가**

`test_integrator.py`에 추가:

```python
def test_build_ending_common_event() -> None:
    """보스 처치 스위치 → CommonEvent autorun 엔딩 생성."""
    from agent.generation.nodes.integrator import build_ending_common_event

    result = build_ending_common_event(
        switch_id=3,
        ending_lines=["마왕을 물리쳤다!", "세계에 평화가 찾아왔다."],
    )
    assert result["id"] == 1
    assert result["trigger"] == 2  # autorun
    assert result["switchId"] == 3
    codes = [cmd["code"] for cmd in result["list"]]
    assert 101 in codes  # ShowText
    assert 354 in codes  # Return to Title
```

- [ ] **Step 2: 구현**

`integrator.py`에 함수 추가:

```python
def build_ending_common_event(switch_id: int, ending_lines: list[str]) -> dict:
    """보스 처치 시 자동 실행되는 엔딩 CommonEvent."""
    cmds: list[dict] = []
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})  # Wait 1초

    for line in ending_lines:
        cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]})
        cmds.append({"code": 401, "indent": 0, "parameters": [line]})

    cmds.append({"code": 230, "indent": 0, "parameters": [60]})
    cmds.append({"code": 221, "indent": 0, "parameters": []})  # Fadeout
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})
    cmds.append({"code": 354, "indent": 0, "parameters": []})  # Return to Title
    cmds.append({"code": 0, "indent": 0, "parameters": []})

    return {
        "id": 1,
        "name": "엔딩",
        "switchId": switch_id,
        "trigger": 2,  # 2 = Autorun (CommonEvent trigger: 0=None, 1=Autorun... RPG MZ는 2=Autorun)
        "list": cmds,
    }
```

integrator 함수 내에서 `final_project["CommonEvents.json"]` 설정 부분 수정:

```python
    # 기존: final_project["CommonEvents.json"] = _load_base_game_file("CommonEvents.json")
    # 변경: 엔딩 CommonEvent 추가
    boss_defeated_sw = switch_table.switches.get(
        normalize_switch_name(f"{game_spec.title}_defeated"),
        None,
    )
    # 보스 이름으로 스위치 찾기 (fallback)
    if boss_defeated_sw is None:
        for sw_name, sw_id in switch_table.switches.items():
            if "defeated" in sw_name and any(
                e.tier == "boss" and normalize_switch_name(e.name) in sw_name
                for e in game_spec.enemies
            ):
                boss_defeated_sw = sw_id
                break

    base_common_events = _load_base_game_file("CommonEvents.json")
    if boss_defeated_sw is not None:
        ending_ce = build_ending_common_event(
            switch_id=boss_defeated_sw,
            ending_lines=["축하합니다!", f"{game_spec.title} — 엔딩", "세계에 평화가 찾아왔습니다."],
        )
        # CommonEvents.json은 [null, ce1, ce2, ...] 형식
        if isinstance(base_common_events, list) and len(base_common_events) > 1:
            base_common_events[1] = ending_ce
        else:
            base_common_events = [None, ending_ce]

    final_project["CommonEvents.json"] = base_common_events
```

- [ ] **Step 3: 테스트 통과 + 전체 확인**

Run: `uv run pytest agent/tests/generation/test_integrator.py -v && uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add agent/generation/nodes/integrator.py agent/tests/generation/test_integrator.py
git commit -m "feat: CommonEvent 엔딩 — 보스 처치 시 자동 엔딩 시퀀스 (Phase 4)"
```

---

## Phase 5: 워크플로우 연결

### Task 6: 스프라이트 매핑 분리

**Files:**
- Create: `agent/generation/sprite_mapping.py`
- Modify: `agent/generation/nodes/event_scaffolder.py` (스프라이트 적용)

- [ ] **Step 1: event_planner.py에서 스프라이트 코드 추출**

`agent/generation/sprite_mapping.py` 생성 — `event_planner.py:401-613`의 `_SF_KEYWORDS`, `_build_troop_sprite_map`, `_BATTLER_TO_MAP_SPRITE`, `_fix_battle_sprites` 함수를 그대로 복사.

임포트만 조정:
```python
"""스프라이트 매핑 — 적/NPC 이미지 자동 결정.

event_planner.py에서 분리됨. 기존 로직 100% 유지.
"""
# ... (event_planner.py:401-613 전체 복사)
```

- [ ] **Step 2: event_scaffolder에서 스프라이트 적용 호출**

```python
from agent.generation.sprite_mapping import _build_troop_sprite_map, _fix_battle_sprites
```

scaffolder 노드에서 이벤트 생성 후 `_fix_battle_sprites` 호출.

- [ ] **Step 3: 커밋**

```bash
git add agent/generation/sprite_mapping.py agent/generation/nodes/event_scaffolder.py
git commit -m "refactor: 스프라이트 매핑 코드를 sprite_mapping.py로 분리 (Phase 5)"
```

### Task 7: workflow.py 교체

**Files:**
- Modify: `agent/generation/workflow.py`
- Modify: `agent/generation/state.py`

- [ ] **Step 1: state.py에 새 필드 추가**

```python
    # ── F 노드 (story_planner) 출력 ───────────────────────
    story_script: dict[int, MapStoryScript] | None
    quest_plan: Any  # GameQuestPlan

    # ── G 노드 (event_scaffolder) 출력 ────────────────────
    event_skeletons: dict[int, list]
```

- [ ] **Step 2: workflow.py 수정**

```python
# 변경: event_planner → event_scaffolder + event_filler
from agent.generation.nodes.event_scaffolder import event_scaffolder
from agent.generation.nodes.event_filler import event_filler

# 노드 등록에서:
# 제거: builder.add_node("event_planner", event_planner)
# 추가:
builder.add_node("event_scaffolder", event_scaffolder)
builder.add_node("event_filler", event_filler)

# 엣지에서:
# 제거: builder.add_edge("story_planner", "event_planner")
#        builder.add_edge("event_planner", "event_compiler")
# 추가:
builder.add_edge("story_planner", "event_scaffolder")
builder.add_edge("event_scaffolder", "event_filler")
builder.add_edge("event_filler", "event_compiler")

# retry_events도 변경:
# "retry_events": "event_scaffolder"  (event_planner 대신)
```

- [ ] **Step 3: 전체 테스트**

Run: `uv run pytest agent/tests/generation/ -v --tb=short -m "not integration"`
Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add agent/generation/workflow.py agent/generation/state.py
git commit -m "feat: 워크플로우 교체 — story_planner → scaffolder → filler → compiler (Phase 5)"
```

### Task 8: story_planner를 QuestScript 출력으로 변경

**Files:**
- Modify: `agent/generation/prompts/story_planner_prompt.py`
- Modify: `agent/generation/nodes/story_planner.py`
- Modify: `agent/generation/models.py` (StoryScriptOutput 대체)

- [ ] **Step 1: story_planner 프롬프트를 QuestScript 유도로 변경**

`story_planner_prompt.py`의 `_SYSTEM`을 교체:

```python
_SYSTEM = """\
당신은 RPG 퀘스트 기획자입니다.
게임 정보를 받아 퀘스트 계획을 JSON으로 작성합니다.

## 규칙
1. 퀘스트는 맵 순서대로 진행되는 메인 퀘스트 1개를 작성합니다.
2. 각 퀘스트 단계(step)는 type이 "talk", "battle", "collect" 중 하나입니다.
3. NPC 이름은 주인공 이름과 절대 겹치지 않아야 합니다.
4. boss_name은 tier가 "boss"인 적의 이름입니다.
5. 맵 순서는 제공된 maps 목록 순서를 따릅니다.
6. 각 맵의 gate_switch는 이전 맵의 완료 스위치입니다 (첫 맵은 null).
"""
```

- [ ] **Step 2: story_planner 노드를 GameQuestPlan 출력으로 변경**

```python
result = cast(
    GameQuestPlan,
    await invoke_llm(messages, structured_output=GameQuestPlan, temperature=_TEMPERATURE),
)
```

폴백은 `_fallback_quest_plan` (event_scaffolder에 이미 구현됨) 사용.

- [ ] **Step 3: 테스트 + 커밋**

```bash
git add agent/generation/prompts/story_planner_prompt.py agent/generation/nodes/story_planner.py
git commit -m "feat: story_planner를 QuestScript 출력으로 변경 (Phase 5)"
```

---

## Phase 6: 실증 + 검증

### Task 9: 전체 통합 테스트

- [ ] **Step 1: 전체 테스트 스위트**

Run: `uv run pytest app/backend/tests agent/tests -v --tb=short -m "not integration"`
Expected: 전체 PASS

- [ ] **Step 2: ruff 린트**

Run: `uv run ruff check agent/generation/`
Expected: All checks passed

- [ ] **Step 3: 실제 LLM 호출 테스트 (story_planner)**

story_planner가 GameQuestPlan을 제대로 생성하는지 3회 실행하여 확인:
```bash
uv run python3 -c "
# story_planner LLM 호출 테스트
# ... (별도 스크립트로 실행)
"
```

- [ ] **Step 4: 실제 LLM 호출 테스트 (event_filler)**

event_filler가 _FILL_을 자연스러운 대사로 교체하는지 3회 실행하여 확인.

- [ ] **Step 5: 생성된 게임 데이터 검증**

```python
# 검증 스크립트: 스위치 체인, NPC 3페이지, 맵 게이트, CommonEvent 엔딩
```

- [ ] **Step 6: 문서 업데이트 + 커밋**

```bash
git add docs/The_world/event_system_redesign.md
git commit -m "docs: 이벤트 시스템 재설계 완료 문서 업데이트"
```
