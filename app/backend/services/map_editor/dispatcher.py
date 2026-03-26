"""맵 에디터 통합 진입점 — map_node가 호출한다."""

from typing import Any, Literal

from app.backend.services.map_editor.event_ops import (
    add_event,
    delete_event,
    update_event_dialogue,
)
from app.backend.services.map_editor.loader import load_map, save_map
from app.backend.services.map_editor.meta_ops import update_meta
from app.backend.services.map_editor.tile_ops import update_tile, update_tile_region

MapOperation = Literal[
    "add_event",
    "update_event_dialogue",
    "delete_event",
    "update_meta",
    "update_tile",
    "update_tile_region",
]

_OP_HANDLERS = {
    "add_event": add_event,
    "update_event_dialogue": update_event_dialogue,
    "delete_event": delete_event,
    "update_meta": update_meta,
    "update_tile": update_tile,
    "update_tile_region": update_tile_region,
}


def execute_map_operation(
    game_id: str,
    map_id: int,
    operation: MapOperation,
    params: dict[str, Any],
) -> dict[str, Any]:
    """맵 수정 작업을 실행하고 결과를 반환한다.

    Returns:
        {
            "success": bool,
            "operation": str,
            "map_id": int,
            "changes": list[dict],  # 변경 내용 요약
            "error": str | None,
        }
    """
    handler = _OP_HANDLERS.get(operation)
    if handler is None:
        return {
            "success": False,
            "operation": operation,
            "map_id": map_id,
            "changes": [],
            "error": f"알 수 없는 작업: {operation}",
        }

    try:
        map_data = load_map(game_id, map_id)
        updated = handler(map_data, params)
        save_map(game_id, map_id, updated)

        return {
            "success": True,
            "operation": operation,
            "map_id": map_id,
            "changes": [{"operation": operation, "params": params}],
            "error": None,
        }
    except (ValueError, FileNotFoundError, KeyError) as e:
        return {
            "success": False,
            "operation": operation,
            "map_id": map_id,
            "changes": [],
            "error": str(e),
        }
