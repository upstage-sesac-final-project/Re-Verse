"""맵 에디터 통합 진입점."""

from typing import Any, Literal

from agent.map_editor.event_ops import (
    add_event,
    delete_event,
    update_event_commands,
    update_event_dialogue,
)
from agent.map_editor.loader import load_map, save_map
from agent.map_editor.map_ops import create_map, duplicate_map
from agent.map_editor.meta_ops import update_meta
from agent.map_editor.tile_ops import fill_map_layer, update_tile, update_tile_region
from agent.map_editor.validator import validate_map
from agent.map_editor.wfc.features import apply_features
from agent.map_editor.wfc.painter import generate_map_from_zones

MapOperation = Literal[
    "create_map",
    "duplicate_map",
    "generate_map",
    "add_event",
    "update_event_commands",
    "update_event_dialogue",
    "delete_event",
    "update_meta",
    "update_tile",
    "update_tile_region",
    "fill_map_layer",
]

# 맵 파일을 직접 다루는 ops (load/save 내부 처리)
_MAP_LEVEL_OPS = {"create_map", "duplicate_map"}


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
            "changes": list[dict],
            "error": str | None,
            "validation_errors": list[str],
        }
    """
    try:
        if operation == "create_map":
            result_data = create_map(game_id, params)
            return {
                "success": True,
                "operation": operation,
                "map_id": result_data["map_id"],
                "changes": [{"operation": operation, "params": params, "result": result_data}],
                "error": None,
                "validation_errors": [],
            }

        if operation == "duplicate_map":
            result_data = duplicate_map(game_id, params)
            return {
                "success": True,
                "operation": operation,
                "map_id": result_data["map_id"],
                "changes": [{"operation": operation, "params": params, "result": result_data}],
                "error": None,
                "validation_errors": [],
            }

        if operation == "generate_map":
            # feature 기반 맵 자동 생성: load → paint → validate → save
            # params에 "features" 키 있으면 신규 방식, "zones"만 있으면 구형 호환
            map_data = load_map(game_id, map_id)
            if "features" in params or "background" in params:
                updated = apply_features(map_data, params)
            else:
                updated = generate_map_from_zones(map_data, params)
            validation_errors = validate_map(updated)
            if validation_errors:
                return {
                    "success": False,
                    "operation": operation,
                    "map_id": map_id,
                    "changes": [],
                    "error": "맵 유효성 검사 실패",
                    "validation_errors": validation_errors,
                }
            save_map(game_id, map_id, updated)
            return {
                "success": True,
                "operation": operation,
                "map_id": map_id,
                "changes": [{"operation": operation, "params": params}],
                "error": None,
                "validation_errors": [],
            }

        # 나머지 ops: load → mutate → validate → save
        handlers = {
            "add_event": add_event,
            "update_event_commands": update_event_commands,
            "update_event_dialogue": update_event_dialogue,
            "delete_event": delete_event,
            "update_meta": update_meta,
            "update_tile": update_tile,
            "update_tile_region": update_tile_region,
            "fill_map_layer": fill_map_layer,
        }

        handler = handlers.get(operation)
        if handler is None:
            return {
                "success": False,
                "operation": operation,
                "map_id": map_id,
                "changes": [],
                "error": f"알 수 없는 작업: {operation}",
                "validation_errors": [],
            }

        map_data = load_map(game_id, map_id)
        updated = handler(map_data, params)

        validation_errors = validate_map(updated)
        if validation_errors:
            return {
                "success": False,
                "operation": operation,
                "map_id": map_id,
                "changes": [],
                "error": "맵 유효성 검사 실패",
                "validation_errors": validation_errors,
            }

        save_map(game_id, map_id, updated)

        return {
            "success": True,
            "operation": operation,
            "map_id": map_id,
            "changes": [{"operation": operation, "params": params}],
            "error": None,
            "validation_errors": [],
        }

    except (ValueError, FileNotFoundError, KeyError) as e:
        return {
            "success": False,
            "operation": operation,
            "map_id": map_id,
            "changes": [],
            "error": str(e),
            "validation_errors": [],
        }
