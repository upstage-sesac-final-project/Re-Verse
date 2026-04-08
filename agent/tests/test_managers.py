"""Manager 단위 테스트 — SystemManager, ClassManager, ActorManager, SkillManager.

로컬 game_001/data/ 의 실제 JSON을 사용한다.
테스트에서 생성한 데이터는 고유 이름(ZZZ_ prefix)으로 충돌을 방지한다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.backend.services.json_modify_tools.managers.actor_manager import ActorManager
from app.backend.services.json_modify_tools.managers.class_manager import ClassManager
from app.backend.services.json_modify_tools.managers.skill_manager import SkillManager
from app.backend.services.json_modify_tools.managers.system_manager import SystemManager


def _get_data_path() -> Path:
    from app.backend.core.config import settings

    return Path(settings.STORAGE_PATH) / "game_001" / "data"


# ── SystemManager ────────────────────────────────────────────


class TestSystemManager:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mgr = SystemManager(_get_data_path(), "test_sys")

    @pytest.mark.asyncio
    async def test_update_game_title(self) -> None:
        old_data = self.mgr.load_json_data()
        old_title = old_data.get("gameTitle", "")

        r = await self.mgr.execute(
            "update_game_title", target_info={"game_title": "TEST_TITLE_TMP"}
        )
        assert r["success"] is True
        assert r["old_title"] == old_title
        assert r["new_title"] == "TEST_TITLE_TMP"

        # 복원
        await self.mgr.execute("update_game_title", target_info={"game_title": old_title})

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

        # 복원
        await self.mgr.execute("set_variable_name", target_info={"variable_id": 5, "name": ""})

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

        # 복원
        await self.mgr.execute("set_switch_name", target_info={"switch_id": 3, "name": ""})

    @pytest.mark.asyncio
    async def test_update_starting_position(self) -> None:
        old = self.mgr.load_json_data()
        old_map = old.get("startMapId")
        old_x = old.get("startX")
        old_y = old.get("startY")

        r = await self.mgr.execute(
            "update_starting_position",
            target_info={"map_id": 2, "x": 10, "y": 20},
        )
        assert r["success"] is True

        system = self.mgr.load_json_data()
        assert system["startMapId"] == 2
        assert system["startX"] == 10
        assert system["startY"] == 20

        # 복원
        await self.mgr.execute(
            "update_starting_position",
            target_info={"map_id": old_map, "x": old_x, "y": old_y},
        )

    @pytest.mark.asyncio
    async def test_unsupported_action(self) -> None:
        r = await self.mgr.execute("unknown_action")
        assert r["success"] is False


# ── ClassManager ─────────────────────────────────────────────


class TestClassManager:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mgr = ClassManager(_get_data_path(), "test_cls")

    @pytest.mark.asyncio
    async def test_query_existing(self) -> None:
        """기본 데이터에 있는 클래스를 조회."""
        data = self.mgr.load_json_data()
        # 첫 번째 실제 클래스 이름 찾기
        first_name = None
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                first_name = item["name"]
                break
        assert first_name is not None

        r = await self.mgr.execute("query", class_name=first_name)
        assert r.get("exists") is True

    @pytest.mark.asyncio
    async def test_query_not_found(self) -> None:
        r = await self.mgr.execute("query", class_name="ZZZ_NONEXISTENT_CLASS")
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
    def _setup(self):
        self.mgr = ActorManager(_get_data_path(), "test_actor")

    @pytest.mark.asyncio
    async def test_query_existing_by_name(self) -> None:
        """기본 데이터에 있는 액터를 이름으로 조회."""
        data = self.mgr.load_json_data()
        first_name = None
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                first_name = item["name"]
                break
        assert first_name is not None

        r = await self.mgr.execute("query", actor_name=first_name)
        assert r.get("exists") is True

    @pytest.mark.asyncio
    async def test_query_not_found(self) -> None:
        r = await self.mgr.execute("query", actor_name="ZZZ_NONEXISTENT_ACTOR")
        assert r.get("exists") is False

    @pytest.mark.asyncio
    async def test_list_actors(self) -> None:
        r = await self.mgr.execute("list")
        assert r.get("success") is True
        assert "id=1:" in (r.get("stdout") or r.get("message") or "")

    @pytest.mark.asyncio
    async def test_search_actor(self) -> None:
        """기본 데이터의 첫 액터 이름으로 검색."""
        data = self.mgr.load_json_data()
        first_name = None
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                first_name = item["name"]
                break
        assert first_name is not None

        r = await self.mgr.execute("search", target_info={"searchTerm": first_name})
        assert r.get("success") is True
        assert r.get("exists") is True

    @pytest.mark.asyncio
    async def test_update_general(self) -> None:
        """create → update_general → 복원."""
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

        # 값 확인
        data = self.mgr.load_json_data()
        assert data[actor_id]["nickname"] == "테스트닉"
        assert data[actor_id]["initialLevel"] == 10

    @pytest.mark.asyncio
    async def test_update_general_type_coercion(self) -> None:
        """문자열 '10' → int 10 변환."""
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
        """지원하지 않는 필드만 주면 실패."""
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
        """빈 actor_name은 에러."""
        r = await self.mgr.execute("query", actor_name="")
        assert r.get("success") is False

    @pytest.mark.asyncio
    async def test_query_by_id_out_of_range(self) -> None:
        """범위 밖 actor_id — actor_name으로 검색하면 exists=False."""
        r = await self.mgr.execute("query", actor_name="ZZZ_NEVER_EXISTS_99999")
        assert r.get("exists") is False

    @pytest.mark.asyncio
    async def test_update_general_bulk(self) -> None:
        """전체 액터에 일괄 필드 업데이트."""
        data = self.mgr.load_json_data()
        originals = {}
        for i, a in enumerate(data):
            if isinstance(a, dict):
                originals[i] = a.get("initialLevel")

        r = await self.mgr.execute(
            "update_general_bulk",
            target_info={
                "selector": {"mode": "all"},
                "updates": {"initialLevel": 5},
            },
        )
        assert r.get("success") is True
        assert r.get("updated_count", 0) > 0

        # 복원
        data = self.mgr.load_json_data()
        for i, orig in originals.items():
            if orig is not None and isinstance(data[i], dict):
                data[i]["initialLevel"] = orig
        self.mgr.save_json_data(data)

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
    def _setup(self):
        self.mgr = ClassManager(_get_data_path(), "test_cls_ext")

    @pytest.mark.asyncio
    async def test_update(self) -> None:
        """클래스 생성 → update → 필드 확인."""
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
        """이미 존재하는 클래스명으로 create → exists 에러."""
        data = self.mgr.load_json_data()
        first_name = None
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                first_name = item["name"]
                break
        assert first_name is not None

        r = await self.mgr.execute("create", class_name=first_name)
        assert r.get("success") is False
        assert r.get("exists") is True


# ── SkillManager ─────────────────────────────────────────────


class TestSkillManager:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.mgr = SkillManager(_get_data_path(), "test_skill")

    @pytest.mark.asyncio
    async def test_add_skill(self) -> None:
        unique = f"ZZZ_SKILL_{uuid.uuid4().hex[:8]}"
        r = await self.mgr.execute("add", target_name=unique, mpCost=10, description="테스트 스킬")
        assert r.get("success") is True
        assert r.get("target_name") == unique

    @pytest.mark.asyncio
    async def test_add_duplicate_skill(self) -> None:
        """기본 데이터에 있는 스킬명으로 add → 실패."""
        data = self.mgr.load_json_data()
        first_name = None
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                first_name = item["name"]
                break
        assert first_name is not None

        r = await self.mgr.execute("add", target_name=first_name)
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
