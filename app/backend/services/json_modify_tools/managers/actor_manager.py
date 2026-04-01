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
        # Executor 구조화 스텝 / MCP 폴백: ID·필드 단위 일반 수정 (update_actor와 동일 역할의 레거시)
        if action == "update_general":
            ti = kwargs.get("target_info", {})
            if isinstance(ti, dict):
                actor_id = ti.get("actor_id") or ti.get("actorId")
                updates = ti.get("updates")
                if actor_id is None:
                    return {
                        "success": False,
                        "error": "update_general에는 actor_id가 필요합니다.",
                        "category": "actors",
                    }
                if not isinstance(updates, dict):
                    return {
                        "success": False,
                        "error": "update_general에는 updates dict가 필요합니다.",
                        "category": "actors",
                    }
                return self._handle_update_general(actor_id, updates)

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

    def _handle_update_general(self, actor_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Actors.json에서 actor_id 인덱스 행의 허용 필드만 갱신한다.

        RPG MZ Actors 배열 규칙(0번 null)을 따르며, 지정 키만 타입에 맞게 덮어쓴다.
        """
        try:
            actor_id = int(actor_id)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": f"잘못된 actor_id: {actor_id}",
                "category": "actors",
            }

        data = self.load_json_data()
        if not isinstance(data, list) or actor_id < 1 or actor_id >= len(data):
            return {
                "success": False,
                "error": f"actor_id {actor_id}는 유효하지 않습니다.",
                "category": "actors",
            }

        actor = data[actor_id]
        if actor is None:
            return {
                "success": False,
                "error": f"actor_id {actor_id}에 액터가 없습니다.",
                "category": "actors",
            }

        # RPG MZ 액터 객체에서 안전하게 손댈 수 있는 키만 허용 (나머지는 무시)
        updatable_fields = {
            "name": str,
            "nickname": str,
            "profile": str,
            "classId": int,
            "characterName": str,
            "characterIndex": int,
            "faceName": str,
            "faceIndex": int,
            "initialLevel": int,
            "expParams": list,
            "params": list,
        }

        updated_fields = []
        original_values = {}

        for field, value in updates.items():
            if field not in updatable_fields:
                logger.warning("[%s] 지원하지 않는 필드 무시: %s", self.operation_id, field)
                continue

            expected_type = updatable_fields[field]
            original_values[field] = actor.get(field)

            try:
                # 타입 변환
                if expected_type is int:
                    actor[field] = int(value)
                elif expected_type is str:
                    actor[field] = str(value)
                elif expected_type is list:
                    if isinstance(value, list):
                        actor[field] = value
                    else:
                        logger.warning("[%s] 리스트가 아닌 값은 무시: %s", self.operation_id, field)
                        continue
                else:
                    actor[field] = value

                updated_fields.append(field)
            except (TypeError, ValueError) as e:
                logger.warning("[%s] 필드 %s 변환 실패: %s", self.operation_id, field, e)
                continue

        if not updated_fields:
            return {
                "success": False,
                "error": "업데이트할 유효한 필드가 없습니다.",
                "category": "actors",
            }

        # 파일 저장
        self.save_json_data(data)

        return {
            "success": True,
            "action": "update_general",
            "actor_id": actor_id,
            "updated_fields": updated_fields,
            "original_values": original_values,
            "message": f"액터 {actor_id}의 {len(updated_fields)}개 속성을 업데이트했습니다: {', '.join(updated_fields)}",
            "modified_files": ["Actors.json"],
            "category": "actors",
        }
