"""event_filler 유닛 테스트 — LLM mock 없이 유틸리티 함수 검증."""

from agent.generation.compilers.dsl_models import NpcEvent, ShopEvent, ShopItem, TransferEvent
from agent.generation.nodes.event_filler import _apply_default_dialogue, _merge_dialogue_only

_FILL = "_FILL_"


def test_merge_dialogue_only_preserves_structure() -> None:
    """대사만 교체, 나머지 필드 유지."""
    original = {
        "type": "npc",
        "name": "촌장",
        "x": 5,
        "y": 5,
        "dialogue": [_FILL],
        "set_switch": "quest",
        "trigger": "action_button",
    }
    filled = {
        "type": "npc",
        "name": "다른이름",
        "x": 99,
        "y": 99,
        "dialogue": ["안녕하세요!"],
        "set_switch": "변경됨",
    }
    result = _merge_dialogue_only(original, filled)
    assert result["dialogue"] == ["안녕하세요!"]
    assert result["name"] == "촌장"
    assert result["x"] == 5
    assert result["set_switch"] == "quest"


def test_merge_dialogue_only_skips_fill_values() -> None:
    """_FILL_ 값은 교체하지 않음."""
    original = {"type": "npc", "dialogue": [_FILL], "alt_dialogue": [_FILL]}
    filled = {"type": "npc", "dialogue": ["대사"], "alt_dialogue": [_FILL]}
    result = _merge_dialogue_only(original, filled)
    assert result["dialogue"] == ["대사"]
    assert result["alt_dialogue"] == [_FILL]  # 여전히 _FILL_


def test_merge_blocked_dialogue_str() -> None:
    """blocked_dialogue (str 타입) 교체."""
    original = {"type": "transfer", "blocked_dialogue": _FILL}
    filled = {"type": "transfer", "blocked_dialogue": "아직 준비가 안 됐어요."}
    result = _merge_dialogue_only(original, filled)
    assert result["blocked_dialogue"] == "아직 준비가 안 됐어요."


def test_apply_default_dialogue_npc() -> None:
    """NPC _FILL_ → 기본 대사."""
    skeletons = [
        NpcEvent(type="npc", name="NPC", x=1, y=1, dialogue=[_FILL]),
    ]
    result = _apply_default_dialogue(skeletons)
    assert result[0].dialogue == ["안녕하세요, 여행자님. 이곳에 오신 걸 환영합니다."]


def test_apply_default_dialogue_transfer() -> None:
    """Transfer blocked_dialogue _FILL_ → 기본 대사."""
    skeletons = [
        TransferEvent(
            type="transfer",
            name="이동",
            x=2,
            y=2,
            to_map="마을",
            to_x=5,
            to_y=5,
            blocked_dialogue=_FILL,
            condition_switch="gate",
        ),
    ]
    result = _apply_default_dialogue(skeletons)
    assert result[0].blocked_dialogue == "아직 이쪽으로는 갈 수 없습니다."


def test_apply_default_dialogue_shop() -> None:
    """Shop dialogue _FILL_ → 기본 대사."""
    skeletons = [
        ShopEvent(
            type="shop",
            name="상인",
            x=3,
            y=3,
            dialogue=_FILL,
            items=[ShopItem(item="포션", item_type="item")],
        ),
    ]
    result = _apply_default_dialogue(skeletons)
    assert result[0].dialogue == "어서오세요! 좋은 물건이 많습니다."
