"""handlers/events.py — Task 7: 5 base case 이벤트 구현.

5 base case:
1. NPC 대사 (npc_talk)
2. 상점 (shop)
3. 장소 이동 (teleport)
4. 스위치 트리거 (switch_trigger)
5. 전투 시작 (battle)

CRUD 대상: CommonEvents.json / Troops.json / MapNNN.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.editor.handlers.events import (
    build_battle_commands,
    build_commands_for_template,
    build_npc_talk_commands,
    build_shop_commands,
    build_switch_trigger_commands,
    build_teleport_commands,
    execute_events_step,
    is_event_target,
)

# ── template 빌더 단위 ───────────────────────────────────────────────────


class TestTemplateBuilders:
    def test_npc_talk_basic(self):
        out = build_npc_talk_commands("안녕하세요")
        # 101 (프레임) + 401 (텍스트) + 0 (종결)
        codes = [c["code"] for c in out]
        assert codes == [101, 401, 0]
        assert out[1]["parameters"] == ["안녕하세요"]

    def test_npc_talk_multiline(self):
        out = build_npc_talk_commands("안녕하세요\n반갑습니다\n또 봐요")
        codes = [c["code"] for c in out]
        # 101 + 401 3번 + 0
        assert codes == [101, 401, 401, 401, 0]

    def test_shop_single_item(self):
        out = build_shop_commands([{"kind": 0, "id": 1, "price": 100}])
        codes = [c["code"] for c in out]
        assert codes == [302, 0]

    def test_shop_multiple_items(self):
        out = build_shop_commands(
            [
                {"kind": 0, "id": 1, "price": 100},
                {"kind": 1, "id": 2, "price": 200},
                {"kind": 2, "id": 3, "price": 300},
            ]
        )
        codes = [c["code"] for c in out]
        assert codes == [302, 605, 605, 0]

    def test_teleport(self):
        out = build_teleport_commands(map_id=3, x=5, y=10, direction=2, fade=0)
        codes = [c["code"] for c in out]
        assert codes == [201, 0]
        assert out[0]["parameters"][:4] == [0, 3, 5, 10]

    def test_switch_trigger(self):
        out = build_switch_trigger_commands(switch_id=5, value=0)
        codes = [c["code"] for c in out]
        assert codes == [121, 0]
        assert out[0]["parameters"] == [5, 5, 0]

    def test_battle(self):
        out = build_battle_commands(troop_id=7, can_escape=True, can_lose=False)
        codes = [c["code"] for c in out]
        assert codes == [301, 0]
        assert out[0]["parameters"][:2] == [0, 7]

    def test_template_dispatch(self):
        out = build_commands_for_template("npc_talk", {"text": "hi"})
        assert out[0]["code"] == 101

    def test_unknown_template_raises(self):
        with pytest.raises(ValueError):
            build_commands_for_template("unknown", {})


# ── dispatch 라우팅 ──────────────────────────────────────────────────────


class TestIsEventTarget:
    def test_common_events(self):
        assert is_event_target("CommonEvents.json", "create_common_event")

    def test_troops(self):
        assert is_event_target("Troops.json", "create_troop")

    def test_map_event_action(self):
        assert is_event_target("Map001.json", "create_event")
        assert is_event_target("Map042.json", "add_event_command")

    def test_map_non_event_action_excluded(self):
        # Map 파일이지만 이벤트 액션이 아니면 map handler 로 가야 함
        assert not is_event_target("Map001.json", "draw_tile")

    def test_other_files_excluded(self):
        assert not is_event_target("Actors.json", "create")


# ── CommonEvents CRUD ────────────────────────────────────────────────────


@pytest.fixture
def tmp_data(tmp_path: Path) -> Path:
    return tmp_path


class TestCommonEventsCrud:
    def test_create_with_template(self, tmp_data: Path):
        (tmp_data / "CommonEvents.json").write_text("[null]", encoding="utf-8")
        result = execute_events_step(
            tmp_data,
            "create_common_event",
            "CommonEvents.json",
            {
                "name": "상점테스트",
                "trigger": 0,
                "template": "shop",
                "config": {"items": [{"kind": 0, "id": 1, "price": 100}]},
            },
        )
        assert result["success"] is True
        assert result["entity_id"] == 1

        saved = json.loads((tmp_data / "CommonEvents.json").read_text(encoding="utf-8"))
        assert saved[1]["name"] == "상점테스트"
        codes = [c["code"] for c in saved[1]["list"]]
        assert codes == [302, 0]

    def test_update(self, tmp_data: Path):
        (tmp_data / "CommonEvents.json").write_text(
            json.dumps([None, {"id": 1, "name": "원본", "list": [], "switchId": 1, "trigger": 0}]),
            encoding="utf-8",
        )
        result = execute_events_step(
            tmp_data,
            "update_common_event",
            "CommonEvents.json",
            {"id": 1, "updates": {"name": "수정됨", "trigger": 1}},
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "CommonEvents.json").read_text(encoding="utf-8"))
        assert saved[1]["name"] == "수정됨"
        assert saved[1]["trigger"] == 1

    def test_delete(self, tmp_data: Path):
        (tmp_data / "CommonEvents.json").write_text(
            json.dumps([None, {"id": 1, "name": "X", "list": [], "switchId": 1, "trigger": 0}]),
            encoding="utf-8",
        )
        result = execute_events_step(
            tmp_data, "delete_common_event", "CommonEvents.json", {"id": 1}
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "CommonEvents.json").read_text(encoding="utf-8"))
        assert saved[1] is None


# ── MapNNN events ────────────────────────────────────────────────────────


class TestMapEventsCrud:
    def _init_map(self, tmp_data: Path, map_id: int) -> None:
        (tmp_data / f"Map{map_id:03d}.json").write_text(
            json.dumps(
                {
                    "events": [None],
                    "data": [],
                    "width": 10,
                    "height": 10,
                }
            ),
            encoding="utf-8",
        )

    def test_create_event_from_template_npc_talk(self, tmp_data: Path):
        self._init_map(tmp_data, 3)
        result = execute_events_step(
            tmp_data,
            "create_event_from_template",
            "Map003.json",
            {
                "template": "npc_talk",
                "config": {"text": "이 마을에 오신 것을 환영합니다"},
                "name": "마을 입구 NPC",
                "x": 5,
                "y": 6,
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map003.json").read_text(encoding="utf-8"))
        ev = saved["events"][1]
        assert ev["name"] == "마을 입구 NPC"
        assert ev["x"] == 5 and ev["y"] == 6
        codes = [c["code"] for c in ev["pages"][0]["list"]]
        assert codes == [101, 401, 0]

    def test_create_event_from_template_teleport(self, tmp_data: Path):
        self._init_map(tmp_data, 1)
        result = execute_events_step(
            tmp_data,
            "create_event_from_template",
            "Map001.json",
            {
                "template": "teleport",
                "config": {"map_id": 2, "x": 0, "y": 0},
                "name": "2층으로",
                "x": 3,
                "y": 4,
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map001.json").read_text(encoding="utf-8"))
        codes = [c["code"] for c in saved["events"][1]["pages"][0]["list"]]
        assert codes == [201, 0]

    def test_create_event_from_template_battle(self, tmp_data: Path):
        self._init_map(tmp_data, 5)
        result = execute_events_step(
            tmp_data,
            "create_event_from_template",
            "Map005.json",
            {
                "template": "battle",
                "config": {"troop_id": 3, "can_escape": True},
                "x": 1,
                "y": 1,
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map005.json").read_text(encoding="utf-8"))
        codes = [c["code"] for c in saved["events"][1]["pages"][0]["list"]]
        assert codes == [301, 0]

    def test_create_event_from_template_switch(self, tmp_data: Path):
        self._init_map(tmp_data, 7)
        result = execute_events_step(
            tmp_data,
            "create_event_from_template",
            "Map007.json",
            {
                "template": "switch_trigger",
                "config": {"switch_id": 2, "value": 0},
                "x": 2,
                "y": 2,
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map007.json").read_text(encoding="utf-8"))
        codes = [c["code"] for c in saved["events"][1]["pages"][0]["list"]]
        assert codes == [121, 0]

    def test_create_event_from_template_shop(self, tmp_data: Path):
        self._init_map(tmp_data, 9)
        result = execute_events_step(
            tmp_data,
            "create_event_from_template",
            "Map009.json",
            {
                "template": "shop",
                "config": {
                    "items": [
                        {"kind": 0, "id": 1, "price": 100},
                        {"kind": 1, "id": 2, "price": 200},
                    ]
                },
                "x": 0,
                "y": 0,
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map009.json").read_text(encoding="utf-8"))
        codes = [c["code"] for c in saved["events"][1]["pages"][0]["list"]]
        assert codes == [302, 605, 0]

    def test_update_map_event(self, tmp_data: Path):
        (tmp_data / "Map010.json").write_text(
            json.dumps(
                {
                    "events": [
                        None,
                        {
                            "id": 1,
                            "name": "원본",
                            "note": "",
                            "pages": [{"list": []}],
                            "x": 0,
                            "y": 0,
                        },
                    ],
                    "data": [],
                }
            ),
            encoding="utf-8",
        )
        result = execute_events_step(
            tmp_data,
            "update_map_event",
            "Map010.json",
            {"id": 1, "updates": {"name": "수정됨", "x": 5}},
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map010.json").read_text(encoding="utf-8"))
        assert saved["events"][1]["name"] == "수정됨"
        assert saved["events"][1]["x"] == 5

    def test_add_event_command_appends_before_terminator(self, tmp_data: Path):
        (tmp_data / "Map020.json").write_text(
            json.dumps(
                {
                    "events": [
                        None,
                        {
                            "id": 1,
                            "name": "X",
                            "note": "",
                            "pages": [{"list": [{"code": 0, "indent": 0, "parameters": []}]}],
                            "x": 0,
                            "y": 0,
                        },
                    ],
                    "data": [],
                }
            ),
            encoding="utf-8",
        )
        result = execute_events_step(
            tmp_data,
            "add_event_command",
            "Map020.json",
            {
                "event_id": 1,
                "page_index": 0,
                "template": "npc_talk",
                "config": {"text": "나중에 추가"},
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Map020.json").read_text(encoding="utf-8"))
        plist = saved["events"][1]["pages"][0]["list"]
        codes = [c["code"] for c in plist]
        # 끝 terminator 유지 + npc_talk 삽입
        assert codes[-1] == 0
        assert 101 in codes and 401 in codes


# ── Troops CRUD ─────────────────────────────────────────────────────────


class TestTroopsCrud:
    def test_create_troop(self, tmp_data: Path):
        (tmp_data / "Troops.json").write_text("[null]", encoding="utf-8")
        result = execute_events_step(
            tmp_data,
            "create_troop",
            "Troops.json",
            {
                "name": "고블린 3인조",
                "members": [
                    {"enemyId": 1, "x": 100, "y": 200, "hidden": False},
                    {"enemyId": 1, "x": 200, "y": 200, "hidden": False},
                    {"enemyId": 1, "x": 300, "y": 200, "hidden": False},
                ],
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Troops.json").read_text(encoding="utf-8"))
        assert saved[1]["name"] == "고블린 3인조"
        assert len(saved[1]["members"]) == 3

    def test_add_troop_event_command(self, tmp_data: Path):
        (tmp_data / "Troops.json").write_text(
            json.dumps(
                [
                    None,
                    {
                        "id": 1,
                        "name": "T",
                        "members": [],
                        "pages": [
                            {
                                "conditions": {},
                                "list": [{"code": 0, "indent": 0, "parameters": []}],
                                "span": 0,
                            }
                        ],
                    },
                ]
            ),
            encoding="utf-8",
        )
        result = execute_events_step(
            tmp_data,
            "add_troop_event_command",
            "Troops.json",
            {
                "troop_id": 1,
                "page_index": 0,
                "template": "switch_trigger",
                "config": {"switch_id": 10},
            },
        )
        assert result["success"] is True
        saved = json.loads((tmp_data / "Troops.json").read_text(encoding="utf-8"))
        codes = [c["code"] for c in saved[1]["pages"][0]["list"]]
        assert 121 in codes
        assert codes[-1] == 0


# ── 에러 경로 ────────────────────────────────────────────────────────────


class TestErrorPaths:
    def test_unsupported_action(self, tmp_data: Path):
        (tmp_data / "CommonEvents.json").write_text("[null]", encoding="utf-8")
        result = execute_events_step(tmp_data, "bogus_action", "CommonEvents.json", {})
        assert result["success"] is False
        assert "미지원" in result["error"]

    def test_missing_file(self, tmp_data: Path):
        result = execute_events_step(
            tmp_data, "create_common_event", "CommonEvents.json", {"name": "x"}
        )
        # 파일 없으면 FileNotFoundError → 에러
        assert result["success"] is False

    def test_update_nonexistent_event(self, tmp_data: Path):
        (tmp_data / "CommonEvents.json").write_text("[null]", encoding="utf-8")
        result = execute_events_step(
            tmp_data,
            "update_common_event",
            "CommonEvents.json",
            {"id": 99, "updates": {"name": "X"}},
        )
        assert result["success"] is False
