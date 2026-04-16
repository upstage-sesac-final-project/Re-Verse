"""GameIndex — 인덱스 빌더.

게임 데이터 파일을 읽어 엔티티 인덱스를 생성한다.
game_id별로 캐싱하며, 파일 mtime 변경 시 자동 invalidation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.utils.game_data_io import get_game_data_dir, read_game_json

logger = logging.getLogger(__name__)


@dataclass
class EntityEntry:
    """인덱스의 단일 엔티티 항목."""

    file: str  # "Enemies.json"
    id: int  # 7
    name: str  # "마왕"
    kind: str  # "enemy"


# entity 파일 8종 + System.json
_ENTITY_FILES: dict[str, str] = {
    # filename: kind
    "Actors.json": "actor",
    "Classes.json": "class",
    "Skills.json": "skill",
    "Items.json": "item",
    "Weapons.json": "weapon",
    "Armors.json": "armor",
    "Enemies.json": "enemy",
    "States.json": "state",
}


# 캐시: {game_id: {"mtime": float, "entries": list[EntityEntry]}}
_INDEX_CACHE: dict[str, dict[str, Any]] = {}


def _data_dir_mtime(game_id: str) -> float:
    """game_id의 data 디렉토리 내 entity 파일 중 가장 최근 mtime."""
    try:
        data_dir = Path(get_game_data_dir(game_id))
    except Exception:
        return 0.0
    if not data_dir.exists():
        return 0.0
    max_mtime = 0.0
    for filename in _ENTITY_FILES:
        fp = data_dir / filename
        if fp.exists():
            mtime = fp.stat().st_mtime
            if mtime > max_mtime:
                max_mtime = mtime
    return max_mtime


def build_index(game_id: str, force: bool = False) -> list[EntityEntry]:
    """game_id의 전체 entity 파일을 스캔하여 인덱스 생성.

    캐싱된 인덱스가 있고 mtime이 같으면 캐시 반환.
    """
    current_mtime = _data_dir_mtime(game_id)

    if not force and game_id in _INDEX_CACHE:
        cached = _INDEX_CACHE[game_id]
        if cached["mtime"] == current_mtime:
            return cached["entries"]

    entries: list[EntityEntry] = []
    for filename, kind in _ENTITY_FILES.items():
        try:
            data = read_game_json(game_id, filename)
        except Exception as e:
            logger.warning("[game_index] %s 로드 실패: %s", filename, e)
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            entries.append(
                EntityEntry(
                    file=filename,
                    id=int(entry.get("id", 0)),
                    name=name,
                    kind=kind,
                )
            )

    _INDEX_CACHE[game_id] = {"mtime": current_mtime, "entries": entries}
    logger.info("[game_index] '%s' 인덱스 빌드 완료: %d entries", game_id, len(entries))
    return entries


def invalidate(game_id: str | None = None) -> None:
    """캐시 무효화. game_id를 지정하면 해당 게임만, 아니면 전체."""
    if game_id is None:
        _INDEX_CACHE.clear()
    else:
        _INDEX_CACHE.pop(game_id, None)
