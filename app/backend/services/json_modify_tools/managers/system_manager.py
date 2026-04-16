"""System Manager — System.json 전용 (구조화 execution_plan용 MVP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base_manager import BaseManager


class SystemManager(BaseManager):
    def get_file_path(self) -> Path:
        return self.data_path / "System.json"

    async def execute(self, action: str, **kwargs) -> dict[str, Any]:
        # 구조화 플랜은 target_info에 snake_case/camelCase 혼용 가능
        ti = kwargs.get("target_info") if isinstance(kwargs.get("target_info"), dict) else {}

        if action == "add_party_member":
            # Planner step: System.json + update(action_type="update")
            # 여기서는 그 의미를 "partyMembers에 actor 추가"로 해석한다.
            actor_name = (ti.get("actor_name") or kwargs.get("actor_name") or "").strip()
            return self._handle_add_party_member(actor_name)
        if action == "remove_party_member":
            actor_name = (ti.get("actor_name") or kwargs.get("actor_name") or "").strip()
            actor_id = ti.get("actor_id")
            return self._handle_remove_party_member(actor_name, actor_id)
        # 아래 네 액션은 MCP(System.json 툴)와 동일 의미 — MCP 비활성/실패 시 레거시로 수행
        if action == "update_game_title":
            title = ti.get("title") or ti.get("game_title")
            return self._handle_update_game_title(title)
        if action == "set_variable_name":
            variable_id = ti.get("variable_id") or ti.get("variableId")
            name = ti.get("name")
            return self._handle_set_variable_name(variable_id, name)
        if action == "set_switch_name":
            switch_id = ti.get("switch_id") or ti.get("switchId")
            name = ti.get("name")
            return self._handle_set_switch_name(switch_id, name)
        if action == "update_starting_position":
            map_id = ti.get("map_id") or ti.get("mapId")
            x = ti.get("x")
            y = ti.get("y")
            return self._handle_update_starting_position(map_id, x, y)
        return {
            "success": False,
            "error": f"MVP에서 지원하지 않는 액션: {action}",
            "category": "system",
        }

    def _handle_add_party_member(self, actor_name: str) -> dict[str, Any]:
        # partyMembers에는 "actorId" 목록이 들어가므로,
        # actor_name을 Actors.json에서 actorId로 resolve한 뒤 System.json에 반영한다.
        if not actor_name:
            return {
                "success": False,
                "error": "actor_name이 비어 있습니다.",
                "category": "system",
            }

        system = self.load_json_data()
        if not isinstance(system, dict):
            return {
                "success": False,
                "error": "System.json 형식이 예상과 다릅니다 (object 필요).",
                "category": "system",
            }

        actors_path = self.data_path / "Actors.json"
        if not actors_path.exists():
            return {"success": False, "error": "Actors.json 파일 없음", "category": "system"}
        with open(actors_path, encoding="utf-8") as f:
            actors = json.load(f)
        if not isinstance(actors, list) or not actors or actors[0] is not None:
            return {
                "success": False,
                "error": "Actors.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                "category": "system",
            }

        actor_id = self.find_by_name(actors, actor_name)
        if actor_id is None:
            return {
                "success": False,
                "error": f"액터 '{actor_name}' 없음",
                "category": "system",
            }

        party = system.get("partyMembers")
        if not isinstance(party, list):
            return {
                "success": False,
                "error": "System.partyMembers 형식 오류",
                "category": "system",
            }

        if actor_id in party:
            # 동일 actorId가 이미 있으면 idempotent(멱등)하게 skip 처리한다.
            return {
                "success": True,
                "action": "add_party_member",
                "skipped": True,
                "actor_id": actor_id,
                "message": f"액터 '{actor_name}'(id={actor_id})는 이미 partyMembers에 존재",
                "modified_files": [],
                "category": "system",
            }

        party.append(actor_id)
        self.save_json_data(system)
        return {
            "success": True,
            "action": "add_party_member",
            "actor_id": actor_id,
            "actor_name": actor_name,
            "message": f"액터 '{actor_name}'(id={actor_id})를 partyMembers에 추가",
            "modified_files": ["System.json"],
            "category": "system",
        }

    def _handle_remove_party_member(
        self, actor_name: str, actor_id: int | None = None
    ) -> dict[str, Any]:
        """partyMembers 에서 지정 액터를 제거."""
        system = self.load_json_data()
        if not isinstance(system, dict):
            return {
                "success": False,
                "error": "System.json 형식이 예상과 다릅니다.",
                "category": "system",
            }
        party = system.get("partyMembers")
        if not isinstance(party, list):
            return {
                "success": False,
                "error": "System.partyMembers 형식 오류",
                "category": "system",
            }

        # id 우선, 없으면 이름으로 조회
        if actor_id is None and actor_name:
            actors_path = self.data_path / "Actors.json"
            if actors_path.exists():
                with open(actors_path, encoding="utf-8") as f:
                    actors = json.load(f)
                if isinstance(actors, list):
                    actor_id = self.find_by_name(actors, actor_name)

        try:
            actor_id_int = int(actor_id) if actor_id is not None else None
        except (TypeError, ValueError):
            actor_id_int = None

        if actor_id_int is None:
            return {
                "success": False,
                "error": f"액터 '{actor_name}' 를 찾지 못해 partyMembers 에서 제거할 수 없습니다.",
                "category": "system",
            }

        if actor_id_int not in party:
            return {
                "success": True,
                "action": "remove_party_member",
                "skipped": True,
                "actor_id": actor_id_int,
                "message": f"액터 '{actor_name}'(id={actor_id_int}) 는 이미 partyMembers 에 없습니다.",
                "modified_files": [],
                "category": "system",
            }

        system["partyMembers"] = [aid for aid in party if aid != actor_id_int]
        self.save_json_data(system)
        return {
            "success": True,
            "action": "remove_party_member",
            "actor_id": actor_id_int,
            "actor_name": actor_name,
            "message": f"액터 '{actor_name}'(id={actor_id_int}) 를 partyMembers 에서 제거했습니다.",
            "modified_files": ["System.json"],
            "category": "system",
        }

    def _handle_update_game_title(self, title: str) -> dict[str, Any]:
        """System.gameTitle 갱신 (MCP update_game_title 대응)."""
        if not title:
            return {
                "success": False,
                "error": "게임 타이틀이 비어있습니다.",
                "category": "system",
            }

        system = self.load_json_data()
        if not isinstance(system, dict):
            return {
                "success": False,
                "error": "System.json 형식이 예상과 다릅니다.",
                "category": "system",
            }

        old_title = system.get("gameTitle", "")
        system["gameTitle"] = str(title)
        self.save_json_data(system)

        return {
            "success": True,
            "action": "update_game_title",
            "old_title": old_title,
            "new_title": title,
            "message": f"게임 타이틀을 '{old_title}' → '{title}'로 변경했습니다.",
            "modified_files": ["System.json"],
            "category": "system",
        }

    def _handle_set_variable_name(self, variable_id: int, name: str) -> dict[str, Any]:
        """variables[variable_id]에 표시 이름 저장; 부족하면 배열 확장 (MCP set_variable_name 대응)."""
        try:
            variable_id = int(variable_id)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": f"잘못된 variable_id: {variable_id}",
                "category": "system",
            }

        if not name:
            return {
                "success": False,
                "error": "변수 이름이 비어있습니다.",
                "category": "system",
            }

        system = self.load_json_data()
        if not isinstance(system, dict):
            return {
                "success": False,
                "error": "System.json 형식이 예상과 다릅니다.",
                "category": "system",
            }

        variables = system.get("variables", [])
        if not isinstance(variables, list):
            variables = []
            system["variables"] = variables

        # MZ는 인덱스=변수 ID; 짧으면 빈 문자열로 패딩
        while len(variables) <= variable_id:
            variables.append("")

        old_name = variables[variable_id]
        variables[variable_id] = str(name)
        self.save_json_data(system)

        return {
            "success": True,
            "action": "set_variable_name",
            "variable_id": variable_id,
            "old_name": old_name,
            "new_name": name,
            "message": f"변수 {variable_id} 이름을 '{old_name}' → '{name}'로 설정했습니다.",
            "modified_files": ["System.json"],
            "category": "system",
        }

    def _handle_set_switch_name(self, switch_id: int, name: str) -> dict[str, Any]:
        """switches[switch_id]에 표시 이름 저장; 부족하면 배열 확장 (MCP set_switch_name 대응)."""
        try:
            switch_id = int(switch_id)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": f"잘못된 switch_id: {switch_id}",
                "category": "system",
            }

        if not name:
            return {
                "success": False,
                "error": "스위치 이름이 비어있습니다.",
                "category": "system",
            }

        system = self.load_json_data()
        if not isinstance(system, dict):
            return {
                "success": False,
                "error": "System.json 형식이 예상과 다릅니다.",
                "category": "system",
            }

        switches = system.get("switches", [])
        if not isinstance(switches, list):
            switches = []
            system["switches"] = switches

        while len(switches) <= switch_id:
            switches.append("")

        old_name = switches[switch_id]
        switches[switch_id] = str(name)
        self.save_json_data(system)

        return {
            "success": True,
            "action": "set_switch_name",
            "switch_id": switch_id,
            "old_name": old_name,
            "new_name": name,
            "message": f"스위치 {switch_id} 이름을 '{old_name}' → '{name}'로 설정했습니다.",
            "modified_files": ["System.json"],
            "category": "system",
        }

    def _handle_update_starting_position(self, map_id: int, x: int, y: int) -> dict[str, Any]:
        """startMapId / startX / startY 설정 (MCP update_starting_position 대응)."""
        try:
            map_id = int(map_id)
            x = int(x)
            y = int(y)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": "map_id, x, y는 모두 정수여야 합니다.",
                "category": "system",
            }

        system = self.load_json_data()
        if not isinstance(system, dict):
            return {
                "success": False,
                "error": "System.json 형식이 예상과 다릅니다.",
                "category": "system",
            }

        old_map = system.get("startMapId", 1)
        old_x = system.get("startX", 0)
        old_y = system.get("startY", 0)

        system["startMapId"] = map_id
        system["startX"] = x
        system["startY"] = y
        self.save_json_data(system)

        return {
            "success": True,
            "action": "update_starting_position",
            "old_position": {"map": old_map, "x": old_x, "y": old_y},
            "new_position": {"map": map_id, "x": x, "y": y},
            "message": f"시작 위치를 맵 {old_map}({old_x},{old_y}) → 맵 {map_id}({x},{y})로 변경했습니다.",
            "modified_files": ["System.json"],
            "category": "system",
        }
