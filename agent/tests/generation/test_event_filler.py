"""event_filler 유닛 테스트 — 대사 추출/파싱/적용 검증."""

from agent.generation.compilers.dsl_models import NpcEvent, ShopEvent, ShopItem, TransferEvent
from agent.generation.nodes.event_filler import (
    _apply_default_dialogue,
    _apply_fills,
    _extract_fill_requests,
    _parse_fill_response,
    _remove_remaining_fills,
)

_FILL = "_FILL_"


def test_extract_fill_requests_finds_fill_fields() -> None:
    """_FILL_ 필드를 정확히 추출."""
    skeletons = [
        NpcEvent(
            type="npc",
            name="촌장",
            x=1,
            y=1,
            dialogue=[_FILL],
            condition_switch="boss_defeated",
            alt_dialogue=[_FILL],
        ),
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
    requests = _extract_fill_requests(skeletons)
    assert len(requests) == 3
    fields = [r[1] for r in requests]
    assert "dialogue" in fields
    assert "alt_dialogue" in fields
    assert "blocked_dialogue" in fields


def test_parse_fill_response() -> None:
    """번호.필드: 대사 형식 파싱."""
    raw = """1.dialogue: 용사여, 마왕을 물리쳐주시오!
1.alt_dialogue: 감사하오! 이 검을 받으시오.
2.blocked_dialogue: 아직 준비가 되지 않았습니다."""
    result = _parse_fill_response(raw)
    assert result[(0, "dialogue")] == "용사여, 마왕을 물리쳐주시오!"
    assert result[(0, "alt_dialogue")] == "감사하오! 이 검을 받으시오."
    assert result[(1, "blocked_dialogue")] == "아직 준비가 되지 않았습니다."


def test_parse_fill_response_ignores_fill() -> None:
    """_FILL_ 이 그대로 남은 응답은 무시."""
    raw = "1.dialogue: _FILL_\n2.dialogue: 실제 대사"
    result = _parse_fill_response(raw)
    assert (0, "dialogue") not in result
    assert result[(1, "dialogue")] == "실제 대사"


def test_apply_fills_preserves_structure() -> None:
    """대사만 교체, 나머지 필드 유지."""
    skeletons = [
        NpcEvent(
            type="npc",
            name="촌장",
            x=5,
            y=5,
            dialogue=[_FILL],
            set_switch="quest",
        ),
    ]
    filled_map = {(0, "dialogue"): "마왕을 처치해주시오!"}
    result = _apply_fills(skeletons, filled_map)
    assert result[0].dialogue == ["마왕을 처치해주시오!"]
    assert result[0].name == "촌장"
    assert result[0].x == 5
    assert result[0].set_switch == "quest"


def test_remove_remaining_fills() -> None:
    """남은 _FILL_을 기본 대사로 교체."""
    d = {
        "type": "npc",
        "name": "NPC",
        "x": 1,
        "y": 1,
        "dialogue": [_FILL],
        "alt_dialogue": [_FILL],
        "trigger": "action_button",
    }
    result = _remove_remaining_fills(d)
    assert result["dialogue"] != [_FILL]
    assert result["alt_dialogue"] != [_FILL]


def test_apply_default_dialogue_npc() -> None:
    """NPC _FILL_ → 기본 대사 (폴백)."""
    skeletons = [
        NpcEvent(type="npc", name="NPC", x=1, y=1, dialogue=[_FILL]),
    ]
    result = _apply_default_dialogue(skeletons)
    assert _FILL not in str(result[0].dialogue)


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
    assert result[0].dialogue != _FILL
    assert "어서오세요" in result[0].dialogue


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
    assert result[0].blocked_dialogue != _FILL
