"""플레이어 시작 지점 주변 이벤트 배치 금지 로직 테스트."""

from unittest.mock import patch

import pytest

from agent.generation.compilers.dsl_models import NpcEvent
from agent.generation.models import MapConnectionInfo, MapSpec
from agent.generation.nodes.event_compiler_node import event_compiler_node
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState


@pytest.mark.asyncio
async def test_spawn_point_exclusion_zone() -> None:
    """spawn_point 주변 3x3 구역에 이벤트가 배치되지 않고 밀려나는지 확인."""

    # 1. 목업 데이터 준비
    # 맵 크기 10x10, 시작 지점 (5, 5)
    spec = MapSpec(
        map_id=1,
        name="Test Map",
        map_type="town",
        width=10,
        height=10,
        tileset_id=1,
        bgm="Field1",
        atmosphere="normal",
        landmarks=[],
        exits=[],
        spawn_point=(5, 5),
    )

    # 시작 지점 바로 위 (5, 5)에 NPC 배치 시도
    npc = NpcEvent(type="npc", name="Test NPC", x=5, y=5, dialogue=["Hello"])

    id_table = IdTable(actors={}, items={}, weapons={}, armors={}, enemies={}, troops={}, maps={})
    switch_table = SwitchTable()

    state: GenerationState = {
        "generation_id": "test_gen",
        "map_specs": [spec],
        "event_dsl": {1: [npc]},
        "id_table": id_table,
        "switch_table": switch_table,
        "map_tiles": {1: [0] * (10 * 10 * 6)},  # 빈 타일 맵
        "completed_phases": [],
    }

    # reachable_coords 목업: 모든 좌표 도달 가능
    all_coords = [(x, y) for x in range(10) for y in range(10)]

    with (
        patch("agent.generation.mapgen.tile_checker.get_reachable_coords", return_value=all_coords),
        patch("agent.generation.nodes.integrator.load_base_tilesets", return_value={}),
        patch("agent.generation.progress.publish_progress"),
    ):
        # 2. 노드 실행
        result = await event_compiler_node(state)

        # 3. 결과 검증
        compiled_events = result["compiled_events"][1]
        assert len(compiled_events) == 1

        event = compiled_events[0]
        ex, ey = event["x"], event["y"]

        # 시작 지점 (5, 5) 및 주변 8칸[(4,4)~(6,6)]에 있으면 안 됨
        forbidden = set()
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                forbidden.add((5 + dx, 5 + dy))

        assert (ex, ey) not in forbidden, f"Event placed in forbidden zone at ({ex}, {ey})"


@pytest.mark.asyncio
async def test_multiple_entry_points_exclusion_zone() -> None:
    """여러 진입점이 있을 때 모든 입구 주변 3x3 구역이 보호되는지 확인."""

    spec = MapSpec(
        map_id=1,
        name="Multi Entry Map",
        map_type="town",
        width=20,
        height=20,
        tileset_id=1,
        bgm="F",
        atmosphere="n",
        landmarks=[],
        exits=[],
        spawn_point=(10, 10),
    )

    # 두 개의 입구: (5, 5)와 (15, 15)
    conn_info = MapConnectionInfo(
        map_id=1,
        exit_tiles=[],
        entry_tiles=[{"x": 5, "y": 5, "from_map_id": 2}, {"x": 15, "y": 15, "from_map_id": 3}],
    )

    # 두 입구 각각에 NPC 배치 시도
    npc1 = NpcEvent(type="npc", name="N1", x=5, y=5, dialogue=["D1"])
    npc2 = NpcEvent(type="npc", name="N2", x=15, y=15, dialogue=["D2"])

    state: GenerationState = {
        "generation_id": "test_gen",
        "map_specs": [spec],
        "event_dsl": {1: [npc1, npc2]},
        "id_table": IdTable(
            actors={}, items={}, weapons={}, armors={}, enemies={}, troops={}, maps={}
        ),
        "switch_table": SwitchTable(),
        "map_tiles": {1: [0] * (20 * 20 * 6)},
        "connection_info": {1: conn_info},
        "completed_phases": [],
    }

    all_coords = [(x, y) for x in range(20) for y in range(20)]

    with (
        patch("agent.generation.mapgen.tile_checker.get_reachable_coords", return_value=all_coords),
        patch("agent.generation.nodes.integrator.load_base_tilesets", return_value={}),
        patch("agent.generation.progress.publish_progress"),
    ):
        result = await event_compiler_node(state)
        events = result["compiled_events"][1]

        forbidden = set()
        for ex, ey in [(5, 5), (15, 15)]:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    forbidden.add((ex + dx, ey + dy))

        for ev in events:
            pos = (ev["x"], ev["y"])
            assert pos not in forbidden, f"Event {ev['name']} placed in forbidden zone at {pos}"


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_spawn_point_exclusion_zone())
    asyncio.run(test_multiple_entry_points_exclusion_zone())
