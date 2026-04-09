"""game_data_io 순수 로직 테스트.

STORAGE_PATH를 monkeypatch로 tmp_path에 연결해서
실제 외부 서비스 없이 JSON 읽기/쓰기/스트리밍을 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def game_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """tmp_path 기반 game_001/data/ 구조를 만들고 STORAGE_PATH를 패치."""
    import agent.utils.game_data_io as mod

    storage = tmp_path / "storage" / "games"
    data = storage / "game_001" / "data"
    data.mkdir(parents=True)
    monkeypatch.setattr(mod, "STORAGE_PATH", str(storage))
    return data


# ── read_game_json ───────────────────────────────────────────


class TestReadGameJson:
    def test_read_normal(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import read_game_json

        (game_dir / "Actors.json").write_text(
            json.dumps([None, {"id": 1, "name": "Hero"}]), encoding="utf-8"
        )
        result = read_game_json("game_001", "Actors.json")
        assert result[1]["name"] == "Hero"

    def test_read_category_name(self, game_dir: Path) -> None:
        """카테고리명 'actor'로 호출 시 Actors.json을 읽는다."""
        from agent.utils.game_data_io import read_game_json

        (game_dir / "Actors.json").write_text(json.dumps([None]), encoding="utf-8")
        result = read_game_json("game_001", "actor")
        assert result == [None]

    def test_read_file_not_found(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import read_game_json

        result = read_game_json("game_001", "Missing.json")
        assert result is None

    def test_read_corrupt_json(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import read_game_json

        (game_dir / "Bad.json").write_text("{{not json}}", encoding="utf-8")
        result = read_game_json("game_001", "Bad.json")
        assert result is None

    def test_read_unknown_category_appends_json(self, game_dir: Path) -> None:
        """CATEGORY_TO_PLURAL에 없는 이름은 그대로 .json을 붙인다."""
        from agent.utils.game_data_io import read_game_json

        (game_dir / "Custom.json").write_text(json.dumps({"key": "val"}), encoding="utf-8")
        result = read_game_json("game_001", "Custom")
        assert result == {"key": "val"}


# ── write_game_json ──────────────────────────────────────────


class TestWriteGameJson:
    def test_write_normal(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import write_game_json

        data = [None, {"id": 1, "name": "Sword"}]
        assert write_game_json("game_001", "Items.json", data) is True
        written = json.loads((game_dir / "Items.json").read_text(encoding="utf-8"))
        assert written[1]["name"] == "Sword"

    def test_write_category_name(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import write_game_json

        assert write_game_json("game_001", "item", [None]) is True
        assert (game_dir / "Items.json").exists()

    def test_write_creates_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """data 디렉터리가 없으면 자동 생성."""
        import agent.utils.game_data_io as mod

        storage = tmp_path / "new_storage"
        monkeypatch.setattr(mod, "STORAGE_PATH", str(storage))
        from agent.utils.game_data_io import write_game_json

        assert write_game_json("game_999", "Test.json", {"ok": True}) is True


# ── read_game_json_fields ────────────────────────────────────


class TestReadGameJsonFields:
    def test_extract_fields(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import read_game_json_fields

        actors = [None, {"id": 1, "name": "Hero", "classId": 1, "extra": "big"}]
        (game_dir / "Actors.json").write_text(json.dumps(actors), encoding="utf-8")
        result = read_game_json_fields("game_001", "Actors", ["name"])
        assert result[0] is None
        assert result[1]["name"] == "Hero"
        assert result[1]["id"] == 1  # id는 자동 포함
        assert "extra" not in result[1]

    def test_file_not_found(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import read_game_json_fields

        assert read_game_json_fields("game_001", "Missing", ["name"]) == []


# ── get_next_append_id_streaming ─────────────────────────────


class TestGetNextAppendIdStreaming:
    def test_normal_array(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_append_id_streaming

        (game_dir / "Items.json").write_text(json.dumps([None, {"id": 1}]), encoding="utf-8")
        assert get_next_append_id_streaming(str(game_dir / "Items.json")) == 2

    def test_file_not_found(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_append_id_streaming

        assert get_next_append_id_streaming(str(game_dir / "Missing.json")) == 1


# ── get_next_empty_slot_id_streaming ─────────────────────────


class TestGetNextEmptySlotIdStreaming:
    def test_finds_empty_name(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_empty_slot_id_streaming

        data = [None, {"id": 1, "name": "Used"}, {"id": 2, "name": ""}, {"id": 3, "name": "Also"}]
        (game_dir / "Actors.json").write_text(json.dumps(data), encoding="utf-8")
        assert get_next_empty_slot_id_streaming(str(game_dir / "Actors.json")) == 2

    def test_no_empty_slot_returns_append(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_empty_slot_id_streaming

        data = [None, {"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        (game_dir / "Actors.json").write_text(json.dumps(data), encoding="utf-8")
        assert get_next_empty_slot_id_streaming(str(game_dir / "Actors.json")) == 3

    def test_file_not_found(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_empty_slot_id_streaming

        assert get_next_empty_slot_id_streaming(str(game_dir / "Missing.json")) == 1


# ── get_next_entity_id ───────────────────────────────────────


class TestGetNextEntityId:
    def test_fill_gaps_strategy(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_entity_id

        data = [None, {"id": 1, "name": "A"}, {"id": 2, "name": ""}]
        (game_dir / "Actors.json").write_text(json.dumps(data), encoding="utf-8")
        assert get_next_entity_id("game_001", "actor", strategy="fill_gaps") == 2

    def test_append_strategy(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_next_entity_id

        data = [None, {"id": 1, "name": "A"}]
        (game_dir / "Actors.json").write_text(json.dumps(data), encoding="utf-8")
        assert get_next_entity_id("game_001", "actor", strategy="append") == 2


# ── get_system_context ───────────────────────────────────────


class TestGetSystemContext:
    def test_full_context(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_system_context

        system = {
            "gameTitle": "My RPG",
            "currencyUnit": "Gold",
            "elements": ["", "Fire"],
            "startMapId": 2,
            "startX": 5,
            "startY": 10,
            "partyMembers": [1],
        }
        actors = [None, {"id": 1, "name": "Hero"}]
        (game_dir / "System.json").write_text(json.dumps(system), encoding="utf-8")
        (game_dir / "Actors.json").write_text(json.dumps(actors), encoding="utf-8")

        ctx = get_system_context("game_001")
        assert ctx["gameTitle"] == "My RPG"
        assert ctx["hero"]["name"] == "Hero"
        assert ctx["startPosition"]["mapId"] == 2

    def test_missing_files(self, game_dir: Path) -> None:
        from agent.utils.game_data_io import get_system_context

        ctx = get_system_context("game_001")
        assert ctx["gameTitle"] == "알 수 없음"
        assert ctx["hero"]["name"] == "알 수 없음"
