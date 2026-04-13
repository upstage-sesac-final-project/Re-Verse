"""Manager 단위 테스트 — SystemManager, ClassManager, ActorManager, SkillManager.

tmp_path에 최소 fixture 데이터를 생성하여 외부 파일 의존 없이 테스트한다.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.backend.services.json_modify_tools.managers.actor_manager import ActorManager
from app.backend.services.json_modify_tools.managers.class_manager import ClassManager
from app.backend.services.json_modify_tools.managers.skill_manager import SkillManager
from app.backend.services.json_modify_tools.managers.system_manager import SystemManager

# ── fixture 데이터 ──────────────────────────────────────────────


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def data_path(tmp_path: Path) -> Path:
    """최소 RPG Maker MZ JSON 파일들을 tmp_path에 생성."""
    # System.json
    _write_json(
        tmp_path / "System.json",
        {
            "gameTitle": "테스트 게임",
            "startMapId": 1,
            "startX": 5,
            "startY": 5,
            "variables": [""] * 20,
            "switches": [""] * 20,
        },
    )

    # Classes.json
    _write_json(
        tmp_path / "Classes.json",
        [
            None,
            {
                "id": 1,
                "name": "전사",
                "expParams": [30, 20, 30, 30],
                "params": [[0] * 99] * 8,
                "learnings": [],
                "traits": [],
                "note": "",
            },
        ],
    )

    # Actors.json
    _write_json(
        tmp_path / "Actors.json",
        [
            None,
            {
                "id": 1,
                "name": "용사",
                "nickname": "",
                "classId": 1,
                "initialLevel": 1,
                "maxLevel": 99,
                "characterName": "Actor1",
                "characterIndex": 0,
                "faceName": "Actor1",
                "faceIndex": 0,
                "battlerName": "Actor1_1",
                "equips": [0, 0, 0, 0, 0],
                "traits": [],
                "note": "",
                "profile": "",
            },
        ],
    )

    # Skills.json
    _write_json(
        tmp_path / "Skills.json",
        [
            None,
            {
                "id": 1,
                "name": "공격",
                "description": "",
                "iconIndex": 76,
                "mpCost": 0,
                "scope": 1,
                "occasion": 1,
                "damage": {"type": 1, "elementId": -1, "formula": "a.atk * 4 - b.def * 2"},
                "effects": [],
                "note": "",
            },
        ],
    )

    return tmp_path


# ── SystemManager ────────────────────────────────────────────


class TestSystemManager:
    @pytest.fixture(autouse=True)
    def _setup(self, data_path: Path):
        self.mgr = SystemManager(data_path, "test_sys")

    @pytest.mark.asyncio
    async def test_update_game_title(self) -> None:
        r = await self.mgr.execute("update_game_title", target_info={"game_title": "NEW_TITLE"})
        assert r["success"] is True
        assert r["new_title"] == "NEW_TITLE"

        data = self.mgr.load_json_data()
        assert data["gameTitle"] == "NEW_TITLE"

    @pytest.mark.asyncio
    async def test_update_game_title_empty(self) -> None:
        r = await self.mgr.execute("update_game_title", target_info={"game_title": ""})
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_variable_name(self) -> None:
        r = await self.mgr.execute(
            "set_variable_name", target_info={"variable_id": 5, "name": "test_var"}
        )
        assert r["success"] is True
        system = self.mgr.load_json_data()
        assert system["variables"][5] == "test_var"

    @pytest.mark.asyncio
    async def test_set_variable_name_invalid_id(self) -> None:
        r = await self.mgr.execute(
            "set_variable_name", target_info={"variable_id": "abc", "name": "x"}
        )
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_switch_name(self) -> None:
        r = await self.mgr.execute(
            "set_switch_name", target_info={"switch_id": 3, "name": "test_switch"}
        )
        assert r["success"] is True
        system = self.mgr.load_json_data()
        assert system["switches"][3] == "test_switch"

    @pytest.mark.asyncio
    async def test_update_starting_position(self) -> None:
        r = await self.mgr.execute(
            "update_starting_position",
            target_info={"map_id": 2, "x": 10, "y": 20},
        )
        assert r["success"] is True
        system = self.mgr.load_json_data()
        assert system["startMapId"] == 2
        assert system["startX"] == 10
        assert system["startY"] == 20

    @pytest.mark.asyncio
    async def test_unsupported_action(self) -> None:
        r = await self.mgr.execute("unknown_action")
        assert r["success"] is False


# ── ClassManager ─────────────────────────────────────────────


class TestClassManager:
    @pytest.fixture(autouse=True)
    def _setup(self, data_path: Path):
        self.mgr = ClassManager(data_path, "test_cls")

    @pytest.mark.asyncio
    async def test_query_existing(self) -> None:
        r = await self.mgr.execute("query", class_name="전사")
        assert r.get("exists") is True

    @pytest.mark.asyncio
    async def test_query_not_found(self) -> None:
        r = await self.mgr.execute("query", class_name="ZZZ_NONEXISTENT")
        assert r.get("exists") is False

    @pytest.mark.asyncio
    async def test_create_and_query(self) -> None:
        unique = f"ZZZ_CLS_{uuid.uuid4().hex[:8]}"
        r = await self.mgr.execute("create", class_name=unique)
        assert r.get("success") is True

        q = await self.mgr.execute("query", class_name=unique)
        assert q.get("exists") is True


# ── ActorManager ─────────────────────────────────────────────


class TestActorManager:
    @pytest.fixture(autouse=True)
    def _setup(self, data_path: Path):
        self.mgr = ActorManager(data_path, "test_actor")

    @pytest.mark.asyncio
    async def test_query_existing_by_name(self) -> None:
        r = await self.mgr.execute("query", actor_name="용사")
        assert r.get("exists") is True

    @pytest.mark.asyncio
    async def test_query_not_found(self) -> None:
        r = await self.mgr.execute("query", actor_name="ZZZ_NONEXISTENT")
        assert r.get("exists") is False

    @pytest.mark.asyncio
    async def test_list_actors(self) -> None:
        r = await self.mgr.execute("list")
        assert r.get("success") is True
        assert "id=1:" in (r.get("stdout") or r.get("message") or "")

    @pytest.mark.asyncio
    async def test_search_actor(self) -> None:
        r = await self.mgr.execute("search", target_info={"searchTerm": "용사"})
        assert r.get("success") is True
        assert r.get("exists") is True

    @pytest.mark.asyncio
    async def test_update_general(self) -> None:
        unique = f"ZZZ_UPD_{uuid.uuid4().hex[:8]}"
        cr = await self.mgr.execute("create", actor_name=unique)
        assert cr.get("success") is True
        actor_id = cr.get("actor_id")

        r = await self.mgr.execute(
            "update_general",
            target_info={
                "actor_id": actor_id,
                "updates": {"nickname": "테스트닉", "initialLevel": 10},
            },
        )
        assert r.get("success") is True
        assert "nickname" in r.get("updated_fields", [])
        assert "initialLevel" in r.get("updated_fields", [])

        data = self.mgr.load_json_data()
        assert data[actor_id]["nickname"] == "테스트닉"
        assert data[actor_id]["initialLevel"] == 10

    @pytest.mark.asyncio
    async def test_update_general_type_coercion(self) -> None:
        unique = f"ZZZ_COERCE_{uuid.uuid4().hex[:8]}"
        cr = await self.mgr.execute("create", actor_name=unique)
        actor_id = cr.get("actor_id")

        r = await self.mgr.execute(
            "update_general",
            target_info={"actor_id": actor_id, "updates": {"initialLevel": "15"}},
        )
        assert r.get("success") is True
        data = self.mgr.load_json_data()
        assert data[actor_id]["initialLevel"] == 15
        assert isinstance(data[actor_id]["initialLevel"], int)

    @pytest.mark.asyncio
    async def test_update_general_invalid_actor_id(self) -> None:
        r = await self.mgr.execute(
            "update_general",
            target_info={"actor_id": "abc", "updates": {"nickname": "x"}},
        )
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_update_general_no_valid_fields(self) -> None:
        unique = f"ZZZ_NOFLD_{uuid.uuid4().hex[:8]}"
        cr = await self.mgr.execute("create", actor_name=unique)
        actor_id = cr.get("actor_id")

        r = await self.mgr.execute(
            "update_general",
            target_info={"actor_id": actor_id, "updates": {"unknownField": 42}},
        )
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_query_empty_name_fails(self) -> None:
        r = await self.mgr.execute("query", actor_name="")
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_query_by_id_out_of_range(self) -> None:
        r = await self.mgr.execute("query", actor_name="ZZZ_NEVER_EXISTS_99999")
        assert r.get("exists") is False

    @pytest.mark.asyncio
    async def test_update_general_bulk(self) -> None:
        r = await self.mgr.execute(
            "update_general_bulk",
            target_info={
                "selector": {"mode": "all"},
                "updates": {"initialLevel": 5},
            },
        )
        assert r.get("success") is True
        assert r.get("updated_count", 0) > 0

        data = self.mgr.load_json_data()
        for a in data:
            if isinstance(a, dict):
                assert a["initialLevel"] == 5

    @pytest.mark.asyncio
    async def test_update_general_bulk_no_valid_fields(self) -> None:
        r = await self.mgr.execute(
            "update_general_bulk",
            target_info={"updates": {"unknownField": 42}},
        )
        assert r.get("success") is False


# ── ClassManager 추가 테스트 ─────────────────────────────────


class TestClassManagerExtended:
    @pytest.fixture(autouse=True)
    def _setup(self, data_path: Path):
        self.mgr = ClassManager(data_path, "test_cls_ext")

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        unique = f"ZZZ_CLS_UPD_{uuid.uuid4().hex[:8]}"
        cr = await self.mgr.execute("create", class_name=unique)
        assert cr.get("success") is True
        class_id = cr.get("class_id")

        r = await self.mgr.execute(
            "update",
            target_info={"class_id": class_id, "updates": {"name": f"{unique}_RENAMED"}},
        )
        assert r.get("success") is True
        assert "name" in r.get("updated_fields", [])

    @pytest.mark.asyncio
    async def test_update_invalid_id(self) -> None:
        r = await self.mgr.execute(
            "update",
            target_info={"class_id": "abc", "updates": {"name": "x"}},
        )
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_update_no_valid_fields(self) -> None:
        unique = f"ZZZ_CLS_NF_{uuid.uuid4().hex[:8]}"
        cr = await self.mgr.execute("create", class_name=unique)
        class_id = cr.get("class_id")

        r = await self.mgr.execute(
            "update",
            target_info={"class_id": class_id, "updates": {"badField": 42}},
        )
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_create_duplicate(self) -> None:
        r = await self.mgr.execute("create", class_name="전사")
        assert r.get("success") is False
        assert r.get("exists") is True


# ── SkillManager ─────────────────────────────────────────────


class TestSkillManager:
    @pytest.fixture(autouse=True)
    def _setup(self, data_path: Path):
        self.mgr = SkillManager(data_path, "test_skill")

    @pytest.mark.asyncio
    async def test_add_skill(self) -> None:
        unique = f"ZZZ_SKILL_{uuid.uuid4().hex[:8]}"
        r = await self.mgr.execute("add", target_name=unique, mpCost=10, description="테스트 스킬")
        assert r.get("success") is True
        assert r.get("target_name") == unique

    @pytest.mark.asyncio
    async def test_add_duplicate_skill(self) -> None:
        r = await self.mgr.execute("add", target_name="공격")
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_update_skill(self) -> None:
        unique = f"ZZZ_SKILL_UPD_{uuid.uuid4().hex[:8]}"
        await self.mgr.execute("add", target_name=unique)

        r = await self.mgr.execute("update", target_name=unique, mpCost=50, description="수정됨")
        assert r.get("success") is True

        data = self.mgr.load_json_data()
        skill = next(s for s in data if isinstance(s, dict) and s.get("name") == unique)
        assert skill["mpCost"] == 50
        assert skill["description"] == "수정됨"

    @pytest.mark.asyncio
    async def test_update_nonexistent_skill(self) -> None:
        r = await self.mgr.execute("update", target_name="ZZZ_NONEXISTENT_SKILL")
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_unsupported_action(self) -> None:
        r = await self.mgr.execute("delete", target_name="x")
        assert r.get("success") is False
