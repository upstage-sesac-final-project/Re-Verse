"""db_lookup 모듈 단위 테스트 (Task 2 산출물).

reader 의 private 로직을 공유 모듈로 추출했으므로 직접 검증한다.
LLM 호출은 없다.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.editor.db_lookup import (
    FUZZY_SUGGESTION_THRESHOLD,
    FUZZY_THRESHOLD,
    PARAMS_INDEX,
    build_id_name_map,
    find_candidates,
    fuzzy_match,
    get_field_value,
    get_numeric_value,
    lookup_by_name,
    valid_items,
)


class TestValidItems:
    def test_strips_null_and_nameless(self):
        data = [None, {"id": 1, "name": "A"}, {"id": 2, "name": ""}, {"id": 3, "name": "B"}]
        assert valid_items(data) == [{"id": 1, "name": "A"}, {"id": 3, "name": "B"}]

    def test_non_list_returns_empty(self):
        assert valid_items(None) == []
        assert valid_items({}) == []


class TestFuzzyMatch:
    def test_exact_match_wins(self):
        items = [{"id": 1, "name": "슬라임"}, {"id": 2, "name": "고블린"}]
        out = fuzzy_match("슬라임", items)
        assert out[0]["id"] == 1

    def test_threshold_filters(self):
        items = [{"id": 1, "name": "슬라임"}, {"id": 2, "name": "아예다름"}]
        out = fuzzy_match("슬라임왕", items, threshold=0.8)
        # "슬라임왕" vs "슬라임" 유사도 ~= 0.857 → 포함
        assert any(i["id"] == 1 for i in out)
        # "아예다름" 은 임계값 미달 → 제외
        assert not any(i["id"] == 2 for i in out)

    def test_empty_name_returns_empty(self):
        items = [{"id": 1, "name": "X"}]
        assert fuzzy_match("", items) == []


class TestFindCandidates:
    def test_id_numeric_short_circuit(self):
        items = [{"id": 5, "name": "Z"}, {"id": 99, "name": "X"}]
        out = find_candidates("5", items)
        assert out == [{"id": 5, "name": "Z"}]

    def test_exact_before_ci(self):
        items = [{"id": 1, "name": "Slime"}, {"id": 2, "name": "slime"}]
        assert find_candidates("Slime", items)[0]["id"] == 1
        assert find_candidates("SLIME", items)[0]["id"] in {1, 2}

    def test_prefix_fallback(self):
        items = [{"id": 1, "name": "드래곤 슬레이어"}, {"id": 2, "name": "고블린"}]
        out = find_candidates("드래곤", items)
        assert out and out[0]["id"] == 1

    def test_fuzzy_fallback(self):
        items = [{"id": 1, "name": "슬라임"}]
        out = find_candidates("슬라임왕", items)
        assert out  # fuzzy 가 잡아줌


class TestFieldValue:
    def test_direct_field(self):
        assert get_field_value({"hp": 100}, "hp") == (100, True)

    def test_missing_field(self):
        assert get_field_value({}, "nope") == (None, False)

    def test_params_alias(self):
        entity = {"params": [500, 50, 20, 10, 0, 0, 5, 5]}
        assert get_field_value(entity, "maxhp") == (500, True)
        assert get_field_value(entity, "atk") == (20, True)

    def test_dot_notation(self):
        entity = {"damage": {"elementId": 2}}
        assert get_field_value(entity, "damage.elementId") == (2, True)

    def test_numeric_helper(self):
        assert get_numeric_value({"hp": 100}, "hp") == 100.0
        assert get_numeric_value({"hp": "x"}, "hp") is None


class TestBuildIdNameMap:
    def test_basic(self):
        data = [None, {"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        assert build_id_name_map(data) == {1: "A", 2: "B"}

    def test_non_list(self):
        assert build_id_name_map(None) == {}


class TestLookupByName:
    """rule-base DB 조회 고수준 API — Definition 이 소비."""

    def _mock_read(self, data):
        return patch("agent.editor.db_lookup.read_game_json", return_value=data)

    def test_unsupported_category_returns_not_found(self):
        out = lookup_by_name("g", "unknown", "x")
        assert out["status"] == "not_found"
        assert out["file"] is None

    def test_empty_name_returns_not_found(self):
        out = lookup_by_name("g", "enemy", "")
        assert out["status"] == "not_found"

    def test_exact_match(self):
        data = [None, {"id": 1, "name": "슬라임"}, {"id": 2, "name": "드래곤"}]
        with self._mock_read(data):
            out = lookup_by_name("g", "enemy", "슬라임")
        assert out["status"] == "found"
        assert out["exact_match"]["id"] == 1
        assert out["file"] == "Enemies.json"

    def test_ambiguous_duplicate_names(self):
        data = [None, {"id": 1, "name": "A"}, {"id": 2, "name": "A"}]
        with self._mock_read(data):
            out = lookup_by_name("g", "enemy", "A")
        assert out["status"] == "ambiguous"
        assert len(out["candidates"]) == 2

    def test_fuzzy_triggers_ambiguous(self):
        """임계값 이상 유사 이름이 있으면 already_exists 경로를 안내하기 위해 ambiguous 반환."""
        data = [None, {"id": 1, "name": "슬라임"}]
        with self._mock_read(data):
            out = lookup_by_name("g", "enemy", "슬라임왕")
        assert out["status"] == "ambiguous"
        assert any(c["id"] == 1 for c in out["candidates"])

    def test_not_found_with_suggestions(self):
        data = [None, {"id": 1, "name": "아무관련없는이름이것임"}]
        with self._mock_read(data):
            out = lookup_by_name("g", "enemy", "짧다")
        assert out["status"] == "not_found"
        assert out["suggestions"] == []

    def test_id_numeric_lookup(self):
        data = [None, {"id": 7, "name": "X"}]
        with self._mock_read(data):
            out = lookup_by_name("g", "item", "7")
        assert out["status"] == "found"
        assert out["exact_match"]["id"] == 7

    def test_file_missing_returns_not_found(self):
        with patch("agent.editor.db_lookup.read_game_json", side_effect=FileNotFoundError):
            out = lookup_by_name("g", "enemy", "슬라임")
        assert out["status"] == "not_found"


def test_module_constants_exposed():
    """Phase 회귀 방지 — 이 상수들은 reader/definition 이 의존한다."""
    assert PARAMS_INDEX["maxhp"] == 0
    assert PARAMS_INDEX["atk"] == 2
    assert 0 < FUZZY_SUGGESTION_THRESHOLD < FUZZY_THRESHOLD <= 1.0
