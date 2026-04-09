"""mcp_toolbox 순수 함수 단위 테스트.

외부 서비스(MCP 서버, LLM 등)를 호출하지 않는다.
monkeypatch로 환경변수만 제어해 parse/resolve/sanitize 로직을 검증한다.
"""

from __future__ import annotations

import importlib

import pytest

from agent import mcp_toolbox as mt

# ──────────────────────────────────────────────────────────────
# parse_mcp_servers_json
# ──────────────────────────────────────────────────────────────


class TestParseMcpServersJson:
    """MCP_SERVERS_JSON 환경변수 파싱."""

    def test_single_server(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVERS_JSON", '{"default":{"node_path":"/a.js"}}')
        result = mt.parse_mcp_servers_json()
        assert result == {"default": {"node_path": "/a.js"}}

    def test_multi_server(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "MCP_SERVERS_JSON",
            '{"default":{"node_path":"/a.js"},"maker":{"command":"npx","args":["maker"]}}',
        )
        result = mt.parse_mcp_servers_json()
        assert result is not None
        assert len(result) == 2
        assert "default" in result
        assert "maker" in result

    def test_empty_env_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_SERVERS_JSON", raising=False)
        assert mt.parse_mcp_servers_json() is None

    def test_blank_string_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVERS_JSON", "   ")
        assert mt.parse_mcp_servers_json() is None

    def test_invalid_json_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVERS_JSON", "{{not json}}")
        assert mt.parse_mcp_servers_json() is None

    def test_json_array_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVERS_JSON", "[1, 2, 3]")
        assert mt.parse_mcp_servers_json() is None

    def test_empty_dict_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVERS_JSON", "{}")
        assert mt.parse_mcp_servers_json() is None

    def test_mixed_valid_invalid_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """유효한 항목(dict 값)만 남기고 비-dict 값은 필터링."""
        monkeypatch.setenv(
            "MCP_SERVERS_JSON",
            '{"good":{"node_path":"/a.js"},"bad":"string_value","also_bad":123}',
        )
        result = mt.parse_mcp_servers_json()
        assert result == {"good": {"node_path": "/a.js"}}


# ──────────────────────────────────────────────────────────────
# resolve_mcp_server_key — 엣지 케이스
# ──────────────────────────────────────────────────────────────


class TestResolveMcpServerKeyEdge:
    """resolve_mcp_server_key 엣지 케이스 (기본 우선순위는 test_mcp_server_resolve.py에서 검증)."""

    def test_explicit_whitespace_only_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """explicit_from_map이 공백만이면 None 취급 → tool/file 매핑으로 폴백."""
        monkeypatch.setenv("MCP_SERVER_BY_TOOL_JSON", '{"get_actor":"by_tool"}')
        monkeypatch.delenv("MCP_SERVER_BY_TARGET_FILE_JSON", raising=False)
        result = mt.resolve_mcp_server_key("Actors.json", "get_actor", "   ")
        # 공백만 있으면 strip 후 빈 문자열이므로 falsy → tool lookup으로 폴백
        assert result == "by_tool"

    def test_tool_name_none_skips_tool_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVER_BY_TOOL_JSON", '{"get_actor":"by_tool"}')
        monkeypatch.setenv("MCP_SERVER_BY_TARGET_FILE_JSON", '{"Actors.json":"by_file"}')
        result = mt.resolve_mcp_server_key("Actors.json", None, None)
        assert result == "by_file"

    def test_empty_target_file_skips_file_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_SERVER_BY_TOOL_JSON", raising=False)
        monkeypatch.setenv("MCP_SERVER_BY_TARGET_FILE_JSON", '{"Actors.json":"by_file"}')
        result = mt.resolve_mcp_server_key("", "unknown_tool", None)
        assert result is None

    def test_broken_tool_json_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MCP_SERVER_BY_TOOL_JSON이 깨진 JSON이면 무시하고 file 매핑으로 폴백."""
        monkeypatch.setenv("MCP_SERVER_BY_TOOL_JSON", "not valid json")
        monkeypatch.setenv("MCP_SERVER_BY_TARGET_FILE_JSON", '{"Actors.json":"by_file"}')
        result = mt.resolve_mcp_server_key("Actors.json", "get_actor", None)
        assert result == "by_file"

    def test_file_json_non_string_value_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """값이 문자열이 아니면(int 등) 필터링되어 매칭 안 됨."""
        monkeypatch.delenv("MCP_SERVER_BY_TOOL_JSON", raising=False)
        monkeypatch.setenv("MCP_SERVER_BY_TARGET_FILE_JSON", '{"Actors.json":123}')
        result = mt.resolve_mcp_server_key("Actors.json", "get_actor", None)
        assert result is None

    def test_tool_json_value_whitespace_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_SERVER_BY_TOOL_JSON", '{"get_actor":" maker "}')
        monkeypatch.delenv("MCP_SERVER_BY_TARGET_FILE_JSON", raising=False)
        result = mt.resolve_mcp_server_key("Actors.json", "get_actor", None)
        assert result == "maker"


# ──────────────────────────────────────────────────────────────
# _sanitize_mz_item_effects_for_schema
# ──────────────────────────────────────────────────────────────


class TestSanitizeMzItemEffects:
    """executor의 _sanitize_mz_item_effects_for_schema 테스트."""

    @pytest.fixture(autouse=True)
    def _load_executor(self):
        self.executor_module = importlib.import_module("agent.graph.nodes.executor")

    def test_swap_when_value1_gt_10_and_value2_zero(self) -> None:
        """code=11, value1=500, value2=0 → value1=0, value2=500."""
        effects = [{"code": 11, "value1": 500, "value2": 0}]
        result = self.executor_module._sanitize_mz_item_effects_for_schema(effects)
        assert result[0]["value1"] == 0
        assert result[0]["value2"] == 500

    def test_no_swap_when_value1_low(self) -> None:
        """code=12, value1=5, value2=100 → 변경 없음."""
        effects = [{"code": 12, "value1": 5, "value2": 100}]
        result = self.executor_module._sanitize_mz_item_effects_for_schema(effects)
        assert result[0]["value1"] == 5
        assert result[0]["value2"] == 100

    def test_non_list_returns_empty(self) -> None:
        assert self.executor_module._sanitize_mz_item_effects_for_schema(None) == []
        assert self.executor_module._sanitize_mz_item_effects_for_schema("string") == []

    def test_non_dict_entries_skipped(self) -> None:
        effects = [42, None, "x", {"code": 11, "value1": 0, "value2": 50}]
        result = self.executor_module._sanitize_mz_item_effects_for_schema(effects)
        assert len(result) == 1
        assert result[0]["code"] == 11

    def test_code_not_11_12_no_swap(self) -> None:
        """code=21(상태 부여)은 swap 대상이 아님."""
        effects = [{"code": 21, "value1": 500, "value2": 0}]
        result = self.executor_module._sanitize_mz_item_effects_for_schema(effects)
        assert result[0]["value1"] == 500
        assert result[0]["value2"] == 0

    def test_empty_list(self) -> None:
        assert self.executor_module._sanitize_mz_item_effects_for_schema([]) == []

    def test_value_type_error_fallback(self) -> None:
        """value가 비숫자이면 float 변환 실패 → 0.0으로 폴백, swap 안 함."""
        effects = [{"code": 11, "value1": "abc", "value2": "def"}]
        result = self.executor_module._sanitize_mz_item_effects_for_schema(effects)
        # v1n=0.0, v2n=0.0 → v1n <= 10이므로 swap 안 함
        assert result[0]["value1"] == "abc"
        assert result[0]["value2"] == "def"


# ──────────────────────────────────────────────────────────────
# is_mcp_enabled
# ──────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────
# filter_category_labels (Definition 지칭어 필터링)
# ──────────────────────────────────────────────────────────────


class TestFilterCategoryLabels:
    """definition.filter_category_labels 순수 로직 테스트."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from agent.graph.nodes.definition import filter_category_labels

        self.fn = filter_category_labels

    def test_concrete_only_kept(self) -> None:
        """구체 이름만 있으면 그대로 유지."""
        cls = [{"name": "루시퍼", "category": "actor", "is_category_label": False}]
        assert self.fn(cls) == cls

    def test_label_only_kept(self) -> None:
        """지칭어만 있으면(예: '액터 전부 삭제') 그대로 유지."""
        cls = [{"name": "액터", "category": "actor", "is_category_label": True}]
        assert self.fn(cls) == cls

    def test_concrete_plus_label_removes_label(self) -> None:
        """'루시퍼 액터 추가' → 구체 이름 + 지칭어 → 지칭어 제거."""
        cls = [
            {"name": "루시퍼", "category": "actor", "is_category_label": False},
            {"name": "액터", "category": "actor", "is_category_label": True},
        ]
        result = self.fn(cls)
        assert len(result) == 1
        assert result[0]["name"] == "루시퍼"

    def test_concrete_plus_different_category_label_removes_label(self) -> None:
        """구체 이름(actor) + 다른 카테고리 지칭어(item) → 지칭어 모두 제거."""
        cls = [
            {"name": "루시퍼", "category": "actor", "is_category_label": False},
            {"name": "아이템", "category": "item", "is_category_label": True},
        ]
        result = self.fn(cls)
        assert len(result) == 1
        assert result[0]["name"] == "루시퍼"

    def test_multiple_labels_only_all_kept(self) -> None:
        """지칭어만 여러 개 → 모두 유지."""
        cls = [
            {"name": "액터", "category": "actor", "is_category_label": True},
            {"name": "아이템", "category": "item", "is_category_label": True},
        ]
        assert self.fn(cls) == cls

    def test_multiple_concrete_no_labels(self) -> None:
        """구체 이름 여러 개, 지칭어 없음 → 모두 유지."""
        cls = [
            {"name": "루시퍼", "category": "actor", "is_category_label": False},
            {"name": "포션", "category": "item", "is_category_label": False},
        ]
        assert self.fn(cls) == cls

    def test_empty_list(self) -> None:
        assert self.fn([]) == []


# ──────────────────────────────────────────────────────────────
# is_mcp_enabled
# ──────────────────────────────────────────────────────────────


class TestIsMcpEnabled:
    def test_true_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("1", "true", "True", "YES", " True "):
            monkeypatch.setenv("MCP_ENABLED", val)
            assert mt.is_mcp_enabled() is True, f"MCP_ENABLED={val!r} should be True"

    def test_false_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("", "false", "0", "no"):
            monkeypatch.setenv("MCP_ENABLED", val)
            assert mt.is_mcp_enabled() is False, f"MCP_ENABLED={val!r} should be False"

    def test_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_ENABLED", raising=False)
        assert mt.is_mcp_enabled() is False


# ──────────────────────────────────────────────────────────────
# get_mcp_server_args
# ──────────────────────────────────────────────────────────────


class TestGetMcpServerArgs:
    def test_json_array(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ARGS", '["/a", "/b"]')
        assert mt.get_mcp_server_args() == ["/a", "/b"]

    def test_plain_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ARGS", "/a/b.js")
        assert mt.get_mcp_server_args() == ["/a/b.js"]

    def test_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ARGS", "")
        assert mt.get_mcp_server_args() == []

    def test_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_ARGS", raising=False)
        assert mt.get_mcp_server_args() == []

    def test_invalid_json_array(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ARGS", "[broken")
        assert mt.get_mcp_server_args() == ["[broken"]


# ──────────────────────────────────────────────────────────────
# get_mcp_stdio_env
# ──────────────────────────────────────────────────────────────


class TestGetMcpStdioEnv:
    def test_valid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ENV_JSON", '{"KEY":"VAL"}')
        assert mt.get_mcp_stdio_env() == {"KEY": "VAL"}

    def test_invalid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ENV_JSON", "not json")
        assert mt.get_mcp_stdio_env() == {}

    def test_not_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ENV_JSON", '["a","b"]')
        assert mt.get_mcp_stdio_env() == {}

    def test_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ENV_JSON", "")
        assert mt.get_mcp_stdio_env() == {}


# ──────────────────────────────────────────────────────────────
# _is_path_under_storage_root
# ──────────────────────────────────────────────────────────────


class TestIsPathUnderStorageRoot:
    def test_valid_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        from app.backend.core.config import settings

        storage = tmp_path / "storage" / "games"
        storage.mkdir(parents=True)
        monkeypatch.setattr(settings, "STORAGE_PATH", str(storage))

        candidate = storage / "game_001" / "data"
        candidate.mkdir(parents=True)
        assert mt._is_path_under_storage_root(candidate) is True

    def test_traversal_blocked(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        from app.backend.core.config import settings

        storage = tmp_path / "storage" / "games"
        storage.mkdir(parents=True)
        monkeypatch.setattr(settings, "STORAGE_PATH", str(storage))

        evil = tmp_path / "etc" / "passwd"
        evil.parent.mkdir(parents=True, exist_ok=True)
        evil.touch()
        assert mt._is_path_under_storage_root(evil) is False
