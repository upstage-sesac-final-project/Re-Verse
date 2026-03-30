"""맵 파일 로드/저장 유틸리티."""

import json
from pathlib import Path
from typing import Any

from agent.map_editor.tileset_catalog import format_catalog_for_prompt, get_tiles_for_images


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


def load_tilesets(game_id: str) -> list[Any]:
    path = _data_dir(game_id) / "Tilesets.json"
    if not path.exists():
        raise FileNotFoundError("Tilesets.json 없음")
    return json.loads(path.read_text(encoding="utf-8"))


def get_tileset_context(game_id: str, tileset_id: int) -> dict[str, Any]:
    """tilesetId에 해당하는 타일셋 정보와 사용 가능한 타일 카탈로그를 반환한다.

    반환:
        {
            "tileset_id": int,
            "name": str,
            "image_names": list[str],    # tilesetNames (빈 문자열 제외)
            "tiles": {"layer0": [...], "layer1": [...]},
            "prompt_text": str,          # LLM 프롬프트용 요약 텍스트
        }
    """
    try:
        tilesets = load_tilesets(game_id)
    except FileNotFoundError:
        return {
            "tileset_id": tileset_id,
            "name": "unknown",
            "image_names": [],
            "tiles": {},
            "prompt_text": "",
        }

    ts = next((t for t in tilesets if t and t.get("id") == tileset_id), None)
    if ts is None:
        return {
            "tileset_id": tileset_id,
            "name": "unknown",
            "image_names": [],
            "tiles": {},
            "prompt_text": "",
        }

    image_names = [n for n in ts.get("tilesetNames", []) if n]
    tiles = get_tiles_for_images(image_names)
    prompt_text = format_catalog_for_prompt(image_names)

    return {
        "tileset_id": tileset_id,
        "name": ts.get("name", ""),
        "image_names": image_names,
        "tiles": tiles,
        "prompt_text": prompt_text,
    }


def find_free_event_id(events: list[Any]) -> int:
    """events 배열에서 None 슬롯 ID를 반환한다. 없으면 마지막 인덱스+1."""
    for i, ev in enumerate(events):
        if ev is None and i > 0:
            return i
    return len(events)
