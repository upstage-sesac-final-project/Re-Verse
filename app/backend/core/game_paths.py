"""게임 데이터 디스크 경로 (로컬 storage 또는 EC2 컨테이너 내 동기화 디렉터리).

프로덕션에서 STORAGE_BACKEND=s3일 때는 요청 전후로 S3와 이 경로를 동기화합니다.
에이전트/JSON 매니저는 항상 이 로컬 경로만 읽고 씁니다.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from app.backend.core.config import settings

logger = logging.getLogger(__name__)


def get_storage_root() -> Path:
    """STORAGE_PATH (예: ./storage/games 또는 /app/storage/games) 절대 경로."""
    return Path(settings.STORAGE_PATH).resolve()


def get_game_root(game_id: str) -> Path:
    """특정 게임 루트: {STORAGE_PATH}/{game_id}/"""
    return get_storage_root() / game_id


def get_game_data_path(game_id: str) -> Path:
    """RPG Maker `data/` 폴더 (Actors.json 등). {STORAGE_PATH}/{game_id}/data/"""
    return get_game_root(game_id) / "data"


def ensure_rpgmaker_mz_project_shell(game_root: Path) -> None:
    """`BASE_GAME_PATH`에서 MZ 프로젝트 루트 표식 파일을 `game_root`에 없으면 복사·연결한다.

    Re-Verse는 `_copy_base_game`으로 `data/`만 둔 프로젝트가 많아, k4zuki 등 Node MCP가
    `RPGMAKER_PROJECT_PATH`를 **전체 MZ 프로젝트**로 검증할 때
    ``Invalid RPG Maker MZ project path`` 가 난다. MCP 호출 전·신규 복제 직후에 호출한다.

    - 루트 파일: `game.rmmzproject`, `package.json`, `index.html`
    - `css/` 디렉터리 전체(작음)
    - POSIX에서만: `js` → `BASE_GAME/js` 심볼릭 링크(대용량 중복 방지, MCP가 스크립트를 열 때 필요할 수 있음)
    """
    base = Path(settings.BASE_GAME_PATH).resolve()
    gr = game_root.resolve()
    if not base.is_dir() or not gr.is_dir():
        return

    n = 0
    for name in ("game.rmmzproject", "package.json", "index.html"):
        src, dst = base / name, gr / name
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            n += 1

    css_src, css_dst = base / "css", gr / "css"
    if css_src.is_dir() and not css_dst.exists():
        shutil.copytree(css_src, css_dst)
        n += 1

    js_src, js_dst = base / "js", gr / "js"
    if js_src.is_dir() and not js_dst.exists():
        if os.name == "posix":
            try:
                js_dst.symlink_to(js_src.resolve(), target_is_directory=True)
                n += 1
            except OSError:
                logger.debug("MZ js 심볼릭 링크 생성 실패(무시): %s", js_dst, exc_info=True)
        else:
            # Windows 등: 링크 대신 생략(MCP가 js를 요구하면 추후 copytree 검토)
            pass

    if n:
        logger.info(
            "MZ MCP용 프로젝트 루트를 base_game에서 보강했습니다: %s (%d 항목)",
            gr,
            n,
        )
