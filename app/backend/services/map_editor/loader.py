"""맵 파일 로드/저장 유틸리티."""

import json
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[5]


def map_path(game_id: str, map_id: int) -> Path:
    return _project_root() / "storage" / "games" / game_id / "data" / f"Map{map_id:03d}.json"


def load_map(game_id: str, map_id: int) -> dict[str, Any]:
    path = map_path(game_id, map_id)
    if not path.exists():
        raise FileNotFoundError(f"맵 파일을 찾을 수 없습니다: Map{map_id:03d}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def save_map(game_id: str, map_id: int, data: dict[str, Any]) -> None:
    path = map_path(game_id, map_id)
    # RPG Maker MZ는 compact JSON을 그대로 읽음
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def find_free_event_id(events: list[Any]) -> int:
    """events 배열에서 None/빈 슬롯의 ID를 반환한다. 없으면 마지막 인덱스+1."""
    for i, ev in enumerate(events):
        if ev is None and i > 0:
            return i
    return len(events)


def validate_bounds(map_data: dict[str, Any], x: int, y: int) -> bool:
    return 0 <= x < map_data["width"] and 0 <= y < map_data["height"]
