"""생성된 final_project를 디스크에 저장."""

import json
import logging
from pathlib import Path

from app.backend.core.game_paths import get_game_data_path

logger = logging.getLogger(__name__)


async def write_project_to_disk(game_id: str, final_project: dict) -> None:
    """final_project dict → storage/games/{game_id}/data/ JSON 파일 저장."""
    data_path: Path = get_game_data_path(game_id)
    data_path.mkdir(parents=True, exist_ok=True)

    for fname, content in final_project.items():
        dest = data_path / fname
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        logger.info("written: %s", dest.name)
