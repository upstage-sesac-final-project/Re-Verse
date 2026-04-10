"""executor.py 내 순수 헬퍼 함수 테스트.

LLM/MCP 호출 없이 dict 변환, 리스트 정규화, 로컬 검색 등을 검증한다.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

executor_module = importlib.import_module("agent.graph.nodes.executor")


# ── _coerce_list_from_mcp_search_payload ─────────────────────


class TestCoerceListFromMcpSearchPayload:
    fn = staticmethod(executor_module._coerce_list_from_mcp_search_payload)

    def test_none_returns_empty(self) -> None:
        assert self.fn(None) == []

    def test_list_passthrough(self) -> None:
        assert self.fn([1, 2]) == [1, 2]

    def test_non_dict_non_list_returns_empty(self) -> None:
        assert self.fn("string") == []
        assert self.fn(42) == []

    def test_dict_with_items_key(self) -> None:
        assert self.fn({"items": [{"id": 1}]}) == [{"id": 1}]

    def test_dict_with_results_key(self) -> None:
        assert self.fn({"results": [{"id": 2}]}) == [{"id": 2}]

    def test_dict_with_singular_key(self) -> None:
        assert self.fn({"item": {"id": 1}}) == [{"id": 1}]

    def test_dict_no_known_keys(self) -> None:
        assert self.fn({"foo": "bar"}) == []


# ── _first_numeric_id_from_row ───────────────────────────────


class TestFirstNumericIdFromRow:
    fn = staticmethod(executor_module._first_numeric_id_from_row)

    def test_finds_id(self) -> None:
        assert self.fn({"id": 5, "name": "x"}, ("id",)) == 5

    def test_string_id_coerced(self) -> None:
        assert self.fn({"actorId": "3"}, ("actorId",)) == 3

    def test_none_value_skipped(self) -> None:
        assert self.fn({"id": None, "actorId": 7}, ("id", "actorId")) == 7

    def test_non_dict_returns_none(self) -> None:
        assert self.fn("not a dict", ("id",)) is None

    def test_no_matching_key(self) -> None:
        assert self.fn({"name": "x"}, ("id", "actorId")) is None

    def test_non_numeric_value(self) -> None:
        assert self.fn({"id": "abc"}, ("id",)) is None


# ── _row_name_matches_search_term ────────────────────────────


class TestRowNameMatchesSearchTerm:
    fn = staticmethod(executor_module._row_name_matches_search_term)

    def test_exact_match(self) -> None:
        assert self.fn({"name": "Hero"}, "Hero") is True

    def test_partial_match(self) -> None:
        assert self.fn({"name": "Fire Ball"}, "fire") is True

    def test_no_match(self) -> None:
        assert self.fn({"name": "Ice"}, "fire") is False

    def test_empty_term_always_true(self) -> None:
        assert self.fn({"name": "anything"}, "") is True

    def test_empty_name_returns_false(self) -> None:
        assert self.fn({"name": ""}, "hero") is False

    def test_display_name_fallback(self) -> None:
        assert self.fn({"displayName": "Shadow"}, "shadow") is True


# ── _items_local_search_by_name ──────────────────────────────


class TestItemsLocalSearchByName:
    fn = staticmethod(executor_module._items_local_search_by_name)

    def test_found(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        items = [None, {"id": 1, "name": "Potion"}, {"id": 2, "name": "Elixir"}]
        (dp / "Items.json").write_text(json.dumps(items), encoding="utf-8")
        exists, item_id = self.fn(dp, "potion")
        assert exists is True
        assert item_id == 1

    def test_not_found(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        items = [None, {"id": 1, "name": "Potion"}]
        (dp / "Items.json").write_text(json.dumps(items), encoding="utf-8")
        exists, _ = self.fn(dp, "sword")
        assert exists is False

    def test_empty_term(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        exists, _ = self.fn(dp, "")
        assert exists is False

    def test_file_missing(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        exists, _ = self.fn(dp, "potion")
        assert exists is False


# ── _actors_local_search_by_name ─────────────────────────────


class TestActorsLocalSearchByName:
    fn = staticmethod(executor_module._actors_local_search_by_name)

    def test_found(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        actors = [None, {"id": 1, "name": "Hero"}]
        (dp / "Actors.json").write_text(json.dumps(actors), encoding="utf-8")
        exists, aid = self.fn(dp, "hero")
        assert exists is True
        assert aid == 1

    def test_not_found(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        actors = [None, {"id": 1, "name": "Hero"}]
        (dp / "Actors.json").write_text(json.dumps(actors), encoding="utf-8")
        exists, _ = self.fn(dp, "villain")
        assert exists is False


# ── _skills_local_search_by_name ─────────────────────────────


class TestSkillsLocalSearchByName:
    fn = staticmethod(executor_module._skills_local_search_by_name)

    def test_found(self, tmp_path: Path) -> None:
        dp = tmp_path / "data"
        dp.mkdir()
        skills = [None, {"id": 1, "name": "Fire"}, {"id": 2, "name": "Ice"}]
        (dp / "Skills.json").write_text(json.dumps(skills), encoding="utf-8")
        exists, sid = self.fn(dp, "fire")
        assert exists is True
        assert sid == 1


# ── _normalize_mcp_arguments ─────────────────────────────────


class TestNormalizeMcpArguments:
    fn = staticmethod(executor_module._normalize_mcp_arguments)

    def test_actors_create_maps_actor_name(self) -> None:
        result = self.fn("Actors.json", "create", {"actor_name": "Hero"})
        assert result["name"] == "Hero"
        assert "actor_name" not in result

    def test_actors_search_sets_search_term(self) -> None:
        result = self.fn("Actors.json", "search", {"actor_name": "Hero"})
        assert result == {"searchTerm": "Hero"}

    def test_actors_query_by_id(self) -> None:
        result = self.fn("Actors.json", "query_by_id", {"actor_id": "3"})
        assert result == {"actorId": 3}

    def test_actors_update_actor(self) -> None:
        result = self.fn(
            "Actors.json",
            "update_actor",
            {"actor_id": 1, "updates": {"maxLevel": 99}},
        )
        assert result == {"actorId": 1, "updates": {"maxLevel": 99}}

    def test_skills_create_maps_skill_name(self) -> None:
        result = self.fn("Skills.json", "create", {"skill_name": "Fire"})
        assert result["name"] == "Fire"

    def test_items_search_sets_search_term(self) -> None:
        result = self.fn("Items.json", "search", {"item_name": "Potion"})
        assert result == {"searchTerm": "Potion"}

    def test_items_update_merges_fields(self) -> None:
        result = self.fn(
            "Items.json",
            "update",
            {"item_id": 5, "new_description": "Good potion", "new_name": "Hi-Potion"},
        )
        assert result["itemId"] == 5
        assert result["updates"]["description"] == "Good potion"
        assert result["updates"]["name"] == "Hi-Potion"


# ── _enrich_items_target_info_from_deps ──────────────────────


class TestEnrichItemsTargetInfoFromDeps:
    fn = staticmethod(executor_module._enrich_items_target_info_from_deps)

    def test_inherits_item_id(self) -> None:
        step = {"step_id": 2, "depends_on": [1]}
        step_results = {1: {"item_id": 10, "exists": True}}
        ti = {"name": "Potion"}
        result = self.fn(step, step_results, ti)
        assert result["item_id"] == 10

    def test_skips_if_already_has_id(self) -> None:
        step = {"step_id": 2, "depends_on": [1]}
        step_results = {1: {"item_id": 99}}
        ti = {"item_id": 5, "name": "Potion"}
        result = self.fn(step, step_results, ti)
        assert result["item_id"] == 5  # 원래 값 유지

    def test_no_deps(self) -> None:
        step = {"step_id": 1, "depends_on": []}
        result = self.fn(step, {}, {"name": "X"})
        assert "item_id" not in result
