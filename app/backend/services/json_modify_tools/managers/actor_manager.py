"""Actor Manager — Actors.json 전용 (3단계 구조화 execution_plan용 MVP)"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .base_manager import BaseManager

logger = logging.getLogger(__name__)


class ActorManager(BaseManager):
    """MVP: 액터 조회(query) / 신규 생성(create). 파일명은 RPG MZ 규칙상 Actors.json."""

    def get_file_path(self) -> Path:
        return self.data_path / "Actors.json"

    async def execute(self, action: str, **kwargs) -> dict[str, Any]:
        actor_name = (kwargs.get("actor_name") or "").strip()
        if not actor_name:
            ti = kwargs.get("target_info")
            if isinstance(ti, dict):
                actor_name = (ti.get("actor_name") or ti.get("name") or "").strip()
        if not actor_name:
            return {
                "success": False,
                "error": "actor_name(또는 target_info.actor_name)이 비어 있습니다.",
                "category": "actors",
            }

        try:
            if action == "query":
                return self._handle_query(actor_name)
            if action == "create":
                template_class_id = int(kwargs.get("class_id", 1))
                return self._handle_create(actor_name, template_class_id)
            return {
                "success": False,
                "error": f"MVP에서 지원하지 않는 액션: {action}",
                "category": "actors",
            }
        except Exception as e:
            logger.error("[%s] ActorManager 오류: %s", self.operation_id, e)
            return {"success": False, "error": str(e), "category": "actors"}

    def _handle_query(self, actor_name: str) -> dict[str, Any]:
        data = self.load_json_data()
        if not isinstance(data, list) or not data or data[0] is not None:
            return {
                "success": False,
                "error": "Actors.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                "category": "actors",
            }

        idx = self.find_by_name(data, actor_name)
        exists = idx is not None
        return {
            "success": True,
            "action": "query",
            "exists": exists,
            "actor_id": idx,
            "actor_name": actor_name,
            "message": (
                f"액터 '{actor_name}' 존재 (id={idx})" if exists else f"액터 '{actor_name}' 없음"
            ),
            "category": "actors",
        }

    def _handle_create(self, actor_name: str, template_class_id: int) -> dict[str, Any]:
        data = self.load_json_data()
        if not isinstance(data, list) or not data or data[0] is not None:
            return {
                "success": False,
                "error": "Actors.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                "category": "actors",
            }

        if self.find_by_name(data, actor_name):
            return {
                "success": False,
                "exists": True,
                "error": f"액터 '{actor_name}' 이미 존재합니다.",
                "category": "actors",
            }

        template = self._pick_template_actor(data, template_class_id)
        if template is None:
            return {
                "success": False,
                "error": "템플릿 액터를 찾을 수 없습니다.",
                "category": "actors",
            }

        new_id = self.find_available_id(data)
        new_actor = copy.deepcopy(template)
        new_actor["id"] = new_id
        new_actor["name"] = actor_name
        new_actor["nickname"] = ""
        new_actor["profile"] = ""
        note_tag = f"[AI_MODIFIED:{datetime.now().strftime('%Y-%m-%d')}]"
        new_actor["note"] = (new_actor.get("note") or "").strip()
        if new_actor["note"]:
            new_actor["note"] = f"{new_actor['note']} {note_tag}"
        else:
            new_actor["note"] = note_tag

        if new_id == len(data):
            data.append(new_actor)
        else:
            data[new_id] = new_actor

        self.save_json_data(data)
        return {
            "success": True,
            "action": "create",
            "actor_id": new_id,
            "actor_name": actor_name,
            "modified_files": ["Actors.json"],
            "message": f"액터 '{actor_name}' 생성됨 (id={new_id})",
            "category": "actors",
        }

    def _pick_template_actor(self, data: list[Any], class_id: int) -> dict[str, Any] | None:
        """동일 classId 우선, 없으면 id==1 액터, 그것도 없으면 첫 유효 dict."""
        for idx in range(1, len(data)):
            item = data[idx]
            if isinstance(item, dict) and int(item.get("classId") or 0) == class_id:
                return item
        if len(data) > 1 and isinstance(data[1], dict):
            return data[1]
        for idx in range(1, len(data)):
            if isinstance(data[idx], dict):
                return data[idx]
        return None
