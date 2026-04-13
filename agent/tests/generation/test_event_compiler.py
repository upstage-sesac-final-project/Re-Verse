"""EventCompiler 유닛 테스트 — 6개 DSL 타입 컴파일 검증."""

import pytest

from agent.generation.compilers.dsl_models import (
    ChestEvent,
    EndingEvent,
    GateEvent,
    NpcEvent,
    QuestChestEvent,
    ShopEvent,
    ShopItem,
    TransferEvent,
)
from agent.generation.compilers.event_compiler import CompileError, EventCompiler
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable


@pytest.fixture
def compiler() -> EventCompiler:
    id_table = IdTable(
        actors={"용사": 1},
        items={"회복 포션": 1, "마나 포션": 2},
        weapons={"강철 검": 1},
        armors={"가죽 갑옷": 1},
        enemies={"슬라임": 1},
        troops={"슬라임 × 2": 1, "드래곤 × 1": 2},
        maps={"출발 마을": 1, "어둠의 던전": 2, "보스의 성": 3},
    )
    switch_table = SwitchTable()
    return EventCompiler(id_table, switch_table)


def test_compile_npc_single_page(compiler: EventCompiler) -> None:
    """NPC 단일 대화 → code 101 + 401 포함, code 0 종결."""
    event = NpcEvent(type="npc", name="마을주민", x=5, y=3, dialogue=["안녕하세요!"])
    result = compiler.compile(event)

    assert result["x"] == 5
    assert result["y"] == 3
    assert len(result["pages"]) == 1
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 101 in codes
    assert 401 in codes
    assert codes[-1] == 0


def test_compile_npc_two_pages(compiler: EventCompiler) -> None:
    """NPC 2페이지 패턴: condition_switch + alt_dialogue → 2페이지."""
    event = NpcEvent(
        type="npc",
        name="여관주인",
        x=8,
        y=3,
        dialogue=["어서오세요!"],
        condition_switch="드래곤_defeated",
        alt_dialogue=["평화가 찾아왔어요!"],
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # 페이지 2는 switch 조건이 있어야 함
    assert result["pages"][1]["conditions"]["switch1Valid"] is True


def test_compile_transfer_uses_map_id(compiler: EventCompiler) -> None:
    """TransferEvent: to_map 이름 → 실제 map_id(code 201)로 변환."""
    event = TransferEvent(
        type="transfer", name="던전_입구", x=10, y=13, to_map="어둠의 던전", to_x=1, to_y=1
    )
    result = compiler.compile(event)
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 201 in codes
    transfer_cmd = next(cmd for cmd in result["pages"][0]["list"] if cmd["code"] == 201)
    assert transfer_cmd["parameters"][1] == 2  # "어둠의 던전" → id=2


def test_compile_chest_item_command(compiler: EventCompiler) -> None:
    """ChestEvent: item_type=item → code 126(Change Items)."""
    event = ChestEvent(
        type="chest",
        name="보물상자",
        x=4,
        y=6,
        item="회복 포션",
        item_type="item",
        amount=2,
        one_time=True,
        chest_switch="chest_01",
    )
    result = compiler.compile(event)
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 126 in codes  # Change Items
    assert 111 in codes  # If (switch condition)
    assert 121 in codes  # Control Switches (turn ON)


def test_compile_ending_auto_run_and_return_to_title(compiler: EventCompiler) -> None:
    """EndingEvent: Auto-Run(trigger=3) + code 354(Return to Title) 포함."""
    event = EndingEvent(
        type="ending",
        name="엔딩_이벤트",
        x=15,
        y=8,
        condition_switch="드래곤_defeated",
        lines=["드래곤을 쓰러뜨렸다!", "세계에 평화가 찾아왔다."],
        action="title",
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # 페이지 1: 대기 페이지(trigger=0), 페이지 2: switch ON 시 Auto-Run(trigger=3)
    assert result["pages"][0]["trigger"] == 0
    assert result["pages"][1]["trigger"] == 3
    codes = [cmd["code"] for cmd in result["pages"][1]["list"]]
    assert 354 in codes


def test_compile_shop_uses_code_302(compiler: EventCompiler) -> None:
    """ShopEvent: 첫 상품 code 302, 추가 상품 code 605."""
    event = ShopEvent(
        type="shop",
        name="무기상인",
        x=6,
        y=4,
        dialogue="어서오세요!",
        items=[
            ShopItem(item="회복 포션", item_type="item"),
            ShopItem(item="강철 검", item_type="weapon"),
        ],
    )
    result = compiler.compile(event)
    codes = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 302 in codes  # Open Shop
    assert 605 in codes  # Additional goods


def test_compile_transfer_unknown_map_raises(compiler: EventCompiler) -> None:
    """존재하지 않는 맵 이름 → CompileError."""
    event = TransferEvent(
        type="transfer", name="미지의 문", x=1, y=1, to_map="없는 맵", to_x=0, to_y=0
    )
    with pytest.raises(CompileError):
        compiler.compile(event)


def test_compile_gate_multi_page(compiler: EventCompiler) -> None:
    """GateEvent: 조건 스위치 수 + 1개 페이지, 마지막은 워프(player_touch)."""
    event = GateEvent(
        type="gate",
        name="던전 문지기",
        x=10,
        y=5,
        to_map="어둠의 던전",
        to_x=1,
        to_y=1,
        condition_switches=["열쇠A", "열쇠B"],
        stage_dialogues=["열쇠A가 필요합니다.", "열쇠B도 필요합니다."],
    )
    result = compiler.compile(event)
    # 2개 힌트 페이지 + 1개 워프 페이지 = 3페이지
    assert len(result["pages"]) == 3
    # 마지막 페이지는 player_touch(1) + 이동 커맨드(201)
    last_page = result["pages"][-1]
    assert last_page["trigger"] == 1
    codes = [cmd["code"] for cmd in last_page["list"]]
    assert 201 in codes


def test_compile_quest_chest_npc_type(compiler: EventCompiler) -> None:
    """QuestChestEvent(npc): 2페이지 — 힌트 대사 + 보물상자."""
    event = QuestChestEvent(
        type="quest_chest",
        name="퀘스트 상자",
        x=7,
        y=3,
        quest_type="npc",
        quest_switch="촌장_퀘스트",
        quest_dialogue=["먼저 촌장과 대화하세요."],
        item="회복 포션",
        item_type="item",
        amount=1,
        chest_switch="chest_quest_01",
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # 페이지 2는 quest_switch ON 조건
    assert result["pages"][1]["conditions"]["switch1Valid"] is True
    # 페이지 2에 아이템 획득 커맨드(126)
    codes_p2 = [cmd["code"] for cmd in result["pages"][1]["list"]]
    assert 126 in codes_p2


def test_compile_quest_chest_battle_type(compiler: EventCompiler) -> None:
    """QuestChestEvent(battle): 전투(301) + 승리 시 quest_switch ON."""
    event = QuestChestEvent(
        type="quest_chest",
        name="몬스터 상자",
        x=5,
        y=8,
        quest_type="battle",
        quest_switch="슬라임_처치",
        troop="슬라임 × 2",
        item="마나 포션",
        item_type="item",
        amount=1,
        chest_switch="chest_battle_01",
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # 페이지 1에 전투 커맨드(301)
    codes_p1 = [cmd["code"] for cmd in result["pages"][0]["list"]]
    assert 301 in codes_p1
    # 승리 분기(601) + 스위치 ON(121)
    assert 601 in codes_p1
    assert 121 in codes_p1
