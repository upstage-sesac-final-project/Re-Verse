"""Base Manager — 모든 매니저의 공통 기능

MVP 버전: 기본적인 파일 I/O와 템플릿 메소드 패턴
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BaseManager:
    """MVP: 모든 카테고리 매니저의 베이스 클래스"""

    def __init__(self, data_path: Path, operation_id: str = "mvp"):
        self.data_path = data_path
        self.operation_id = operation_id
        self.category = self.__class__.__name__.replace("Manager", "").lower()

    def get_file_path(self) -> Path:
        """카테고리별 파일 경로"""
        return self.data_path / f"{self.category.title()}.json"

    def load_json_data(self) -> Any:
        """JSON 파일 로드"""
        file_path = self.get_file_path()

        if not file_path.exists():
            raise FileNotFoundError(f"{self.category} 파일 없음: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    def save_json_data(self, data: Any) -> None:
        """JSON 파일 저장 (MVP: 동기 방식)"""
        file_path = self.get_file_path()

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        logger.info("[%s] %s 저장 완료", self.operation_id, file_path.name)

    def find_by_name(self, data: list, name: str) -> int | None:
        """이름으로 ID 검색 (정규화)"""
        if not name or not isinstance(data, list):
            return None

        normalized_target = name.replace(" ", "").lower()

        for idx in range(1, len(data)):  # RPG MZ: 0번은 null
            item = data[idx]
            if isinstance(item, dict) and item.get("name"):
                normalized_item = item["name"].replace(" ", "").lower()
                if normalized_item == normalized_target:
                    return idx

        return None

    def find_available_id(self, data: list) -> int:
        """새 항목용 빈 ID 찾기"""
        # 1) null 슬롯 우선 검색
        for idx in range(1, len(data)):
            if data[idx] is None:
                return idx

        # 2) 빈 이름 슬롯 검색
        for idx in range(1, len(data)):
            item = data[idx]
            if isinstance(item, dict) and not item.get("name"):
                return idx

        # 3) 마지막에 추가
        return len(data)

    # 서브클래스에서 구현할 메소드들
    async def execute(self, action: str, **kwargs) -> dict[str, Any]:
        """서브클래스에서 구현"""
        raise NotImplementedError(f"{self.__class__.__name__}.execute() 미구현")
