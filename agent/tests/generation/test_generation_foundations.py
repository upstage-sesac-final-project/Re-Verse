import asyncio

import pytest

from agent.generation.models import CharacterSpec, EnemySpec, GameMapInfo, GameSpec
from agent.generation.nodes.asset_planner import _build_id_table, asset_planner
from agent.generation.nodes.game_designer import _validate_map_connections, game_designer
from agent.generation.progress import (
    _generation_queues,
    publish_progress,
    subscribe_generation_events,
)
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable


def make_game_spec(
    *,
    class_names: list[str] | None = None,
    maps: list[GameMapInfo] | None = None,
) -> GameSpec:
    classes = class_names or ["전사", "마법사"]
    game_maps = maps or [
        GameMapInfo(
            name="시작 마을",
            type="town",
            description="모험의 시작점",
            connects_to=["서쪽 들판"],
        ),
        GameMapInfo(
            name="서쪽 들판",
            type="field",
            description="마을 밖 들판",
            connects_to=["시작 마을", "어둠의 던전"],
        ),
        GameMapInfo(
            name="어둠의 던전",
            type="dungeon",
            description="보스에게 가는 길",
            connects_to=["서쪽 들판", "마왕의 성"],
        ),
        GameMapInfo(
            name="마왕의 성",
            type="boss",
            description="최종 결전",
            connects_to=["어둠의 던전"],
        ),
    ]

    characters = [
        CharacterSpec(
            name=f"캐릭터{i + 1}",
            class_name=class_name,
            role="주인공" if i == 0 else "서포터",
            personality=f"성격{i + 1}",
        )
        for i, class_name in enumerate(classes)
    ]

    return GameSpec(
        title="테스트 게임",
        theme="중세 판타지",
        playtime_minutes=7,
        story={"synopsis": "짧은 모험", "acts": ["출발", "탐험", "결전"]},
        characters=characters,
        enemies=[
            EnemySpec(name="슬라임", tier="weak", location="서쪽 들판"),
            EnemySpec(name="오크 대장", tier="elite", location="어둠의 던전"),
            EnemySpec(name="마왕", tier="boss", location="마왕의 성"),
        ],
        maps=game_maps,
        key_items=["성문 열쇠"],
        skills=["파이어볼", "힐"],
    )


def test_switch_table_allocate_switch_is_immutable_and_reuses_existing_id() -> None:
    table = SwitchTable()

    new_table, first_id = table.allocate_switch("boss_defeated")
    reused_table, reused_id = new_table.allocate_switch("boss_defeated")

    assert first_id == 1
    assert table.switches == {}
    assert new_table.switches == {"boss_defeated": 1}
    assert reused_table is new_table
    assert reused_id == 1


def test_switch_table_exports_rpgmaker_arrays_with_null_index_zero() -> None:
    table, _ = SwitchTable().allocate_switch("boss_defeated")
    table, _ = table.allocate_switch("game_cleared")
    table, _ = table.allocate_variable("slime_kills")

    assert table.to_rpgmaker_switches() == [None, "boss_defeated", "game_cleared"]
    assert table.to_rpgmaker_variables() == [None, "slime_kills"]


def test_id_table_get_id_returns_value_or_none() -> None:
    table = IdTable(actors={"해럴드": 1}, maps={"시작 마을": 2})

    assert table.get_id("actors", "해럴드") == 1
    assert table.get_id("maps", "없는 맵") is None
    assert table.get_id("unknown_category", "해럴드") is None


def test_asset_planner_returns_expected_phase_outputs() -> None:
    result = asset_planner({"game_spec": make_game_spec(), "completed_phases": ["spec"]})

    assert result["completed_phases"] == ["spec", "planning"]
    assert result["generation_order"][0] == "classes"
    assert result["generation_order"][1] == "actors"
    assert result["id_table"].actors == {"캐릭터1": 1, "캐릭터2": 2}
    assert result["id_table"].maps["마왕의 성"] == 4
    assert result["switch_table"].switches["오크 대장_defeated"] >= 1
    assert result["switch_table"].switches["마왕_defeated"] >= 1
    assert result["switch_table"].switches["어둠의 던전_cleared"] >= 1
    assert result["switch_table"].switches["game_cleared"] >= 1


@pytest.mark.asyncio
async def test_publish_and_subscribe_generation_events_round_trip() -> None:
    generation_id = "generation-roundtrip"
    received: list[dict] = []

    async def consume() -> None:
        async for event in subscribe_generation_events(generation_id):
            received.append(event)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)

    await publish_progress(generation_id, {"type": "progress", "progress": 10})
    await publish_progress(generation_id, {"type": "completed", "progress": 100})
    await task

    assert received == [
        {"type": "progress", "progress": 10},
        {"type": "completed", "progress": 100},
    ]
    assert generation_id not in _generation_queues


@pytest.mark.asyncio
async def test_game_designer_uses_structured_output_and_publishes_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_spec = make_game_spec()
    recorded_events: list[dict] = []

    async def fake_publish_progress(generation_id: str, event: dict) -> None:
        assert generation_id == "gen-001"
        recorded_events.append(event)

    async def fake_invoke_llm(messages, structured_output=None):
        assert structured_output is GameSpec
        assert len(messages) == 2
        return expected_spec

    monkeypatch.setattr(
        "agent.generation.nodes.game_designer.publish_progress", fake_publish_progress
    )
    monkeypatch.setattr("agent.generation.nodes.game_designer.invoke_llm", fake_invoke_llm)

    result = await game_designer(
        {
            "generation_id": "gen-001",
            "user_input": "중세 판타지 게임 만들어줘",
            "completed_phases": [],
        }
    )

    assert result["game_spec"] == expected_spec
    assert result["completed_phases"] == ["spec"]
    assert recorded_events[0]["type"] == "progress"
    assert recorded_events[0]["phase"] == "spec"
    assert recorded_events[-1]["type"] == "phase_complete"
    assert recorded_events[-1]["phase"] == "spec"


def test_build_id_table_assigns_dense_class_ids_for_unique_class_names() -> None:
    spec = make_game_spec(class_names=["전사", "전사", "마법사"])

    id_table = _build_id_table(spec)

    assert id_table.classes == {"전사": 1, "마법사": 2}


def test_validate_map_connections_warns_on_one_way_edges(caplog: pytest.LogCaptureFixture) -> None:
    spec = make_game_spec(
        maps=[
            GameMapInfo(
                name="시작 마을",
                type="town",
                description="마을",
                connects_to=["어둠의 던전"],
            ),
            GameMapInfo(
                name="어둠의 던전",
                type="dungeon",
                description="던전",
                connects_to=[],
            ),
        ]
    )

    with caplog.at_level("WARNING"):
        _validate_map_connections(spec)

    assert any(
        "시작 마을" in record.message and "어둠의 던전" in record.message
        for record in caplog.records
    )
