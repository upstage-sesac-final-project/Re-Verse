"""publish_progress / subscribe_generation_events — WebSocket 진행률 브로드캐스트.

canonical: docs/The_world/generation_api.md §이벤트 브로드캐스팅
"""

from asyncio import Queue
from collections.abc import AsyncIterator

_generation_queues: dict[str, Queue] = {}


async def publish_progress(generation_id: str, event: dict) -> None:
    """워크플로우 노드에서 호출. 진행 상황을 WebSocket 구독자에게 발행."""
    if generation_id in _generation_queues:
        await _generation_queues[generation_id].put(event)


async def subscribe_generation_events(generation_id: str) -> AsyncIterator[dict]:
    """WebSocket 핸들러에서 구독. completed 또는 error 이벤트 수신 시 종료."""
    q: Queue = Queue()
    _generation_queues[generation_id] = q
    try:
        while True:
            event = await q.get()
            yield event
            if event.get("type") in ("completed", "completed_with_warnings", "error"):
                break
    finally:
        _generation_queues.pop(generation_id, None)
