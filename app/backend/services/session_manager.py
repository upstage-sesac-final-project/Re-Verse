"""편집 세션 관리 + Game-Level Lock.

편집 페이지 진입/이탈 시 세션을 등록/해제하고,
동일 게임의 동시 편집을 방지하는 lock을 제공한다.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    user_id: int
    project_id: int
    game_id: str
    entered_at: float = field(default_factory=time.time)
    last_sync_at: float | None = None


# ── 세션 레지스트리 ──────────────────────────────────────
_active_sessions: dict[str, SessionInfo] = {}  # key: game_id


def register_session(game_id: str, user_id: int, project_id: int) -> SessionInfo:
    """세션 등록. 이미 활성이면 409."""
    if game_id in _active_sessions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 다른 세션에서 편집 중입니다.",
        )
    info = SessionInfo(user_id=user_id, project_id=project_id, game_id=game_id)
    _active_sessions[game_id] = info
    logger.info("[Session] 등록 | game_id=%s, user_id=%d", game_id, user_id)
    return info


def unregister_session(game_id: str) -> SessionInfo | None:
    """세션 제거 및 반환. 없으면 None."""
    info = _active_sessions.pop(game_id, None)
    if info:
        logger.info("[Session] 해제 | game_id=%s, user_id=%d", game_id, info.user_id)
    return info


def is_active(game_id: str) -> bool:
    return game_id in _active_sessions


def get_all_active() -> dict[str, SessionInfo]:
    return dict(_active_sessions)


def touch_session(game_id: str) -> None:
    """백그라운드 S3 업로드 성공 시 last_sync_at 갱신."""
    if game_id in _active_sessions:
        _active_sessions[game_id].last_sync_at = time.time()


# ── Game-Level Lock ──────────────────────────────────────
_game_locks: dict[str, asyncio.Lock] = {}


async def get_game_lock(game_id: str) -> asyncio.Lock:
    if game_id not in _game_locks:
        _game_locks[game_id] = asyncio.Lock()
    return _game_locks[game_id]


def remove_game_lock(game_id: str) -> None:
    """프로젝트 삭제 시 해당 lock 정리."""
    _game_locks.pop(game_id, None)


# ── Orphan 감지 ──────────────────────────────────────────
def get_orphan_game_ids(storage_path: Path) -> list[str]:
    """로컬에 남아있지만 활성 세션이 없는 game 폴더 목록."""
    storage = Path(storage_path).resolve()
    if not storage.is_dir():
        return []
    orphans = []
    for child in storage.iterdir():
        if child.is_dir() and child.name.startswith("game_") and child.name not in _active_sessions:
            orphans.append(child.name)
    return orphans
