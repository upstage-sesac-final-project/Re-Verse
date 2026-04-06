"""generation_validator.py 유닛 테스트 — 핵심 검증 함수 개별 테스트."""

from agent.generation.models import ExitSpec, MapSpec
from agent.generation.nodes.generation_validator import (
    _check_ending_reachable,
    _check_map_id_consistency,
    _check_null_at_index_0,
)
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable

# ── _check_null_at_index_0 ────────────────────────────────────────────────────


def test_check_null_at_index_0_passes_for_valid_data() -> None:
    """index-0이 null인 배열은 오류 없음."""
    project = {
        "Actors.json": [None, {"id": 1, "name": "용사"}],
        "Enemies.json": [None, {"id": 1, "name": "슬라임"}],
    }
    errors = _check_null_at_index_0(project)
    assert errors == []


def test_check_null_at_index_0_fails_if_non_null() -> None:
    """index-0이 null이 아니면 R_NULL 오류."""
    project = {
        "Actors.json": [{"id": 0, "name": "PLACEHOLDER"}, {"id": 1, "name": "용사"}],
    }
    errors = _check_null_at_index_0(project)
    assert any("R_NULL" in e for e in errors)


def test_check_null_at_index_0_skips_missing_file() -> None:
    """파일 자체가 없으면 skip (오류 없음)."""
    project = {}
    errors = _check_null_at_index_0(project)
    assert errors == []


# ── _check_map_id_consistency ─────────────────────────────────────────────────


def test_check_map_id_consistency_passes_when_matched() -> None:
    """MapInfos와 Map*.json이 일치하면 오류 없음."""
    project = {
        "MapInfos.json": {"1": {"id": 1, "name": "출발 마을"}},
        "Map001.json": {"displayName": "출발 마을"},
    }
    errors = _check_map_id_consistency(project)
    assert errors == []


def test_check_map_id_consistency_fails_when_missing_map_file() -> None:
    """MapInfos에 있는데 Map*.json 파일이 없으면 R18 오류."""
    project = {
        "MapInfos.json": {"1": {"id": 1}, "2": {"id": 2}},
        "Map001.json": {},
        # Map002.json 누락
    }
    errors = _check_map_id_consistency(project)
    assert any("R18" in e for e in errors)


def test_check_map_id_consistency_skips_when_no_map_files() -> None:
    """Map*.json이 없으면 에셋 생성 단계 → R18 skip."""
    project = {
        "MapInfos.json": {"1": {"id": 1}},
        "Actors.json": [None],
        # Map*.json 없음
    }
    errors = _check_map_id_consistency(project)
    assert errors == []


# ── _check_ending_reachable ───────────────────────────────────────────────────


def _make_boss_map_spec() -> MapSpec:
    return MapSpec(
        map_id=3,
        name="보스의 성",
        map_type="boss",
        width=17,
        height=13,
        tileset_id=2,
        bgm="Boss1",
        atmosphere="위험한",
        landmarks=[],
        exits=[ExitSpec(direction="west", to_map_id=2, label="던전")],
        spawn_point=(8, 12),
    )


def test_check_ending_reachable_no_boss_map() -> None:
    """보스 맵 없으면 R23 오류."""
    map_specs = []  # boss 타입 없음
    id_table = IdTable(maps={"출발 마을": 1})
    switch_table = SwitchTable()
    errors = _check_ending_reachable(map_specs, {}, id_table, switch_table)
    assert any("R23" in e for e in errors)


def test_check_ending_reachable_passes_with_ending_event() -> None:
    """보스 맵에 code 354 있고 _defeated 스위치 있으면 통과."""
    boss_spec = _make_boss_map_spec()
    id_table = IdTable(maps={"보스의 성": 3})
    switch_table, _ = SwitchTable().allocate_switch("드래곤_defeated")

    # code 354 포함 이벤트
    ending_event = {
        "x": 8,
        "y": 8,
        "pages": [
            {
                "list": [
                    {"code": 354, "indent": 0, "parameters": []},
                    {"code": 0, "indent": 0, "parameters": []},
                ]
            }
        ],
    }
    compiled_events = {3: [ending_event]}

    errors = _check_ending_reachable([boss_spec], compiled_events, id_table, switch_table)
    assert errors == []


def test_check_ending_reachable_fails_without_ending_code() -> None:
    """보스 맵에 353/354 없으면 R23 오류."""
    boss_spec = _make_boss_map_spec()
    id_table = IdTable(maps={"보스의 성": 3})
    switch_table, _ = SwitchTable().allocate_switch("드래곤_defeated")

    compiled_events = {3: []}  # 이벤트 없음

    errors = _check_ending_reachable([boss_spec], compiled_events, id_table, switch_table)
    assert any("R23" in e for e in errors)
