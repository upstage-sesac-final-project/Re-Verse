import json
import logging
import os
from typing import Any

import ijson

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


def read_game_json_fields(game_id: str, category: str, fields: list[str]) -> list[dict | None]:
    """대용량 JSON에서 필요한 필드만 추출하여 메모리 효율적으로 읽는다.

    Args:
        game_id: 게임 ID
        category: 데이터 카테고리 (Actors, Items 등)
        fields: 추출할 필드 리스트 (예: ["id", "name", "description"])

    Returns:
        추출된 필드들만 담은 가벼운 dict 리스트 (0번 null 유지)
    """
    file_name = category
    if not file_name.lower().endswith(".json"):
        cat_key = file_name.lower()
        if cat_key in CATEGORY_TO_PLURAL:
            file_name = CATEGORY_TO_PLURAL[cat_key] + ".json"
        else:
            file_name += ".json"

    file_path = os.path.join(get_game_data_dir(game_id), file_name)
    results: list[dict | None] = []

    if not os.path.exists(file_path):
        return results

    try:
        with open(file_path, "rb") as f:
            # 'item'은 루트 배열의 각 요소를 의미함
            for item in ijson.items(f, "item"):
                if item is None:
                    results.append(None)
                    continue

                if isinstance(item, dict):
                    # 필요한 필드만 쏙 뽑아냄
                    filtered_item = {k: item.get(k) for k in fields if k in item}
                    # ID는 기본적으로 포함시켜주는 것이 추적에 유리함
                    if "id" not in filtered_item and "id" in item:
                        filtered_item["id"] = item["id"]
                    results.append(filtered_item)
                else:
                    results.append(None)
        return results
    except Exception as e:
        logger.error(f"Error streaming fields from {file_path}: {e}")
        return results


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


def get_next_append_id_streaming(file_path: str) -> int:
    """ijson을 사용하여 파일 전체를 로드하지 않고 배열의 길이를 계산한다."""
    if not os.path.exists(file_path):
        return 1

    last_idx = -1
    try:
        with open(file_path, "rb") as f:
            # 'item'은 루트 배열의 각 요소를 의미함
            for i, _ in enumerate(ijson.items(f, "item")):
                last_idx = i
        return last_idx + 1
    except Exception as e:
        logger.error(f"Error counting items in {file_path}: {e}")
        return 1


def get_next_empty_slot_id_streaming(file_path: str) -> int:
    """ijson을 사용하여 이름이 비어있는 첫 번째 슬롯의 ID를 찾는다."""
    if not os.path.exists(file_path):
        return 1

    last_idx = -1
    found_id = None
    try:
        with open(file_path, "rb") as f:
            for i, item in enumerate(ijson.items(f, "item")):
                last_idx = i
                if i > 0 and isinstance(item, dict):
                    name = item.get("name")
                    # 디버깅: 모든 슬롯의 이름 상태를 로그로 남김 (나중에 삭제 예정)
                    # logger.debug(f"[ID-DEBUG] Index {i}: name='{name}' (type: {type(name)})")

                    if name == "":
                        found_id = i
                        logger.info(f"[ID-DEBUG] 빈 슬롯 발견! ID: {i}")
                        break

        final_id = found_id if found_id is not None else last_idx + 1
        return final_id
    except Exception as e:
        logger.error(f"Error searching empty slot in {file_path}: {e}")
        return 1


def get_next_entity_id(game_id: str, category: str, strategy: str = "fill_gaps") -> int:
    """특정 카테고리의 다음 가용한 ID를 가져온다. (Streaming 지원)

    Args:
        game_id: 게임 ID
        category: 데이터 카테고리 (Actors, Items 등)
        strategy: 'append' (무조건 맨 뒤) 또는 'fill_gaps' (비어있는 중간 슬롯 우선)
    """
    # 파일 경로 생성
    file_name = category
    if not file_name.lower().endswith(".json"):
        cat_key = file_name.lower()
        if cat_key in CATEGORY_TO_PLURAL:
            file_name = CATEGORY_TO_PLURAL[cat_key] + ".json"
        else:
            file_name += ".json"

    file_path = os.path.join(get_game_data_dir(game_id), file_name)

    if strategy == "fill_gaps":
        return get_next_empty_slot_id_streaming(file_path)
    else:
        return get_next_append_id_streaming(file_path)


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
