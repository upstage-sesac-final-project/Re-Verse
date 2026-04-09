"""agent/tests 공유 pytest fixture.

backend conftest가 STORAGE_PATH를 임시 디렉토리로 패치하는 경우,
agent 테스트에서 실제 게임 데이터가 필요할 때를 위해
base_game/data/를 임시 STORAGE_PATH/game_001/data/에 복사한다.

agent 테스트만 단독 실행할 때(backend conftest 미로드)는
STORAGE_PATH가 실제 경로이므로 복사하지 않는다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BASE_GAME_DATA = _PROJECT_ROOT / "storage" / "games" / "base_game" / "data"
_REAL_STORAGE = _PROJECT_ROOT / "storage" / "games"


@pytest.fixture(autouse=True)
def _ensure_test_game_data():
    """매 테스트마다 STORAGE_PATH의 game_001/data/를 base_game에서 초기화.

    단, STORAGE_PATH가 실제 프로젝트 경로면 이미 데이터가 있으므로 건너뛴다.
    임시 디렉토리(backend conftest)인 경우에만 복사한다.
    """
    from app.backend.core.config import settings

    storage_path = Path(settings.STORAGE_PATH).resolve()

    # 실제 프로젝트 storage 경로면 복사 불필요 (agent 단독 실행 시)
    if storage_path == _REAL_STORAGE.resolve():
        return

    # 임시 디렉토리인 경우에만 base_game에서 복사
    test_data = storage_path / "game_001" / "data"
    if _BASE_GAME_DATA.exists():
        if test_data.exists():
            shutil.rmtree(test_data)
        shutil.copytree(_BASE_GAME_DATA, test_data)
