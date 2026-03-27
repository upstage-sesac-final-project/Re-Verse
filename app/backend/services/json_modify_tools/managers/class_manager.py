"""Class Manager — Classes.json 전용 (구조화 execution_plan용 MVP)."""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Any

from .base_manager import BaseManager


class ClassManager(BaseManager):
    def get_file_path(self) -> Path:
        return self.data_path / "Classes.json"

    async def execute(self, action: str, **kwargs) -> dict[str, Any]:
        # Structured step에서 넘어오는 값을 기반으로 query/create를 분기한다.
        class_name = (kwargs.get("class_name") or "").strip()
        if not class_name:
            ti = kwargs.get("target_info")
            if isinstance(ti, dict):
                class_name = (ti.get("class_name") or ti.get("name") or "").strip()
        if not class_name:
            return {
                "success": False,
                "error": "class_name(또는 target_info.class_name)이 비어 있습니다.",
                "category": "classes",
            }

        if action == "query":
            return self._handle_query(class_name)
        if action == "create":
            return self._handle_create(class_name)
        return {
            "success": False,
            "error": f"MVP에서 지원하지 않는 액션: {action}",
            "category": "classes",
        }

    def _handle_query(self, class_name: str) -> dict[str, Any]:
        # Classes.json 역시 RPG Maker 규칙상 [null, {...}, {...}] 구조를 기대한다.
        data = self.load_json_data()
        if not isinstance(data, list) or not data or data[0] is not None:
            return {
                "success": False,
                "error": "Classes.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                "category": "classes",
            }
        idx = self.find_by_name(data, class_name)
        return {
            "success": True,
            "action": "query",
            "exists": idx is not None,
            "class_id": idx,
            "class_name": class_name,
            "message": (
                f"클래스 '{class_name}' 존재 (id={idx})"
                if idx is not None
                else f"클래스 '{class_name}' 없음"
            ),
            "category": "classes",
        }

    def _handle_create(self, class_name: str) -> dict[str, Any]:
        # MVP는 "없는 경우에만" 클래스를 생성한다. (있으면 error/exists 반환)
        data = self.load_json_data()
        if not isinstance(data, list) or not data or data[0] is not None:
            return {
                "success": False,
                "error": "Classes.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                "category": "classes",
            }
        if self.find_by_name(data, class_name):
            return {
                "success": False,
                "exists": True,
                "error": f"클래스 '{class_name}' 이미 존재합니다.",
                "category": "classes",
            }

        # 템플릿 선택 규칙:
        # - id==1(보통 기본값) 우선
        # - 없으면 첫 유효 dict
        template = None
        if len(data) > 1 and isinstance(data[1], dict):
            template = data[1]
        if template is None:
            for idx in range(1, len(data)):
                if isinstance(data[idx], dict):
                    template = data[idx]
                    break
        if template is None:
            return {
                "success": False,
                "error": "템플릿 클래스를 찾을 수 없습니다.",
                "category": "classes",
            }

        new_id = self.find_available_id(data)
        new_class = copy.deepcopy(template)
        new_class["id"] = new_id
        new_class["name"] = class_name
        note_tag = f"[AI_MODIFIED:{datetime.now().strftime('%Y-%m-%d')}]"
        new_class["note"] = (new_class.get("note") or "").strip()
        new_class["note"] = f"{new_class['note']} {note_tag}".strip()

        if new_id == len(data):
            data.append(new_class)
        else:
            data[new_id] = new_class
        self.save_json_data(data)
        return {
            "success": True,
            "action": "create",
            "class_id": new_id,
            "class_name": class_name,
            "modified_files": ["Classes.json"],
            "message": f"클래스 '{class_name}' 생성됨 (id={new_id})",
            "category": "classes",
        }
