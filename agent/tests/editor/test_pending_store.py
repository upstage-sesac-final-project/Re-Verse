"""pending_store 단위 테스트.

clock 주입으로 TTL 거동을 결정적으로 검증한다. 실시간 sleep 은 쓰지 않는다.
"""

from __future__ import annotations

import pytest

from agent.editor.pending_store import (
    DEFAULT_TTL_SECONDS,
    PendingEntry,
    PendingStore,
    get_default_store,
)


class _FakeClock:
    """호출 시 현재 시간을 돌려주고, advance 로 앞당긴다."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _snap(msg: str = "hi") -> dict:
    return {"field": "무기", "target": "검 A", "note": msg}


# ── 기본 CRUD ───────────────────────────────────────────────────


def test_get_returns_none_for_unknown_cid():
    s = PendingStore(clock=_FakeClock())
    assert s.get("missing") is None


def test_set_then_get_roundtrip():
    clk = _FakeClock()
    s = PendingStore(clock=clk)
    s.set(
        "cid-1",
        hold_reason="not_found",
        hold_question="'검 A' 없는데 만들까요?",
        snapshot=_snap(),
    )

    got = s.get("cid-1")
    assert got is not None
    assert got.hold_reason == "not_found"
    assert got.hold_question == "'검 A' 없는데 만들까요?"
    assert got.resolve is False
    assert got.status == "active"
    assert got.created_at == clk.now
    assert got.last_touched_at == clk.now
    assert got.snapshot == _snap()


def test_set_overwrites_existing_active():
    # 한 conversation 에 active hold 는 1 개만 유지.
    s = PendingStore(clock=_FakeClock())
    s.set("cid", hold_reason="not_found", hold_question="Q1", snapshot={})
    s.set("cid", hold_reason="ambiguous_ref", hold_question="Q2", snapshot={})

    got = s.get("cid")
    assert got is not None
    assert got.hold_reason == "ambiguous_ref"
    assert got.hold_question == "Q2"


def test_snapshot_is_defensive_copy():
    s = PendingStore(clock=_FakeClock())
    snap = {"field": "무기"}
    s.set("cid", hold_reason="not_found", hold_question="Q", snapshot=snap)

    snap["field"] = "이상한 값으로 변조"
    got = s.get("cid")
    assert got is not None
    assert got.snapshot == {"field": "무기"}


# ── mark_resolved / mark_dropped ────────────────────────────────


def test_mark_resolved_flips_flag_and_status():
    clk = _FakeClock()
    s = PendingStore(clock=clk)
    s.set("cid", hold_reason="not_found", hold_question="Q", snapshot=_snap())

    clk.advance(30)
    returned = s.mark_resolved("cid")
    assert returned is not None
    assert returned.resolve is True
    assert returned.status == "resolved"
    assert returned.last_touched_at == clk.now  # touch

    # snapshot 은 유지되어야 함 — 이어받기에서 복원할 수 있도록
    assert returned.snapshot == _snap()


def test_mark_dropped_sets_status_without_deleting():
    clk = _FakeClock()
    s = PendingStore(clock=clk)
    s.set("cid", hold_reason="not_found", hold_question="Q", snapshot=_snap())

    clk.advance(5)
    returned = s.mark_dropped("cid")
    assert returned is not None
    assert returned.status == "dropped"
    # resolve 는 False 로 유지 (해소된 게 아니라 폐기됨)
    assert returned.resolve is False
    # 엔트리 자체는 TTL 까지 남아있어야 함
    assert s.get("cid") is not None


def test_mark_on_missing_cid_returns_none():
    s = PendingStore(clock=_FakeClock())
    assert s.mark_resolved("nope") is None
    assert s.mark_dropped("nope") is None


# ── TTL / lazy gc ───────────────────────────────────────────────


def test_get_lazy_gc_after_ttl():
    clk = _FakeClock()
    s = PendingStore(ttl_seconds=60, clock=clk)
    s.set("cid", hold_reason="not_found", hold_question="Q", snapshot=_snap())

    clk.advance(61)
    assert s.get("cid") is None
    # lazy gc 로 내부 저장소에서 실제 제거
    assert s._size() == 0


def test_get_just_under_ttl_still_returns():
    clk = _FakeClock()
    s = PendingStore(ttl_seconds=60, clock=clk)
    s.set("cid", hold_reason="not_found", hold_question="Q", snapshot=_snap())

    clk.advance(60)  # == TTL, 아직 만료 아님 (strict greater than)
    assert s.get("cid") is not None


def test_mark_resolved_touch_extends_ttl():
    clk = _FakeClock()
    s = PendingStore(ttl_seconds=60, clock=clk)
    s.set("cid", hold_reason="not_found", hold_question="Q", snapshot=_snap())

    clk.advance(30)
    s.mark_resolved("cid")

    clk.advance(45)  # 원래 TTL(60) 은 지났지만 resolve 시점부터는 45s
    got = s.get("cid")
    assert got is not None
    assert got.status == "resolved"


def test_gc_expired_bulk():
    clk = _FakeClock()
    s = PendingStore(ttl_seconds=60, clock=clk)
    s.set("a", hold_reason="not_found", hold_question="Q", snapshot={})
    s.set("b", hold_reason="not_found", hold_question="Q", snapshot={})
    clk.advance(30)
    s.set("c", hold_reason="not_found", hold_question="Q", snapshot={})
    clk.advance(31)  # a, b 만료 (총 61s) / c 는 31s 경과 → 생존

    removed = s.gc_expired()
    assert removed == 2
    assert s._size() == 1
    assert s.get("c") is not None


def test_default_ttl_is_15_minutes():
    # YB.md 8-2 와 결정된 미확정 표에서 15 분 확정
    assert DEFAULT_TTL_SECONDS == 15 * 60


# ── 싱글톤 ──────────────────────────────────────────────────────


def test_default_store_is_singleton():
    a = get_default_store()
    b = get_default_store()
    assert a is b
    assert isinstance(a, PendingStore)


# ── 타입·dataclass 기본 ─────────────────────────────────────────


def test_pending_entry_dataclass_shape():
    clk = _FakeClock()
    s = PendingStore(clock=clk)
    entry = s.set(
        "cid",
        hold_reason="ambiguous_position",
        hold_question="어디에 둘까요?",
        snapshot=_snap(),
    )
    assert isinstance(entry, PendingEntry)
    # 전 필드 존재
    for attr in (
        "created_at",
        "last_touched_at",
        "resolve",
        "hold_reason",
        "hold_question",
        "snapshot",
        "status",
    ):
        assert hasattr(entry, attr), attr


# ── 동시성 sanity (진짜 race 증명은 아니고 lock 경로 실행 확인) ──


def test_concurrent_sets_do_not_raise():
    import threading

    s = PendingStore(clock=_FakeClock())

    def worker(i: int) -> None:
        for _ in range(50):
            s.set(
                f"cid-{i}",
                hold_reason="not_found",
                hold_question=f"Q{i}",
                snapshot={"i": i},
            )
            s.get(f"cid-{i}")
            s.mark_resolved(f"cid-{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 8 개 cid 각각 살아있어야 함
    assert s._size() == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
