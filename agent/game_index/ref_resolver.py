"""GameIndex — 참조 해소.

System.json 타입 배열(elements, weaponTypes 등)과 엔티티 파일에서
이름으로 ID를 찾는다.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from agent.game_index.catalog import find_in_file
from agent.utils.game_data_io import read_game_json

logger = logging.getLogger(__name__)

_FUZZY_THRESHOLD = 0.6


def resolve_system_type(game_id: str, system_key: str, name: str) -> int | None:
    """System.json의 배열에서 이름→인덱스. 없으면 None.

    예: resolve_system_type("game_001", "elements", "빛") → 8
    """
    if not name:
        return None
    try:
        system = read_game_json(game_id, "System.json")
    except Exception as e:
        logger.warning("[ref_resolver] System.json 로드 실패: %s", e)
        return None
    if not isinstance(system, dict):
        return None
    arr = system.get(system_key)
    if not isinstance(arr, list):
        return None

    target = name.strip().lower()
    # 완전 일치
    for idx, val in enumerate(arr):
        if isinstance(val, str) and val.strip().lower() == target:
            return idx

    # fuzzy
    best_idx, best_ratio = None, 0.0
    for idx, val in enumerate(arr):
        if not isinstance(val, str) or not val.strip():
            continue
        ratio = SequenceMatcher(None, target, val.strip().lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = idx
    return best_idx if best_ratio >= _FUZZY_THRESHOLD else None


def resolve_entity_ref(game_id: str, filename: str, name: str) -> int | None:
    """엔티티 파일에서 이름→ID."""
    entry = find_in_file(game_id, filename, name)
    return entry.id if entry else None
