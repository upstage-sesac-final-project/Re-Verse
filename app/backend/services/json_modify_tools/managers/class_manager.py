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
        # update는 class_id+updates만 사용 (이름 없이 호출됨 — Executor 구조화·MCP 폴백)
        if action == "update":
            ti = kwargs.get("target_info", {})
            if isinstance(ti, dict):
                class_id = ti.get("class_id") or ti.get("classId")
                updates = ti.get("updates")
                if class_id is not None and isinstance(updates, dict):
                    return self._handle_update_general(class_id, updates)
            return {
                "success": False,
                "error": "update 액션에는 target_info에 class_id와 updates가 필요합니다.",
                "category": "classes",
            }

        # query / create: 클래스 이름 기반
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

    def _handle_update_general(self, class_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Classes.json에서 class_id 인덱스 행의 허용 필드만 갱신한다 (이름 기반 create/query와 별개)."""
        try:
            class_id = int(class_id)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": f"잘못된 class_id: {class_id}",
                "category": "classes",
            }

        data = self.load_json_data()
        if not isinstance(data, list) or class_id < 1 or class_id >= len(data):
            return {
                "success": False,
                "error": f"class_id {class_id}는 유효하지 않습니다.",
                "category": "classes",
            }

        class_obj = data[class_id]
        if class_obj is None:
            return {
                "success": False,
                "error": f"class_id {class_id}에 클래스가 없습니다.",
                "category": "classes",
            }

        # 허용 키만 반영 (미지정 필드는 건너뜀)
        updatable_fields = {
            "name": str,
            "params": list,
            "expParams": list,
            "learnings": list,
            "characterName": str,
            "characterIndex": int,
            "faceName": str,
            "faceIndex": int,
            "note": str,
        }

        updated_fields = []
        original_values = {}

        for field, value in updates.items():
            if field not in updatable_fields:
                continue

            expected_type = updatable_fields[field]
            original_values[field] = class_obj.get(field)

            try:
                if expected_type is int:
                    class_obj[field] = int(value)
                elif expected_type is str:
                    class_obj[field] = str(value)
                elif expected_type is list:
                    if isinstance(value, list):
                        class_obj[field] = value
                else:
                    class_obj[field] = value

                updated_fields.append(field)
            except (TypeError, ValueError):
                continue

        if not updated_fields:
            return {
                "success": False,
                "error": "업데이트할 유효한 필드가 없습니다.",
                "category": "classes",
            }

        self.save_json_data(data)

        return {
            "success": True,
            "action": "update_general",
            "class_id": class_id,
            "updated_fields": updated_fields,
            "message": f"클래스 {class_id}의 {len(updated_fields)}개 속성을 업데이트했습니다: {', '.join(updated_fields)}",
            "modified_files": ["Classes.json"],
            "category": "classes",
        }
