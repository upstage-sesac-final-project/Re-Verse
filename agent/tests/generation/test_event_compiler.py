"""EventCompiler 유닛 테스트 — 6개 DSL 타입 컴파일 검증."""

import pytest

from agent.generation.compilers.dsl_models import (
    ChestEvent,
    EndingEvent,
    NpcEvent,
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


def test_compile_shop_with_condition_switch(compiler: EventCompiler) -> None:
    """ShopEvent: condition_switch 있으면 2페이지 — page1 비활성, page2 상점."""
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


def test_compile_npc_with_required_item(compiler: EventCompiler) -> None:
    """NpcEvent: required_item 있으면 page2는 itemValid 조건."""
    event = NpcEvent(
        type="npc",
        name="장로",
        x=5,
        y=5,
        dialogue=["열쇠를 가져오세요."],
        required_item="회복 포션",
        alt_dialogue=["열쇠를 가져왔군요!"],
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    assert result["pages"][1]["conditions"]["itemValid"] is True
    assert result["pages"][1]["conditions"]["itemId"] == 1  # 회복 포션 = id 1


def test_compile_npc_with_required_item_and_consume(compiler: EventCompiler) -> None:
    """NpcEvent: consume_item=True면 page2에서 아이템 소비 (code 126)."""
    event = NpcEvent(
        type="npc",
        name="장로",
        x=5,
        y=5,
        dialogue=["열쇠를 가져오세요."],
        required_item="회복 포션",
        alt_dialogue=["감사합니다!"],
        consume_item=True,
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    codes_p2 = [cmd["code"] for cmd in result["pages"][1]["list"]]
    assert 126 in codes_p2  # Change Items (consume)


def test_compile_npc_condition_switch_takes_priority_over_required_item(
    compiler: EventCompiler,
) -> None:
    """condition_switch와 required_item 둘 다 있으면 condition_switch 우선."""
    event = NpcEvent(
        type="npc",
        name="장로",
        x=5,
        y=5,
        dialogue=["기본 대사"],
        condition_switch="quest_done",
        required_item="회복 포션",
        alt_dialogue=["조건 후 대사"],
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # switch condition should be used, not item
    assert result["pages"][1]["conditions"]["switch1Valid"] is True
    assert result["pages"][1]["conditions"]["itemValid"] is False


def test_compile_chest_with_condition_switch(compiler: EventCompiler) -> None:
    """ChestEvent: condition_switch 있으면 2페이지 — page1 숨김, page2 상자."""
    event = ChestEvent(
        type="chest",
        name="숨겨진_보물",
        x=4,
        y=6,
        item="회복 포션",
        item_type="item",
        condition_switch="quest_done",
        chest_switch="hidden_chest_01",
        one_time=True,
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 2
    # page1: 숨겨진 상태
    assert result["pages"][0]["conditions"]["switch1Valid"] is False
    assert result["pages"][0]["image"]["characterName"] == ""
    # page2: switch ON일 때 상자 출현
    assert result["pages"][1]["conditions"]["switch1Valid"] is True
    codes_p2 = [cmd["code"] for cmd in result["pages"][1]["list"]]
    assert 126 in codes_p2  # Change Items


def test_compile_chest_without_condition_switch_unchanged(compiler: EventCompiler) -> None:
    """ChestEvent: condition_switch 없으면 기존과 동일."""
    event = ChestEvent(
        type="chest",
        name="보물상자",
        x=4,
        y=6,
        item="회복 포션",
        item_type="item",
        chest_switch="chest_01",
        one_time=True,
    )
    result = compiler.compile(event)
    assert len(result["pages"]) == 1


def test_validate_switch_refs_warns_on_orphan_condition(caplog) -> None:
    """condition_switch가 어떤 이벤트의 set_switch에도 없으면 경고 로그."""
    import logging

    from agent.generation.nodes.event_planner import _validate_switch_refs

    events = [
        NpcEvent(
            type="npc",
            name="NPC",
            x=1,
            y=1,
            dialogue=["hi"],
            condition_switch="never_set_switch",
        ),
        NpcEvent(
            type="npc",
            name="NPC2",
            x=2,
            y=2,
            dialogue=["hello"],
            set_switch="some_other_switch",
        ),
    ]
    with caplog.at_level(logging.WARNING):
        _validate_switch_refs(events, set())

    assert any("never_set_switch" in r.message for r in caplog.records)


def test_switch_name_normalization_spaces_to_underscores() -> None:
    """공백이 포함된 스위치 이름과 밑줄 버전이 같은 ID를 받는지 확인."""
    from agent.generation.registry.switch_table import normalize_switch_name

    assert normalize_switch_name("고대 유적_cleared") == "고대_유적_cleared"
    assert normalize_switch_name("던전 입구_cleared") == "던전_입구_cleared"
    assert normalize_switch_name("act_1_started") == "act_1_started"  # 변경 없음


def test_switch_table_allocates_same_id_for_normalized_names() -> None:
    """공백 vs 밑줄 이름이 같은 스위치 ID를 할당받는지 확인."""
    table = SwitchTable()
    table, id1 = table.allocate_switch("고대 유적_cleared")
    table, id2 = table.allocate_switch("고대_유적_cleared")
    assert id1 == id2  # 정규화 후 같은 이름이므로 같은 ID


def test_prefix_chest_switches_adds_map_name() -> None:
    """chest_switch에 맵 접두어가 없으면 자동 추가."""
    from agent.generation.nodes.event_planner import _prefix_chest_switches

    events = [
        ChestEvent(
            type="chest",
            name="보물상자",
            x=4,
            y=6,
            item="회복 포션",
            item_type="item",
            chest_switch="chest_01",
            one_time=True,
        ),
        ChestEvent(
            type="chest",
            name="보물상자2",
            x=5,
            y=6,
            item="회복 포션",
            item_type="item",
            chest_switch="고대_유적_chest_02",
            one_time=True,
        ),
    ]
    result = _prefix_chest_switches(events, "고대 유적")
    assert result[0].chest_switch == "고대_유적_chest_01"  # 접두어 추가됨
    assert result[1].chest_switch == "고대_유적_chest_02"  # 이미 접두어 있어서 변경 없음
