# Full Generation 테스트 전략

> 각 노드별 단위 테스트, 통합 테스트, 수동 체크리스트

---

## 원칙

```
1. LLM이 없는 결정론적 코드는 단위 테스트로 100% 커버
2. LLM이 있는 코드는 mock으로 대체해서 입출력 계약만 검증
3. 실제 LLM 호출은 통합 테스트로만 (CI에서 제외, 로컬 실행)
4. TDD 원칙: 구현 전 테스트 작성 → 실패 확인 → 구현 → 통과 확인
```

---

## 테스트 파일 구조

```
agent/tests/generation/
├── fixtures/
│   ├── game_spec_medieval.json      # 고정 GameSpec (mock용)
│   ├── id_table_medieval.json       # 고정 IdTable
│   ├── switch_table_medieval.json
│   ├── actors_expected.json         # 예상 출력 (검증용)
│   └── map_spec_town.json
│
├── test_asset_planner.py            # B. 설계사 단위 테스트
├── test_asset_generator.py          # C. 에셋 생성 단위 테스트 (LLM mock)
├── test_town_generator.py           # E-1. 마을 타일 생성 단위 테스트
├── test_dungeon_generator.py        # E-2. 던전 BSP 단위 테스트
├── test_event_compiler.py           # G. 이벤트 컴파일러 단위 테스트
├── test_integrator.py               # H. 통합기 단위 테스트
├── test_generation_validator.py     # I. 검증기 단위 테스트
├── test_id_registry.py              # ID 충돌 방지 단위 테스트
├── test_switch_registry.py          # 스위치 번호 관리 단위 테스트
└── test_full_pipeline.py            # 통합 테스트 (LLM mock + 실제 LLM)
```

---

## B. 설계사 — 단위 테스트

```python
# test_asset_planner.py
import pytest
from agent.generation.nodes.asset_planner import asset_planner
from agent.generation.fixtures import load_game_spec


class TestAssetPlanner:
    def test_id_table_starts_at_1(self):
        """RPG Maker MZ 인덱스 0은 null이므로 ID는 1부터 시작해야 함."""
        spec = load_game_spec("medieval")
        state = {"game_spec": spec, "game_id": "test"}
        result = asset_planner(state)

        id_table = result["id_table"]
        assert min(id_table.actors.values()) == 1
        assert min(id_table.classes.values()) == 1
        assert min(id_table.enemies.values()) == 1

    def test_no_duplicate_ids_within_table(self):
        """같은 테이블 내에서 ID 중복 없음."""
        spec = load_game_spec("medieval")
        result = asset_planner({"game_spec": spec, "game_id": "test"})
        id_table = result["id_table"]

        actor_ids = list(id_table.actors.values())
        assert len(actor_ids) == len(set(actor_ids)), "actor ID 중복"

        enemy_ids = list(id_table.enemies.values())
        assert len(enemy_ids) == len(set(enemy_ids)), "enemy ID 중복"

    def test_class_ids_cover_all_characters(self):
        """모든 캐릭터의 class_name이 class ID 테이블에 있어야 함."""
        spec = load_game_spec("medieval")
        result = asset_planner({"game_spec": spec, "game_id": "test"})
        id_table = result["id_table"]

        for char in spec.characters:
            assert char.class_name in id_table.classes, \
                f"{char.name}의 class '{char.class_name}'가 id_table에 없음"

    def test_switch_table_no_duplicates(self):
        """스위치 번호 중복 없음."""
        spec = load_game_spec("medieval")
        result = asset_planner({"game_spec": spec, "game_id": "test"})
        switch_ids = list(result["switch_table"].switches.values())
        assert len(switch_ids) == len(set(switch_ids)), "스위치 번호 중복"

    def test_generation_order_dependency(self):
        """classes가 actors보다 앞에 와야 함 (의존성 순서)."""
        spec = load_game_spec("medieval")
        result = asset_planner({"game_spec": spec, "game_id": "test"})
        order = result["generation_order"]

        classes_idx = order.index("classes")
        actors_idx  = order.index("actors")
        assert classes_idx < actors_idx, "classes가 actors보다 먼저 생성돼야 함"
```

---

## G. 이벤트 컴파일러 — 단위 테스트

컴파일러는 LLM 없이 결정론적이므로 가장 중요한 단위 테스트 대상.

```python
# test_event_compiler.py
import pytest
from agent.generation.compilers.event_compiler import EventCompiler
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable


@pytest.fixture
def compiler():
    id_table = IdTable(
        maps={"어둠의 던전": 2},
        items={"회복 포션": 1},
        enemies={"슬라임": 1},
        troops={"슬라임_group": 1},
    )
    switch_table = SwitchTable(
        switches={"dungeon_entered": 1, "boss_defeated": 2, "chest_01": 3}
    )
    return EventCompiler(id_table, switch_table)


class TestNpcCompile:
    def test_basic_dialogue(self, compiler):
        dsl = {"type": "npc", "x": 5, "y": 3, "name": "여관주인",
               "dialogue": ["안녕!", "잘 가!"]}
        cmds = compiler.compile(dsl)

        codes = [c["code"] for c in cmds]
        assert 101 in codes, "대화 시작(101) 없음"
        assert codes.count(401) == 2, "대화 내용(401) 2개여야 함"
        assert codes[-1] == 0, "이벤트 종료(0) 없음"

    def test_dialogue_order(self, compiler):
        dsl = {"type": "npc", "x": 5, "y": 3, "name": "NPC",
               "dialogue": ["첫 번째", "두 번째"]}
        cmds = compiler.compile(dsl)

        dialogue_cmds = [c for c in cmds if c["code"] == 401]
        assert dialogue_cmds[0]["parameters"][0] == "첫 번째"
        assert dialogue_cmds[1]["parameters"][0] == "두 번째"

    def test_condition_wraps_dialogue(self, compiler):
        """조건부 대화는 111(If) ~ 412(EndIf) 사이에 위치해야 함."""
        dsl = {"type": "npc", "x": 5, "y": 3, "name": "NPC",
               "dialogue": ["보스 처치 전 대사"],
               "condition": {"switch": "boss_defeated", "value": False}}
        cmds = compiler.compile(dsl)

        codes = [c["code"] for c in cmds]
        assert codes[0] == 111, "첫 커맨드가 조건 분기(111)여야 함"
        assert 412 in codes, "End If(412) 없음"
        # 조건 파라미터: 스위치 2번이 OFF(0)인지 확인
        if_cmd = cmds[0]
        assert if_cmd["parameters"][1] == 2, "switch_id=2(boss_defeated)여야 함"
        assert if_cmd["parameters"][2] == 0, "0=OFF 조건이어야 함"

    def test_set_switch_after_dialogue(self, compiler):
        """set_switch가 있으면 대화 후 스위치 ON 커맨드(121) 추가."""
        dsl = {"type": "npc", "x": 5, "y": 3, "name": "NPC",
               "dialogue": ["대사"], "set_switch": "dungeon_entered"}
        cmds = compiler.compile(dsl)

        switch_cmds = [c for c in cmds if c["code"] == 121]
        assert len(switch_cmds) == 1
        assert switch_cmds[0]["parameters"][0] == 1   # switch_id=1
        assert switch_cmds[0]["parameters"][2] == 0   # 0=ON


class TestTransferCompile:
    def test_basic_transfer(self, compiler):
        dsl = {"type": "transfer", "x": 8, "y": 12, "name": "던전입구",
               "to_map": "어둠의 던전", "to_x": 8, "to_y": 1}
        cmds = compiler.compile(dsl)

        transfer_cmd = next(c for c in cmds if c["code"] == 201)
        assert transfer_cmd["parameters"][1] == 2, "맵 ID=2(어둠의 던전)여야 함"
        assert transfer_cmd["parameters"][2] == 8
        assert transfer_cmd["parameters"][3] == 1

    def test_unknown_map_raises(self, compiler):
        dsl = {"type": "transfer", "x": 1, "y": 1, "name": "오류",
               "to_map": "존재하지않는맵", "to_x": 0, "to_y": 0}
        with pytest.raises(ValueError, match="맵.*찾을 수 없음"):
            compiler.compile(dsl)

    def test_set_switch_in_transfer(self, compiler):
        dsl = {"type": "transfer", "x": 8, "y": 12, "name": "던전입구",
               "to_map": "어둠의 던전", "to_x": 8, "to_y": 1,
               "set_switch": "dungeon_entered"}
        cmds = compiler.compile(dsl)
        switch_cmds = [c for c in cmds if c["code"] == 121]
        assert len(switch_cmds) == 1


class TestChestCompile:
    def test_basic_chest(self, compiler):
        dsl = {"type": "chest", "x": 5, "y": 3, "name": "보물상자",
               "item": "회복 포션", "amount": 2,
               "one_time": True, "chest_switch": "chest_01"}
        cmds = compiler.compile(dsl)

        codes = [c["code"] for c in cmds]
        assert 111 in codes, "조건 분기(111) 없음 (한 번만 열림)"
        assert 126 in codes, "아이템 추가(126) 없음"
        assert 121 in codes, "스위치 ON(121) 없음"

    def test_item_amount(self, compiler):
        dsl = {"type": "chest", "x": 5, "y": 3, "name": "상자",
               "item": "회복 포션", "amount": 3,
               "one_time": False}
        cmds = compiler.compile(dsl)
        item_cmd = next(c for c in cmds if c["code"] == 126)
        assert item_cmd["parameters"][3] == 3, "수량=3이어야 함"

    def test_unknown_item_raises(self, compiler):
        dsl = {"type": "chest", "x": 1, "y": 1, "name": "상자",
               "item": "없는아이템", "amount": 1}
        with pytest.raises(ValueError, match="아이템.*찾을 수 없음"):
            compiler.compile(dsl)


class TestBattleCompile:
    def test_basic_battle(self, compiler):
        dsl = {"type": "battle", "x": 5, "y": 5, "name": "슬라임전투",
               "troop": "슬라임_group", "escape_allowed": True}
        cmds = compiler.compile(dsl)

        codes = [c["code"] for c in cmds]
        assert 301 in codes, "전투 처리(301) 없음"
        assert 601 in codes, "승리 분기(601) 없음"

    def test_one_time_battle(self, compiler):
        """한 번 이기면 다시 발생 안 함 (battle_switch)."""
        dsl = {"type": "battle", "x": 5, "y": 5, "name": "슬라임전투",
               "troop": "슬라임_group", "escape_allowed": True,
               "one_time": True, "battle_switch": "boss_defeated"}
        cmds = compiler.compile(dsl)
        # 맨 앞에 조건 분기가 있어야 함
        assert cmds[0]["code"] == 111

    def test_on_win_give_item(self, compiler):
        dsl = {"type": "battle", "x": 5, "y": 5, "name": "전투",
               "troop": "슬라임_group",
               "on_win": [{"give_item": {"item": "회복 포션", "amount": 1}}]}
        cmds = compiler.compile(dsl)
        # 601(승리) 이후에 126(아이템) 있어야 함
        codes = [c["code"] for c in cmds]
        win_idx  = codes.index(601)
        item_idx = next(i for i, c in enumerate(codes[win_idx:], win_idx) if c == 126)
        assert item_idx > win_idx
```

---

## E. 타일 생성기 — 단위 테스트

```python
# test_town_generator.py
from agent.generation.mapgen.town_generator import generate_town, is_walkable
from agent.generation.mapgen import get_exit_position
from tests.generation.fixtures import make_town_spec


class TestTownGenerator:
    def test_data_length(self):
        spec = make_town_spec(width=17, height=13)
        data = generate_town(spec, seed=42)
        assert len(data) == 17 * 13 * 6

    def test_exits_are_walkable(self):
        spec = make_town_spec()
        data = generate_town(spec, seed=42)
        for exit_spec in spec.exits:
            ex, ey = get_exit_position(exit_spec.direction, spec.width, spec.height)
            assert is_walkable(data, ex, ey, spec.width), \
                f"출구({ex},{ey})가 이동 불가 타일"

    def test_spawn_point_is_walkable(self):
        spec = make_town_spec()
        data = generate_town(spec, seed=42)
        sx, sy = spec.spawn_point
        assert is_walkable(data, sx, sy, spec.width)

    def test_different_seeds_different_layout(self):
        spec = make_town_spec()
        data1 = generate_town(spec, seed=1)
        data2 = generate_town(spec, seed=2)
        assert data1 != data2, "다른 시드는 다른 맵을 생성해야 함"

    def test_same_seed_same_layout(self):
        spec = make_town_spec()
        data1 = generate_town(spec, seed=42)
        data2 = generate_town(spec, seed=42)
        assert data1 == data2, "같은 시드는 같은 맵을 생성해야 함"


# test_dungeon_generator.py
from agent.generation.mapgen.dungeon_generator import generate_dungeon
from agent.generation.mapgen.bfs import bfs_all_reachable, find_all_walkable
from tests.generation.fixtures import make_dungeon_spec


class TestDungeonGenerator:
    def test_data_length(self):
        spec = make_dungeon_spec(width=20, height=15)
        data = generate_dungeon(spec, seed=42)
        assert len(data) == 20 * 15 * 6

    def test_no_isolated_rooms(self):
        """모든 바닥 타일이 계단에서 BFS로 도달 가능해야 함."""
        spec = make_dungeon_spec()
        data = generate_dungeon(spec, seed=42)

        stairs_pos = find_stairs_up(data, spec.width)
        reachable = bfs_all_reachable(data, *stairs_pos, spec.width)
        all_walkable = find_all_walkable(data, spec.width, spec.height)

        isolated = all_walkable - reachable
        assert not isolated, f"고립된 방 존재: {isolated}"

    def test_start_and_end_connected(self):
        spec = make_dungeon_spec()
        data = generate_dungeon(spec, seed=42)

        start = find_stairs_up(data, spec.width)
        end   = find_stairs_down(data, spec.width)
        assert bfs_path_exists(data, *start, *end, spec.width), \
            "시작 계단과 끝 계단 사이에 경로 없음"

    @pytest.mark.parametrize("seed", range(10))
    def test_multiple_seeds_always_connected(self, seed):
        """10가지 시드 모두 연결된 던전이어야 함 (알고리즘 안정성)."""
        spec = make_dungeon_spec()
        data = generate_dungeon(spec, seed=seed)
        stairs_pos = find_stairs_up(data, spec.width)
        reachable = bfs_all_reachable(data, *stairs_pos, spec.width)
        all_walkable = find_all_walkable(data, spec.width, spec.height)
        assert reachable == all_walkable
```

---

## I. 검증기 — 단위 테스트

```python
# test_generation_validator.py
from agent.generation.nodes.generation_validator import (
    check_id_references,
    check_map_connectivity,
    check_balance,
    check_ending_reachable,
)


class TestIdReferenceCheck:
    def test_valid_actors_pass(self):
        assets = {
            "Actors.json": [None, {"id": 1, "name": "해럴드", "classId": 1}],
            "Classes.json": [None, {"id": 1, "name": "전사"}],
        }
        errors = check_id_references(assets)
        assert not errors

    def test_invalid_class_id_detected(self):
        assets = {
            "Actors.json": [None, {"id": 1, "name": "해럴드", "classId": 99}],
            "Classes.json": [None, {"id": 1, "name": "전사"}],
        }
        errors = check_id_references(assets)
        assert any("classId=99" in e for e in errors)

    def test_null_entries_skipped(self):
        """null 엔트리는 검증 건너뜀 (인덱스 0)."""
        assets = {
            "Actors.json": [None, {"id": 1, "name": "A", "classId": 1}],
            "Classes.json": [None, {"id": 1, "name": "전사"}],
        }
        errors = check_id_references(assets)
        assert not errors


class TestMapConnectivity:
    def test_all_maps_connected(self):
        """시작 맵에서 모든 맵이 도달 가능한 경우."""
        maps = {
            1: {"events": [_make_transfer_event(from_map=1, to_map=2)]},
            2: {"events": [_make_transfer_event(from_map=2, to_map=3)]},
            3: {"events": []},
        }
        system = {"startMapId": 1}
        errors = check_map_connectivity(maps, system)
        assert not errors

    def test_isolated_map_detected(self):
        maps = {
            1: {"events": []},
            2: {"events": []},   # 맵 2로 가는 이벤트 없음
        }
        system = {"startMapId": 1}
        errors = check_map_connectivity(maps, system)
        assert any("Map002" in e for e in errors), "고립된 맵 감지 안 됨"


class TestBalanceCheck:
    def test_too_strong_weak_enemy(self):
        assets = {
            "Actors.json": [None, {"params": [150] + [0] * 791}],  # HP=150
            "Enemies.json": [None, {
                "name": "슬라임",
                "params": [60, 0, 30, 0, 0, 0, 0, 0],  # ATK=30 (HP의 20%)
                "meta": {"tier": "weak"},
            }],
        }
        warnings = check_balance(assets)
        assert any("ATK" in w and "슬라임" in w for w in warnings)

    def test_balanced_enemy_passes(self):
        assets = {
            "Actors.json": [None, {"params": [150] + [0] * 791}],
            "Enemies.json": [None, {
                "name": "슬라임",
                "params": [60, 0, 10, 0, 0, 0, 0, 0],  # ATK=10 (HP의 6.7%)
                "meta": {"tier": "weak"},
            }],
        }
        warnings = check_balance(assets)
        assert not [w for w in warnings if "슬라임" in w]
```

---

## 전체 파이프라인 통합 테스트

```python
# test_full_pipeline.py
import pytest
import json
from unittest.mock import AsyncMock, patch
from agent.generation.workflow import run_generation_workflow


def load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text())


@pytest.fixture
def medieval_spec():
    return load_fixture("game_spec_medieval.json")


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_phase2_without_maps(self, medieval_spec):
        """Phase 2: 에셋만 생성 (맵 없음)."""
        with patch("agent.generation.nodes.game_designer.invoke_llm",
                   AsyncMock(return_value=json.dumps(medieval_spec))):
            with patch("agent.generation.nodes.asset_generator.invoke_llm",
                       new_callable=_mock_asset_generator):
                state = await run_generation_workflow(
                    user_input="중세 판타지 게임",
                    game_id="test_game",
                    phase_limit="assets",  # Phase 2까지만
                )

        assert "Actors.json"  in state["generated_assets"]
        assert "Skills.json"  in state["generated_assets"]
        assert "Enemies.json" in state["generated_assets"]
        assert state["validation_passed"] is True

    @pytest.mark.asyncio
    async def test_actors_have_valid_class_ids(self, medieval_spec):
        """생성된 actors의 classId가 모두 존재해야 함."""
        with _mock_full_generation(medieval_spec):
            state = await run_generation_workflow(
                user_input="중세 판타지 게임",
                game_id="test_game",
                phase_limit="assets",
            )

        assets = state["generated_assets"]
        class_ids = {a["id"] for a in assets["Classes.json"] if a}
        for actor in assets["Actors.json"]:
            if actor:
                assert actor["classId"] in class_ids, \
                    f"Actor '{actor['name']}' classId={actor['classId']} 없음"

    @pytest.mark.asyncio
    async def test_phase4_produces_playable_game(self, medieval_spec):
        """Phase 4: 맵 + 이벤트까지 생성."""
        with _mock_full_generation(medieval_spec):
            state = await run_generation_workflow(
                user_input="중세 판타지 게임",
                game_id="test_game",
            )

        assert state["validation_passed"] is True
        assert len(state["final_project"]) >= 8  # Map001, Map002, ..., System.json 등
        # 맵 이동 이벤트 존재 확인
        map1 = state["final_project"]["Map001.json"]
        transfer_events = [
            e for e in map1.get("events", [])
            if e and any(cmd.get("code") == 201 for page in e.get("pages", [])
                         for cmd in page.get("list", []))
        ]
        assert transfer_events, "Map001에 맵 이동 이벤트 없음"


# ── 실제 LLM 통합 테스트 (로컬 실행 전용) ──────────────────────────────────

@pytest.mark.integration
class TestFullGenerationIntegration:
    @pytest.mark.asyncio
    async def test_medieval_fantasy_end_to_end(self):
        """실제 LLM으로 전체 생성 파이프라인 실행."""
        state = await run_generation_workflow(
            user_input="중세 판타지 게임 만들어줘, 기사 주인공",
            game_id="integration_test",
        )
        print(f"\n제목: {state['game_spec']['title']}")
        print(f"에셋: {list(state['final_project'].keys())}")
        assert state["validation_passed"] is True
        assert "Actors.json" in state["final_project"]
        assert "Map001.json" in state["final_project"]
```

---

## CI/CD 설정

```yaml
# .github/workflows/ci.yml 추가 항목

jobs:
  generation-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --all-extras --dev
      - run: |
          uv run pytest agent/tests/generation/ \
            -v --tb=short \
            -m "not integration" \
            --cov=agent/generation \
            --cov-report=term-missing
```

```
# 단위 테스트만 (CI에서 자동 실행):
uv run pytest agent/tests/generation/ -m "not integration"

# 실제 LLM 통합 테스트 (로컬에서만):
uv run pytest agent/tests/generation/ -m integration -s -v
```

---

## 수동 검증 체크리스트

### Phase 2 완료 시 (에셋 생성)

```
RPG Maker MZ에서 직접 확인:
  □ Actors.json — 캐릭터 이름, HP, MP, 직업 확인
  □ Skills.json — 스킬 이름, MP 소비, 범위 확인
  □ Enemies.json — 적 이름, HP, ATK 확인
  □ System.json — 시작 파티 actor_id, 게임 제목 확인
  □ 에디터에서 "새 프로젝트" 데이터 교체 후 오류 없음
```

### Phase 3 완료 시 (맵 생성)

```
RPG Maker MZ 에디터에서 확인:
  □ Map001.json — 맵 에디터에서 열 수 있음
  □ 타일 배열 길이 = width × height × 6 (자동 검증)
  □ 플레이 시작 → 맵이 보임 (검은 화면 아님)
  □ 이동 가능/불가 타일 육안 확인 (이동 테스트)
  □ 맵 외곽이 벽으로 막혀 있음
```

### Phase 4 완료 시 (이벤트 포함)

```
실제 플레이 테스트:
  □ 시작 → 마을 맵에서 출발
  □ NPC와 대화 → 올바른 텍스트 출력
  □ 마을 출구 → 던전 맵으로 이동
  □ 던전 적 접촉 → 전투 시작
  □ 전투 승리 → 경험치/아이템 획득
  □ 던전 보물 상자 → 아이템 획득
  □ 이미 연 상자 → 반응 없음 (스위치 동작 확인)
  □ 보스 격파 → 엔딩 이벤트 실행
  □ 총 플레이 시간 5~10분 이내
```

---

## 테스트 커버리지 목표

| 모듈 | 목표 커버리지 | 비고 |
|------|------------|------|
| `asset_planner.py` | 100% | LLM 없음, 완전 결정론적 |
| `event_compiler.py` | 100% | LLM 없음, 완전 결정론적 |
| `town_generator.py` | 90%+ | LLM 없음, 랜덤성 있음 |
| `dungeon_generator.py` | 90%+ | LLM 없음, 랜덤성 있음 |
| `integrator.py` | 85%+ | 조립 로직 |
| `generation_validator.py` | 95%+ | 검증 로직 |
| `asset_generator.py` | 70%+ | LLM mock으로 커버 |
| `event_planner.py` | 60%+ | LLM mock으로 커버 |

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- 리스크 분석: `docs/The_world/risks_and_mitigations.md`
- DSL 명세: `docs/The_world/dsl_specification.md`
- 맵 생성 알고리즘: `docs/The_world/map_generation.md`
- 에셋 생성 상세: `docs/The_world/asset_generation.md`
