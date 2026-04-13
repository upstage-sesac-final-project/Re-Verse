"""publish_progress / subscribe_generation_events — WebSocket 진행률 브로드캐스트.

canonical: docs/The_world/generation_api.md §이벤트 브로드캐스팅
"""

from asyncio import Queue
from collections.abc import AsyncIterator

_generation_queues: dict[str, Queue] = {}
# WebSocket 연결 전에 발행된 이벤트를 구독자가 올 때까지 버퍼링
_pending_events: dict[str, list[dict]] = {}


async def publish_progress(generation_id: str, event: dict) -> None:
    """워크플로우 노드에서 호출. 진행 상황을 WebSocket 구독자에게 발행."""
    if generation_id in _generation_queues:
        await _generation_queues[generation_id].put(event)
    else:
        _pending_events.setdefault(generation_id, []).append(event)


async def subscribe_generation_events(generation_id: str) -> AsyncIterator[dict]:
    """WebSocket 핸들러에서 구독. completed 또는 error 이벤트 수신 시 종료."""
    q: Queue = Queue()
    # 구독 전에 쌓인 이벤트를 먼저 큐에 적재
    for buffered in _pending_events.pop(generation_id, []):
        await q.put(buffered)
    _generation_queues[generation_id] = q
    try:
        while True:
            event = await q.get()
            yield event
            if event.get("type") in ("completed", "completed_with_warnings", "error"):
                break
    finally:
        _generation_queues.pop(generation_id, None)
        _pending_events.pop(generation_id, None)
