"""맵 에디터 — RPG Maker MZ Map*.json 수정 모듈."""

from app.backend.services.map_editor.dispatcher import MapOperation, execute_map_operation

__all__ = ["execute_map_operation", "MapOperation"]
