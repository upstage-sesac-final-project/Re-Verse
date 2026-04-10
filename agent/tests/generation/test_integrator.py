"""integrator.py 유닛 테스트 — Map*.json / System.json 조립 검증."""

from agent.generation.models import (
    EnemySpec,
    ExitSpec,
    GameMapInfo,
    GameSpec,
    LandmarkSpec,
    MapSpec,
)
from agent.generation.nodes.integrator import build_map_json, build_system_json_phase2
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable


def _make_game_spec() -> GameSpec:
    return GameSpec(
        title="테스트 RPG",
        theme="판타지",
        story={"synopsis": "세계를 구하라"},
        characters=[],
        enemies=[EnemySpec(name="슬라임", tier="weak", location="던전")],
        maps=[
            GameMapInfo(name="출발 마을", type="town", description="시작점", connects_to=["던전"]),
        ],
    )


def _make_map_spec(map_type: str = "town") -> MapSpec:
    return MapSpec(
        map_id=1,
        name="출발 마을",
        map_type=map_type,
        width=17,
        height=13,
        tileset_id=1,
        bgm="Town1",
        atmosphere="평화로운",
        landmarks=[LandmarkSpec(name="여관", landmark_type="building", position_hint="north")],
        exits=[ExitSpec(direction="south", to_map_id=2, label="던전")],
        spawn_point=(8, 6),
    )


def test_build_map_json_events_index_zero_null() -> None:
    """Map*.json events[0]은 항상 null이어야 함 (RPG Maker MZ 규칙)."""
    spec = _make_map_spec("town")
    tile_data = [0] * (17 * 13 * 6)
    events = [{"id": 1, "x": 5, "y": 3, "pages": []}]
    result = build_map_json(spec, tile_data, events)

    assert result["events"][0] is None
    assert result["events"][1] == events[0]


def test_build_map_json_dungeon_has_encounter_list() -> None:
    """전투는 이벤트 기반으로만 진행하므로 encounterList는 항상 빈 배열."""
    spec = _make_map_spec("dungeon")
    tile_data = [0] * (17 * 13 * 6)
    battle_event = {
        "pages": [
            {
                "list": [
                    {"code": 301, "parameters": [0, 3, True, True]},
                    {"code": 0, "parameters": []},
                ]
            }
        ]
    }
    result = build_map_json(spec, tile_data, [battle_event])

    # _build_encounter_list는 의도적으로 빈 배열 반환 (랜덤 인카운터 미사용)
    assert result["encounterList"] == []


def test_build_map_json_dungeon_no_battle_empty_encounter_list() -> None:
    """dungeon 타입이라도 battle 이벤트가 없으면 encounterList는 빈 배열이어야 함."""
    spec = _make_map_spec("dungeon")
    tile_data = [0] * (17 * 13 * 6)
    result = build_map_json(spec, tile_data, [])

    assert result["encounterList"] == []


def test_build_map_json_town_empty_encounter_list() -> None:
    """town 타입 맵은 encounterList가 빈 배열이어야 함."""
    spec = _make_map_spec("town")
    tile_data = [0] * (17 * 13 * 6)
    result = build_map_json(spec, tile_data, [])

    assert result["encounterList"] == []


def test_build_system_json_start_map_id() -> None:
    """startMapId가 id_table의 맵 ID 중 하나여야 함."""
    game_spec = _make_game_spec()
    id_table = IdTable(
        actors={"용사": 1},
        maps={"출발 마을": 1, "던전": 2},
    )
    switch_table = SwitchTable()
    result = build_system_json_phase2(game_spec, id_table, switch_table)

    assert result["startMapId"] in {1, 2}
    assert result["gameTitle"] == "테스트 RPG"


def test_build_system_json_party_members() -> None:
    """partyMembers는 id_table.actors의 ID들로 구성되어야 함."""
    game_spec = _make_game_spec()
    id_table = IdTable(
        actors={"용사": 1, "마법사": 2},
        maps={"출발 마을": 1},
    )
    switch_table = SwitchTable()
    result = build_system_json_phase2(game_spec, id_table, switch_table)

    assert sorted(result["partyMembers"]) == [1, 2]


def test_build_ending_common_event() -> None:
    """보스 처치 스위치 → CommonEvent autorun 엔딩."""
    from agent.generation.nodes.integrator import build_ending_common_event

    result = build_ending_common_event(
        switch_id=3,
        ending_lines=["마왕을 물리쳤다!", "세계에 평화가 찾아왔다."],
    )
    assert result["id"] == 1
    assert result["trigger"] == 1  # Autorun
    assert result["switchId"] == 3
    codes = [cmd["code"] for cmd in result["list"]]
    assert 101 in codes  # ShowText
    assert 354 in codes  # Return to Title
    assert codes[-1] == 0  # End
