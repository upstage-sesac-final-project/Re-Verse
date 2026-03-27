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
        if action == "add_party_member":
            # Planner step: System.json + update(action_type="update")
            # 여기서는 그 의미를 "partyMembers에 actor 추가"로 해석한다.
            ti = kwargs.get("target_info") if isinstance(kwargs.get("target_info"), dict) else {}
            actor_name = (ti.get("actor_name") or kwargs.get("actor_name") or "").strip()
            return self._handle_add_party_member(actor_name)
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
