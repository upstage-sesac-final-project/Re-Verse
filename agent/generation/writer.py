"""생성된 final_project를 디스크에 저장.

Atomic write 패턴: 임시 파일에 쓰고 rename하여 에디터가 읽는 도중 깨진 JSON을 보지 않게 한다.
"""

import json
import logging
import tempfile
from pathlib import Path

from app.backend.core.game_paths import get_game_data_path

logger = logging.getLogger(__name__)


def _atomic_write_json(dest: Path, content: dict) -> None:
    """임시 파일에 쓰고 atomic rename으로 교체."""
    fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        Path(tmp_path).replace(dest)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


async def write_project_to_disk(game_id: str, final_project: dict) -> None:
    """final_project dict → storage/games/{game_id}/data/ JSON 파일 저장."""
    data_path: Path = get_game_data_path(game_id)
    data_path.mkdir(parents=True, exist_ok=True)

    # base_game에서 복사된 잔여 Map*.json 파일 제거 (새 프로젝트에 없는 것)
    new_map_files = {
        fname for fname in final_project if fname.startswith("Map") and fname.endswith(".json")
    }
    for existing in data_path.glob("Map*.json"):
        if existing.name not in new_map_files:
            existing.unlink()
            logger.info("removed stale: %s", existing.name)

    for fname, content in final_project.items():
        dest = data_path / fname
        _atomic_write_json(dest, content)
        logger.info("written: %s", dest.name)
