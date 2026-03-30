"""Actor Manager — Actors.json 전용 (3단계 구조화 execution_plan용 MVP)"""

from __future__ import annotations

import copy
import json
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
            # Structured step의 action_type을 여기서는 "MVP 매니저 action"으로 매핑한다.
            # - Planner step: Actors.json + (query/create/update)
            # - 여기서 실제 호출: execute("query"/"create"/"update_class")
            if action == "query":
                return self._handle_query(actor_name)
            if action == "create":
                template_class_id = int(kwargs.get("class_id", 1))
                return self._handle_create(actor_name, template_class_id)
            if action == "update_class":
                ti = (
                    kwargs.get("target_info") if isinstance(kwargs.get("target_info"), dict) else {}
                )
                class_name = (ti.get("class_name") or kwargs.get("class_name") or "").strip()
                class_id_raw = ti.get("class_id", kwargs.get("class_id"))
                class_id: int | None = None
                if class_id_raw is not None:
                    try:
                        class_id = int(class_id_raw)
                    except (TypeError, ValueError):
                        class_id = None
                return self._handle_update_class(actor_name, class_name, class_id)
            return {
                "success": False,
                "error": f"MVP에서 지원하지 않는 액션: {action}",
                "category": "actors",
            }
        except Exception as e:
            logger.error("[%s] ActorManager 오류: %s", self.operation_id, e)
            return {"success": False, "error": str(e), "category": "actors"}

    def _handle_query(self, actor_name: str) -> dict[str, Any]:
        # RPG Maker MZ Actors.json은 배열이며, 0번 인덱스는 null로 고정되어 있다.
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
        # MVP에서는 "없을 때만 create"하도록 설계한다.
        # 이미 존재하면 create를 진행하지 않고 success=False로 반환한다.
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
        # 생성/수정된 항목임을 추적하기 위해 note에 태그를 남긴다.
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
        """동일 classId 우선으로 템플릿을 고른다.

        - 같은 classId가 있으면 그 액터를 복사
        - 없으면 id==1 액터(기본값으로 자주 존재)를 복사
        - 그것도 없으면 첫 유효 dict를 복사(마지막 수단)
        """
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

    def _handle_update_class(
        self,
        actor_name: str,
        class_name: str,
        class_id: int | None,
    ) -> dict[str, Any]:
        """액터의 `classId`를 갱신한다.

        MVP 제약:
        - class_id가 들어오면 바로 사용
        - 없으면 `Classes.json`에서 class_name으로 classId를 resolve한 뒤 갱신
        """
        actors_data = self.load_json_data()
        if not isinstance(actors_data, list) or not actors_data or actors_data[0] is not None:
            return {
                "success": False,
                "error": "Actors.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                "category": "actors",
            }

        actor_id = self.find_by_name(actors_data, actor_name)
        if actor_id is None:
            return {
                "success": False,
                "error": f"액터 '{actor_name}' 없음",
                "category": "actors",
            }

        resolved_class_id = class_id
        if resolved_class_id is None:
            # Planner step이 `class_id` 없이 `class_name`만 줄 수도 있어서
            # 여기서 Classes.json을 직접 읽어 resolve한다.
            classes_path = self.data_path / "Classes.json"
            if not classes_path.exists():
                return {
                    "success": False,
                    "error": "Classes.json 파일 없음",
                    "category": "actors",
                }
            with open(classes_path, encoding="utf-8") as f:
                classes_data = json.load(f)
            if (
                not isinstance(classes_data, list)
                or not classes_data
                or classes_data[0] is not None
            ):
                return {
                    "success": False,
                    "error": "Classes.json 형식이 예상과 다릅니다 ([null, ...] 필요).",
                    "category": "actors",
                }
            if not class_name:
                return {
                    "success": False,
                    "error": "class_name 또는 class_id가 필요합니다.",
                    "category": "actors",
                }
            class_idx = self.find_by_name(classes_data, class_name)
            if class_idx is None:
                return {
                    "success": False,
                    "error": f"클래스 '{class_name}' 없음",
                    "category": "actors",
                }
            resolved_class_id = class_idx

        target = actors_data[actor_id]
        if not isinstance(target, dict):
            return {
                "success": False,
                "error": f"액터 ID {actor_id} 형식이 올바르지 않습니다.",
                "category": "actors",
            }

        target["classId"] = int(resolved_class_id)
        self.save_json_data(actors_data)
        return {
            "success": True,
            "action": "update_class",
            "actor_id": actor_id,
            "actor_name": actor_name,
            "class_id": int(resolved_class_id),
            "modified_files": ["Actors.json"],
            "message": f"액터 '{actor_name}' classId를 {int(resolved_class_id)}로 수정",
            "category": "actors",
        }
