import logging


async def publish_progress(generation_id: str, data: dict):
    """WebSocket 등을 통해 생성 진행 상황을 발행 (현재는 로그 출력)."""
    logger = logging.getLogger(__name__)
    phase = data.get("phase", "unknown")
    progress = data.get("progress", 0)
    message = data.get("message", "")

    logger.info(f"[PROGRESS] {generation_id} | {phase} | {progress}% | {message}")
    # TODO: 실제 WebSocket Manager와 연동
