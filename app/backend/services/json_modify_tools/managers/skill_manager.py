"""Skill Manager — 스킬 전용 매니저

MVP 버전: 기존 edit_skills.py 로직 래핑 + 기본 템플릿
"""

import copy
import logging
from pathlib import Path
from typing import Any

from .base_manager import BaseManager

logger = logging.getLogger(__name__)


class SkillManager(BaseManager):
    """MVP: 스킬 관리 매니저"""

    def get_file_path(self) -> Path:
        return self.data_path / "Skills.json"

    def __init__(self, data_path, operation_id="mvp"):
        super().__init__(data_path, operation_id)

        # MVP: 기본 스킬 템플릿 (필수 필드만)
        self.DEFAULT_SKILL_TEMPLATE = {
            "id": 0,
            "name": "",
            "description": "",
            "iconIndex": 0,
            "mpCost": 0,
            "tpCost": 0,
            "occasion": 1,  # 배틀에서만
            "scope": 1,  # 단일 적
            "speed": 0,
            "successRate": 100,
            "repeats": 1,
            "tpGain": 0,
            "hitType": 1,
            "animationId": -1,
            "damage": {
                "type": 0,  # 데미지 없음
                "elementId": 0,
                "formula": "0",
                "variance": 0,
                "critical": False,
            },
            "effects": [],
            "requiredWtypeId1": 0,
            "requiredWtypeId2": 0,
            "message1": "",
            "message2": "",
            "note": "",
            "stypeId": 1,  # 기본 스킬 타입
            "messageType": 1,
        }

    async def execute(self, action: str, target_name: str = "", **kwargs) -> dict[str, Any]:
        """MVP: 스킬 실행 (기본 add/update만)"""

        try:
            if action == "add":
                return await self._handle_add(target_name, kwargs)
            elif action == "update":
                return await self._handle_update(target_name, kwargs)
            else:
                return {
                    "success": False,
                    "error": f"MVP에서 지원하지 않는 액션: {action}",
                    "category": "skills",
                }

        except Exception as e:
            logger.error("[%s] 스킬 매니저 에러: %s", self.operation_id, e)
            return {"success": False, "error": str(e), "category": "skills"}

    async def _handle_add(self, skill_name: str, params: dict) -> dict[str, Any]:
        """MVP: 새 스킬 추가"""

        # 데이터 로드
        skills_data = self.load_json_data()

        # 중복 체크 (MVP: 간단한 체크)
        existing_id = self.find_by_name(skills_data, skill_name)
        if existing_id:
            return {
                "success": False,
                "error": f"스킬 '{skill_name}' 이미 존재 (ID: {existing_id})",
                "category": "skills",
            }

        # 새 ID 할당
        new_id = self.find_available_id(skills_data)

        # 템플릿 복사 및 수정
        new_skill = copy.deepcopy(self.DEFAULT_SKILL_TEMPLATE)
        new_skill["id"] = new_id
        new_skill["name"] = skill_name

        # MVP: 기본 파라미터만 적용
        if "mpCost" in params:
            new_skill["mpCost"] = int(params["mpCost"])
        if "description" in params:
            new_skill["description"] = params["description"]

        # 배열에 추가
        if new_id == len(skills_data):
            skills_data.append(new_skill)
        else:
            skills_data[new_id] = new_skill

        # 저장
        self.save_json_data(skills_data)

        return {
            "success": True,
            "action": "add",
            "target_name": skill_name,
            "target_id": new_id,
            "modified_files": ["Skills.json"],
            "message": f"스킬 '{skill_name}' 추가됨 (ID: {new_id})",
        }

    async def _handle_update(self, skill_name: str, params: dict) -> dict[str, Any]:
        """MVP: 기존 스킬 수정"""

        # 데이터 로드
        skills_data = self.load_json_data()

        # 대상 찾기
        target_id = self.find_by_name(skills_data, skill_name)
        if target_id is None:
            available_names = [
                s.get("name") for s in skills_data[1:] if isinstance(s, dict) and s.get("name")
            ]
            return {
                "success": False,
                "error": f"스킬 '{skill_name}' 없음",
                "available": available_names[:10],  # 처음 10개만
                "category": "skills",
            }

        # 기존 스킬 수정
        target_skill = skills_data[target_id]

        # MVP: 기본 필드만 수정
        if "mpCost" in params:
            target_skill["mpCost"] = int(params["mpCost"])
        if "description" in params:
            target_skill["description"] = params["description"]
        if "scope" in params:
            target_skill["scope"] = int(params["scope"])

        # 저장
        self.save_json_data(skills_data)

        return {
            "success": True,
            "action": "update",
            "target_name": skill_name,
            "target_id": target_id,
            "modified_files": ["Skills.json"],
            "message": f"스킬 '{skill_name}' 수정됨 (ID: {target_id})",
        }
