"""게임 데이터 디스크 경로 (로컬 storage 또는 EC2 컨테이너 내 동기화 디렉터리).

프로덕션에서 STORAGE_BACKEND=s3일 때는 요청 전후로 S3와 이 경로를 동기화합니다.
에이전트/JSON 매니저는 항상 이 로컬 경로만 읽고 씁니다.
"""

from __future__ import annotations

from pathlib import Path

from app.backend.core.config import settings


def get_storage_root() -> Path:
    """STORAGE_PATH (예: ./storage/games 또는 /app/storage/games) 절대 경로."""
    return Path(settings.STORAGE_PATH).resolve()


def get_game_root(game_id: str) -> Path:
    """특정 게임 루트: {STORAGE_PATH}/{game_id}/"""
    return get_storage_root() / game_id


def get_game_data_path(game_id: str) -> Path:
    """RPG Maker `data/` 폴더 (Actors.json 등). {STORAGE_PATH}/{game_id}/data/"""
    return get_game_root(game_id) / "data"
