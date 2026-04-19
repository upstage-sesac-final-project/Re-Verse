"""MCP 툴 레지스트리 — Phase F 분해 1단계.

executor/core.py 에 있던 정적 MCP_TOOL_MAP 과 map 파일 동적 분기 로직을 분리.
후속 sprint 에서 handler-level 로 이주하면 이 파일은 더 얇아지거나 제거된다.
"""

from __future__ import annotations

import re
from typing import Any

# ────────────────────────────────────────────────────────────
# MCP 툴 매핑 ((target_file, action) → {tool, backup_files})
# ────────────────────────────────────────────────────────────
# 맵 파일(MapNNN.json)은 패턴 매칭이라 이 표에 포함시키지 않고
# `resolve_mcp_map_file_entry` 에서 동적으로 결정한다.
MCP_TOOL_MAP: dict[tuple[str, str], dict[str, Any]] = {
    # Actors.json
    ("Actors.json", "list"): {"tool": "list_actors", "backup_files": []},
    ("Actors.json", "search"): {"tool": "search_actors", "backup_files": []},
    ("Actors.json", "query_by_id"): {"tool": "get_actor", "backup_files": []},
    ("Actors.json", "create"): {"tool": "create_actor", "backup_files": ["Actors.json"]},
    ("Actors.json", "update_actor"): {"tool": "update_actor", "backup_files": ["Actors.json"]},
    # Skills.json
    ("Skills.json", "list"): {"tool": "list_skills", "backup_files": []},
    ("Skills.json", "query"): {"tool": "get_skill", "backup_files": []},
    ("Skills.json", "search"): {"tool": "search_skills", "backup_files": []},
    ("Skills.json", "create"): {"tool": "create_skill", "backup_files": ["Skills.json"]},
    ("Skills.json", "create_damage"): {
        "tool": "create_damage_skill",
        "backup_files": ["Skills.json"],
    },
    ("Skills.json", "create_healing"): {
        "tool": "create_healing_skill",
        "backup_files": ["Skills.json"],
    },
    ("Skills.json", "create_buff"): {"tool": "create_buff_skill", "backup_files": ["Skills.json"]},
    ("Skills.json", "create_state"): {
        "tool": "create_state_skill",
        "backup_files": ["Skills.json"],
    },
    ("Skills.json", "update"): {"tool": "update_skill", "backup_files": ["Skills.json"]},
    # Items.json
    ("Items.json", "list"): {"tool": "list_items", "backup_files": []},
    ("Items.json", "search"): {"tool": "search_items", "backup_files": []},
    ("Items.json", "create"): {"tool": "create_item", "backup_files": ["Items.json"]},
    ("Items.json", "update"): {"tool": "update_item", "backup_files": ["Items.json"]},
    # Weapons.json
    ("Weapons.json", "list"): {"tool": "list_weapons", "backup_files": []},
    ("Weapons.json", "create"): {"tool": "create_weapon", "backup_files": ["Weapons.json"]},
    ("Weapons.json", "update"): {"tool": "update_weapon", "backup_files": ["Weapons.json"]},
    # Armors.json
    ("Armors.json", "list"): {"tool": "list_armors", "backup_files": []},
    ("Armors.json", "create"): {"tool": "create_armor", "backup_files": ["Armors.json"]},
    ("Armors.json", "update"): {"tool": "update_armor", "backup_files": ["Armors.json"]},
    # Classes.json
    ("Classes.json", "list"): {"tool": "list_classes", "backup_files": []},
    ("Classes.json", "create"): {"tool": "create_class", "backup_files": ["Classes.json"]},
    ("Classes.json", "update"): {"tool": "update_class", "backup_files": ["Classes.json"]},
    # States.json
    ("States.json", "list"): {"tool": "list_states", "backup_files": []},
    ("States.json", "create"): {"tool": "create_state", "backup_files": ["States.json"]},
    ("States.json", "update"): {"tool": "update_state", "backup_files": ["States.json"]},
    # Enemies.json
    ("Enemies.json", "list"): {"tool": "list_enemies", "backup_files": []},
    ("Enemies.json", "create"): {"tool": "create_enemy", "backup_files": ["Enemies.json"]},
    ("Enemies.json", "update"): {"tool": "update_enemy", "backup_files": ["Enemies.json"]},
    # System.json
    ("System.json", "query"): {"tool": "get_system", "backup_files": []},
    ("System.json", "list_variables"): {"tool": "get_variables", "backup_files": []},
    ("System.json", "set_variable_name"): {
        "tool": "set_variable_name",
        "backup_files": ["System.json"],
    },
    ("System.json", "list_switches"): {"tool": "get_switches", "backup_files": []},
    ("System.json", "set_switch_name"): {
        "tool": "set_switch_name",
        "backup_files": ["System.json"],
    },
    ("System.json", "get_game_title"): {"tool": "get_game_title", "backup_files": []},
    ("System.json", "update_game_title"): {
        "tool": "update_game_title",
        "backup_files": ["System.json"],
    },
    ("System.json", "update_starting_position"): {
        "tool": "update_starting_position",
        "backup_files": ["System.json"],
    },
    # MapInfos.json
    ("MapInfos.json", "list"): {"tool": "list_maps", "backup_files": ["MapInfos.json"]},
    ("MapInfos.json", "query"): {"tool": "list_maps", "backup_files": ["MapInfos.json"]},
    ("MapInfos.json", "create"): {"tool": "create_map", "backup_files": ["MapInfos.json"]},
}


# ── 맵 파일 (MapNNN.json) ────────────────────────────────────────
_MAP_JSON_FILE_RE = re.compile(r"^Map(\d{1,3})\.json$", re.IGNORECASE)


def parse_map_id_from_target_file(target_file: str) -> int | None:
    m = _MAP_JSON_FILE_RE.match((target_file or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


# Map 파일 action → MCP 툴 이름 매핑 (동적 분기용)
_MAP_TOOL_BY_ACTION: dict[str, str] = {
    "query": "get_map",
    "read": "get_map",
    "update": "update_map",
    "list_events": "get_map_events",
    "search": "search_map_events",
    "search_events": "search_map_events",
    "create_event": "create_map_event",
    "update_event": "update_map_event",
    "add_event_command": "add_event_command",
    "draw_tile": "draw_map_tile",
}


def resolve_mcp_map_file_entry(target_file: str, action: str) -> dict[str, Any] | None:
    """MapNNN.json + action → MCP 툴 엔트리 동적 해결."""
    if parse_map_id_from_target_file(target_file) is None:
        return None
    a = (action or "").strip().lower()
    tool = _MAP_TOOL_BY_ACTION.get(a)
    if not tool:
        return None
    return {"tool": tool, "backup_files": [target_file]}
