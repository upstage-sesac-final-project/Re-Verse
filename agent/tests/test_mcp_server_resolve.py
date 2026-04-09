"""resolve_mcp_server_key 우선순위."""

from __future__ import annotations

import pytest

from agent import mcp_toolbox as mt


def test_resolve_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MCP_SERVER_BY_TOOL_JSON",
        '{"get_actor":"wrong"}',
    )
    monkeypatch.setenv(
        "MCP_SERVER_BY_TARGET_FILE_JSON",
        '{"Actors.json":"also_wrong"}',
    )
    assert mt.resolve_mcp_server_key("Actors.json", "get_actor", "default") == "default"


def test_tool_over_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MCP_SERVER_BY_TOOL_JSON",
        '{"get_actor":"by_tool"}',
    )
    monkeypatch.setenv(
        "MCP_SERVER_BY_TARGET_FILE_JSON",
        '{"Actors.json":"by_file"}',
    )
    assert mt.resolve_mcp_server_key("Actors.json", "get_actor", None) == "by_tool"


def test_file_when_no_tool_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_SERVER_BY_TOOL_JSON", raising=False)
    monkeypatch.setenv(
        "MCP_SERVER_BY_TARGET_FILE_JSON",
        '{"System.json":"rpgmaker_underscore"}',
    )
    assert mt.resolve_mcp_server_key("System.json", "get_system", None) == "rpgmaker_underscore"


def test_none_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_SERVER_BY_TOOL_JSON", raising=False)
    monkeypatch.delenv("MCP_SERVER_BY_TARGET_FILE_JSON", raising=False)
    assert mt.resolve_mcp_server_key("Actors.json", "get_actors", None) is None
