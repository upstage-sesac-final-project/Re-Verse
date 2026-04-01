import json
import logging
import os
from typing import Any

# 백엔드 설정 로드 시도 (호환성 유지)
try:
    from app.backend.core.config import settings

    STORAGE_PATH = settings.STORAGE_PATH
except (ImportError, ModuleNotFoundError):
    # 백엔드 환경이 아닐 경우(예: 독립 에이전트 테스트) 기본값 사용
    STORAGE_PATH = os.path.join("storage", "games")

logger = logging.getLogger(__name__)

# RPG Maker MZ 카테고리 매핑
CATEGORY_TO_PLURAL = {
    "actor": "Actors",
    "enemy": "Enemies",
    "item": "Items",
    "skill": "Skills",
    "weapon": "Weapons",
    "armor": "Armors",
    "class": "Classes",
    "state": "States",
    "element": "System",
    "system": "System",
}


def get_game_data_dir(game_id: str) -> str:
    """게임 데이터 폴더 경로를 반환한다. (STORAGE_PATH/{game_id}/data)"""
    return os.path.join(STORAGE_PATH, game_id, "data")


def read_game_json(game_id: str, file_name: str) -> Any:
    """특정 게임의 JSON 파일을 읽어 반환한다."""
    # .json 확장자 처리
    if not file_name.lower().endswith(".json"):
        # 카테고리명으로 들어온 경우 복수형 파일명으로 변환 시도
        cat_key = file_name.lower()
        if cat_key in CATEGORY_TO_PLURAL:
            file_name = CATEGORY_TO_PLURAL[cat_key] + ".json"
        else:
            file_name += ".json"

    file_path = os.path.join(get_game_data_dir(game_id), file_name)

    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return None


def write_game_json(game_id: str, file_name: str, data: Any) -> bool:
    """특정 게임의 JSON 파일을 저장한다."""
    if not file_name.lower().endswith(".json"):
        cat_key = file_name.lower()
        if cat_key in CATEGORY_TO_PLURAL:
            file_name = CATEGORY_TO_PLURAL[cat_key] + ".json"
        else:
            file_name += ".json"

    file_dir = get_game_data_dir(game_id)
    os.makedirs(file_dir, exist_ok=True)
    file_path = os.path.join(file_dir, file_name)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error writing {file_path}: {e}")
        return False


def get_next_entity_id(game_id: str, category: str) -> int:
    """특정 카테고리의 다음 가용한 ID(마지막 ID + 1)를 가져온다."""
    data = read_game_json(game_id, category)

    if not data or not isinstance(data, list):
        return 1

    try:
        # RPG Maker 데이터는 보통 [null, {id:1}, {id:2}, ...] 구조임
        ids = [item["id"] for item in data if isinstance(item, dict) and "id" in item]
        return max(ids) + 1 if ids else 1
    except Exception:
        return 1


def get_system_context(game_id: str) -> dict:
    """System.json 및 Actors.json에서 핵심 시스템 정보를 추출한다."""
    sys_data = read_game_json(game_id, "System")
    actors_data = read_game_json(game_id, "Actors")

    info: dict[str, Any] = {
        "gameTitle": "알 수 없음",
        "currencyUnit": "G",
        "hero": {"id": None, "name": "알 수 없음"},
        "startPosition": {"mapId": 0, "x": 0, "y": 0},
        "elements": [],
    }

    if sys_data:
        info["gameTitle"] = sys_data.get("gameTitle", "알 수 없음")
        info["currencyUnit"] = sys_data.get("currencyUnit", "G")
        info["elements"] = sys_data.get("elements", [])
        info["startPosition"] = {
            "mapId": sys_data.get("startMapId", 0),
            "x": sys_data.get("startX", 0),
            "y": sys_data.get("startY", 0),
        }
        # 주인공 (1번 파티원) ID
        party = list(sys_data.get("partyMembers", []))
        if party:
            info["hero"]["id"] = party[0]

    # 주인공 이름 찾기 (Actors.json)
    if info["hero"]["id"] and actors_data:
        for a in actors_data:
            if a and a.get("id") == info["hero"]["id"]:
                info["hero"]["name"] = a.get("name", "알 수 없음")
                break

    return info
