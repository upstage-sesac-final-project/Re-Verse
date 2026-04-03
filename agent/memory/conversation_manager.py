"""대화 이력 관리 — 슬라이딩 윈도우 + 요약 압축."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.llm_client import invoke_llm_simple
from app.backend.repositories.project_repository import project_repository

logger = logging.getLogger(__name__)

WINDOW_SIZE = 10  # 최근 N턴 그대로 전달
SUMMARY_WINDOW = 10  # 그 이전 N턴은 요약 압축

_SUMMARY_SYSTEM = """\
아래는 RPG Maker 게임 제작 AI 'Re:Verse'와 사용자의 이전 대화 목록이다.
핵심 내용만 3~5줄로 간결하게 요약하라. 요약문만 출력하고 다른 말은 하지 마라.
"""


async def build_conversation_history(
    project_id: int,
    db: AsyncSession,
) -> list[dict]:
    """슬라이딩 윈도우 + 요약 압축으로 conversation_history 구성.

    Returns:
        [{"role": "user"|"assistant", "content": str}, ...]
        오래된 순서대로 정렬. 요약본이 있으면 맨 앞에 삽입.
    """
    logs = await project_repository.get_recent_conversation_logs(
        project_id=project_id,
        limit=WINDOW_SIZE + SUMMARY_WINDOW,
        db=db,
    )

    if not logs:
        return []

    recent_logs = logs[-WINDOW_SIZE:]
    older_logs = logs[: len(logs) - len(recent_logs)]

    history: list[dict] = []

    # 오래된 구간 요약
    if older_logs:
        older_text = "\n".join(
            f"[user] {log.user_input}\n[assistant] {log.agent_response or ''}" for log in older_logs
        )
        try:
            summary = await invoke_llm_simple(_SUMMARY_SYSTEM, older_text)
            history.append({"role": "assistant", "content": f"[이전 대화 요약] {summary}"})
            logger.debug("[ConversationManager] 요약 완료 | turns=%d", len(older_logs))
        except Exception:
            logger.warning("[ConversationManager] 요약 실패, 건너뜀", exc_info=True)

    # 최근 구간 그대로 추가
    for log in recent_logs:
        history.append({"role": "user", "content": log.user_input})
        if log.agent_response:
            history.append({"role": "assistant", "content": log.agent_response})

    return history
