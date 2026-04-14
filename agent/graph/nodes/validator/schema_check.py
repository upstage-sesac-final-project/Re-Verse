"""Schema 검증 — pydantic 으로 변경된 파일을 검증한다."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.utils.game_data_io import get_game_data_dir

logger = logging.getLogger(__name__)

# 기존 agent/schemas 재활용
try:
    from agent.schemas.actors import ActorsFile
    from agent.schemas.armors import ArmorsFile
    from agent.schemas.classes import ClassesFile
    from agent.schemas.enemies import EnemiesFile
    from agent.schemas.items import ItemsFile
    from agent.schemas.skills import SkillsFile
    from agent.schemas.states import StatesFile
    from agent.schemas.system import System
    from agent.schemas.weapons import WeaponsFile

    SCHEMA_MAP: dict[str, type] = {
        "Actors.json": ActorsFile,
        "Armors.json": ArmorsFile,
        "Classes.json": ClassesFile,
        "Enemies.json": EnemiesFile,
        "Items.json": ItemsFile,
        "Skills.json": SkillsFile,
        "States.json": StatesFile,
        "System.json": System,
        "Weapons.json": WeaponsFile,
    }
except ImportError:
    SCHEMA_MAP = {}
    logger.warning("[schema_check] agent.schemas 를 import 할 수 없습니다. Schema 검증 비활성화.")

_MAP_PATTERN = re.compile(r"^Map\d{3}\.json$", re.IGNORECASE)


def validate_changed_files(
    game_id: str,
    modified_files: list[str],
) -> list[dict[str, Any]]:
    """변경된 파일 목록을 pydantic schema 로 검증.

    Returns list of {"file": str, "valid": bool, "detail": str}
    """
    if not game_id or not SCHEMA_MAP:
        return []

    from pathlib import Path

    data_path = Path(get_game_data_dir(game_id))
    results: list[dict[str, Any]] = []

    for filename in modified_files:
        schema_cls = SCHEMA_MAP.get(filename)
        if schema_cls is None:
            if _MAP_PATTERN.match(filename):
                schema_cls = SCHEMA_MAP.get("Maps.json")  # MapFile if exists
            if schema_cls is None:
                continue  # 스키마 없으면 skip

        fp = data_path / filename
        if not fp.exists():
            results.append({"file": filename, "valid": False, "detail": f"{filename} 파일 없음"})
            continue

        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
            schema_cls.model_validate(raw)
            results.append({"file": filename, "valid": True, "detail": ""})
        except Exception as e:
            detail = str(e)[:500]
            results.append({"file": filename, "valid": False, "detail": detail})
            logger.warning("[schema_check] %s 검증 실패: %s", filename, detail[:200])

    return results
