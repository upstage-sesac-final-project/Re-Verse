"""Executor dispatch — target_file 에 따라 handler 라우팅.

executor entry point (executor/__init__.py) 에서 step 마다 이 함수를 호출한다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agent.graph.nodes.executor_v2.handlers.entity import ALL_SUPPORTED as ENTITY_SUPPORTED
from agent.graph.nodes.executor_v2.handlers.entity import execute_entity_step
from agent.graph.nodes.executor_v2.handlers.map import execute_map_step

logger = logging.getLogger(__name__)

_MAP_FILE_PATTERN = re.compile(r"^Map\d{3}\.json$", re.IGNORECASE)


def dispatch_step(
    data_path: Path,
    action: str,
    target_file: str,
    target_info: dict[str, Any],
) -> dict[str, Any]:
    """target_file 을 보고 적절한 handler 로 라우팅.

    Returns:
        RPGMakerCRUD 호환 result dict.
    """
    if target_file in ENTITY_SUPPORTED:
        return execute_entity_step(data_path, action, target_file, target_info)

    if target_file == "MapInfos.json" or _MAP_FILE_PATTERN.match(target_file) or target_file == "Map":
        return execute_map_step(data_path, action, target_file, target_info)

    return {
        "success": False,
        "data": None,
        "modified_files": [],
        "error": f"지원하지 않는 target_file: {target_file}",
        "entity_id": None,
    }
