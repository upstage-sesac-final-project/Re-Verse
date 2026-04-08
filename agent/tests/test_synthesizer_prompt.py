"""synthesizer_prompt 스냅샷 비교 순수 로직 테스트.

LLM 호출 없이 dict 비교 함수만 검증한다.
"""

from __future__ import annotations

from agent.prompts.synthesizer_prompt import (
    _extract_actual_changes,
    _extract_actual_changes_from_snapshots,
)


# ── _extract_actual_changes_from_snapshots ───────────────────


class TestExtractActualChangesFromSnapshots:
    def test_dict_field_changed(self) -> None:
        """System.json 같은 단일 dict에서 필드 변경 감지."""
        before = {"System.json": {"gameTitle": "Old", "startX": 0}}
        after = {"System.json": {"gameTitle": "New", "startX": 0}}
        result = _extract_actual_changes_from_snapshots(before, after)
        assert len(result) == 1
        assert "gameTitle" in result[0]
        assert "`Old`" in result[0]
        assert "`New`" in result[0]

    def test_no_change_returns_empty(self) -> None:
        before = {"System.json": {"gameTitle": "Same"}}
        after = {"System.json": {"gameTitle": "Same"}}
        assert _extract_actual_changes_from_snapshots(before, after) == []

    def test_array_item_changed(self) -> None:
        """Actors.json 같은 배열에서 항목 필드 변경 감지."""
        before = {"Actors.json": [None, {"id": 1, "name": "Hero", "maxLevel": 50}]}
        after = {"Actors.json": [None, {"id": 1, "name": "Hero", "maxLevel": 99}]}
        result = _extract_actual_changes_from_snapshots(before, after)
        assert len(result) == 1
        assert "maxLevel" in result[0]
        assert "Hero" in result[0]

    def test_empty_snapshots(self) -> None:
        assert _extract_actual_changes_from_snapshots({}, {}) == []

    def test_new_file_in_modified(self) -> None:
        """수정 스냅샷에만 존재하는 파일 — before가 {}이므로 모든 필드가 변경."""
        before = {}
        after = {"System.json": {"gameTitle": "New"}}
        result = _extract_actual_changes_from_snapshots(before, after)
        assert len(result) == 1

    def test_array_null_items_skipped(self) -> None:
        """null 항목은 건너뛴다."""
        before = {"Actors.json": [None, None]}
        after = {"Actors.json": [None, None]}
        assert _extract_actual_changes_from_snapshots(before, after) == []

    def test_multiple_files_changes(self) -> None:
        """여러 파일에서 동시 변경."""
        before = {
            "System.json": {"gameTitle": "Old"},
            "Actors.json": [None, {"id": 1, "name": "A", "hp": 100}],
        }
        after = {
            "System.json": {"gameTitle": "New"},
            "Actors.json": [None, {"id": 1, "name": "A", "hp": 200}],
        }
        result = _extract_actual_changes_from_snapshots(before, after)
        assert len(result) == 2


# ── _extract_actual_changes ──────────────────────────────────


class TestExtractActualChanges:
    def test_array_item_changed(self) -> None:
        before = {"Actors.json": [None, {"id": 1, "name": "Hero", "maxLevel": 50}]}
        after = {"Actors.json": [None, {"id": 1, "name": "Hero", "maxLevel": 99}]}
        changes = _extract_actual_changes(before, after)
        key = "Actors.json[Hero]"
        assert key in changes
        assert changes[key]["maxLevel"] == {"before": 50, "after": 99}

    def test_no_change_returns_empty(self) -> None:
        data = {"Actors.json": [None, {"id": 1, "name": "Hero"}]}
        assert _extract_actual_changes(data, data) == {}

    def test_dict_file_skipped(self) -> None:
        """System.json(단일 dict)은 이 함수에서 처리하지 않는다."""
        before = {"System.json": {"gameTitle": "Old"}}
        after = {"System.json": {"gameTitle": "New"}}
        assert _extract_actual_changes(before, after) == {}

    def test_multiple_fields_changed(self) -> None:
        before = {"Items.json": [None, {"id": 1, "name": "Potion", "price": 50, "scope": 7}]}
        after = {"Items.json": [None, {"id": 1, "name": "Hi-Potion", "price": 100, "scope": 7}]}
        changes = _extract_actual_changes(before, after)
        item_changes = list(changes.values())[0]
        assert "name" in item_changes
        assert "price" in item_changes
        assert "scope" not in item_changes
