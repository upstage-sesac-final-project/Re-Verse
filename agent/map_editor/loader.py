"""맵 파일 로드/저장 유틸리티."""

import json
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    # agent/map_editor/loader.py → agent/map_editor/ → agent/ → project root
    return Path(__file__).resolve().parents[2]


def _data_dir(game_id: str) -> Path:
    return _project_root() / "storage" / "games" / game_id / "data"


def map_path(game_id: str, map_id: int) -> Path:
    return _data_dir(game_id) / f"Map{map_id:03d}.json"


def map_infos_path(game_id: str) -> Path:
    return _data_dir(game_id) / "MapInfos.json"


def load_map(game_id: str, map_id: int) -> dict[str, Any]:
    path = map_path(game_id, map_id)
    if not path.exists():
        raise FileNotFoundError(f"맵 파일 없음: Map{map_id:03d}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def save_map(game_id: str, map_id: int, data: dict[str, Any]) -> None:
    path = map_path(game_id, map_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def load_map_infos(game_id: str) -> list[Any]:
    path = map_infos_path(game_id)
    if not path.exists():
        raise FileNotFoundError("MapInfos.json 없음")
    return json.loads(path.read_text(encoding="utf-8"))


def save_map_infos(game_id: str, infos: list[Any]) -> None:
    path = map_infos_path(game_id)
    text = json.dumps(infos, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def next_map_id(game_id: str) -> int:
    """MapInfos에서 사용 가능한 다음 맵 ID를 반환한다."""
    try:
        infos = load_map_infos(game_id)
    except FileNotFoundError:
        return 1
    # 인덱스 = 맵 ID. 마지막 non-null 인덱스 + 1
    last = max((i for i, v in enumerate(infos) if v is not None), default=0)
    return last + 1


def find_free_event_id(events: list[Any]) -> int:
    """events 배열에서 None 슬롯 ID를 반환한다. 없으면 마지막 인덱스+1."""
    for i, ev in enumerate(events):
        if ev is None and i > 0:
            return i
    return len(events)
