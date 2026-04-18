"""pending_store — conversation 수준 hold 저장소.

AgentState 는 요청당 휘발이므로, definition 이 만든 hold 의 활성/해소 여부를
다음 턴까지 전달하려면 별도 저장소가 필요하다.

Phase B 는 in-memory dict. 프로덕션은 Redis 로 백엔드 교체 예정이고
교체 시 이 파일만 수정하면 되도록 5 종 인터페이스로 고정한다:
    get / set / mark_resolved / mark_dropped / gc_expired

TTL 은 15 분. 대화가 끊기면 새로 시작하는 게 자연스럽다는 전제.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

# 15 분
DEFAULT_TTL_SECONDS = 15 * 60

HoldReason = Literal[
    "already_exists",
    "not_found",
    "ambiguous_ref",
    "page_condition_unclear",
    "ambiguous_position",
]

EntryStatus = Literal["active", "resolved", "dropped"]


@dataclass
class PendingEntry:
    created_at: float
    last_touched_at: float
    resolve: bool
    hold_reason: HoldReason
    hold_question: str
    snapshot: dict[str, Any]
    status: EntryStatus = "active"


class PendingStore:
    """in-memory dict 구현. 단일 프로세스 전제. 스레드 안전."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._store: dict[str, PendingEntry] = {}
        self._lock = threading.Lock()

    # ── 내부 ────────────────────────────────────────────────────
    def _is_expired(self, entry: PendingEntry, now: float | None = None) -> bool:
        now_ts = now if now is not None else self._clock()
        return (now_ts - entry.last_touched_at) > self._ttl

    # ── public API ─────────────────────────────────────────────
    def get(self, conversation_id: str) -> PendingEntry | None:
        """conversation 의 pending 조회. 만료 엔트리는 lazy gc 후 None."""
        with self._lock:
            entry = self._store.get(conversation_id)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._store[conversation_id]
                return None
            return entry

    def set(
        self,
        conversation_id: str,
        *,
        hold_reason: HoldReason,
        hold_question: str,
        snapshot: dict[str, Any],
    ) -> PendingEntry:
        """새 hold 저장. 기존에 다른 hold 가 있으면 덮어씀.

        한 conversation 에 동시 active hold 는 1 개만 허용한다.
        """
        now = self._clock()
        entry = PendingEntry(
            created_at=now,
            last_touched_at=now,
            resolve=False,
            hold_reason=hold_reason,
            hold_question=hold_question,
            snapshot=dict(snapshot),  # defensive copy (caller mutation 격리)
            status="active",
        )
        with self._lock:
            self._store[conversation_id] = entry
        return entry

    def mark_resolved(self, conversation_id: str) -> PendingEntry | None:
        """유저 답으로 해소. resolve=True, status='resolved'.

        snapshot 은 유지하고 TTL 도 touch (유저가 다시 돌아올 여지).
        """
        with self._lock:
            entry = self._store.get(conversation_id)
            if entry is None:
                return None
            entry.resolve = True
            entry.status = "resolved"
            entry.last_touched_at = self._clock()
            return entry

    def mark_dropped(self, conversation_id: str) -> PendingEntry | None:
        """딴소리로 폐기. status='dropped'. snapshot 은 TTL 까지 캐시."""
        with self._lock:
            entry = self._store.get(conversation_id)
            if entry is None:
                return None
            entry.status = "dropped"
            entry.last_touched_at = self._clock()
            return entry

    def gc_expired(self) -> int:
        """만료된 엔트리를 전수 제거. 제거 개수 반환.

        `get` 은 자체 lazy gc 가 있으니 평소엔 필요 없지만,
        장시간 유휴 시 메모리 정리·디버깅용으로 두는 엔트리포인트.
        """
        now = self._clock()
        with self._lock:
            expired = [cid for cid, e in self._store.items() if self._is_expired(e, now)]
            for cid in expired:
                del self._store[cid]
        return len(expired)

    # ── 테스트·디버그용 ────────────────────────────────────────
    def _size(self) -> int:
        with self._lock:
            return len(self._store)


# 모듈 전역 싱글톤. 프로세스 경계 넘어가면 Redis 로 교체 필요.
_default_store = PendingStore()


def get_default_store() -> PendingStore:
    return _default_store
