"""대화 이력 관리 — 슬라이딩 윈도우 + 요약 압축."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.config import agent_config
from agent.core.llm_client import invoke_llm_simple
from app.backend.repositories.project_repository import project_repository

logger = logging.getLogger(__name__)

# 게임 관련 인텐트만 history에 포함 (#3) — Phase C 이후 영문 enum 사용.
# 구 한국어 literal 은 DB 에 이미 쌓여있을 수 있어 하위 호환으로 병행 허용.
_GAME_INTENTS = {
    # 신(Phase C): agent/editor/intents.py IntentValue
    "object_create",
    "object_update",
    "event_create",
    "event_update",
    "query",
    "game_overview",
    "multi_intent",
    "clarification_needed",
    # 구(Phase C 이전): 호환용. 기존 로그 로드 시 필터 통과.
    "게임_요소_생성",
    "게임_요소_수정",
    "게임_요소_조회",
    "복합_의도",
    "추가_정보_필요",
}

_SUMMARY_SYSTEM = """\
아래는 RPG Maker 게임 제작 AI 'Re:Verse'와 사용자의 이전 대화 목록이다.
핵심 내용만 3~5줄로 간결하게 요약하라. 요약문만 출력하고 다른 말은 하지 마라.
"""

# 요약 캐시: project_id → (older_log_ids 튜플, 요약문) (#1)
_summary_cache: dict[int, tuple[tuple, str]] = {}


async def build_conversation_history(
    project_id: int,
    db: AsyncSession,
) -> list[dict]:
    """슬라이딩 윈도우 + 요약 압축으로 conversation_history 구성.

    Returns:
        오래된 순 정렬. 요약본이 있으면 맨 앞에 삽입.
    """
    window = agent_config.HISTORY_WINDOW_SIZE
    summary_window = agent_config.HISTORY_SUMMARY_WINDOW

    all_logs = await project_repository.get_recent_conversation_logs(
        project_id=project_id,
        limit=window + summary_window,
        db=db,
    )

    # 게임 관련 인텐트만 필터링 (#3)
    logs = [log for log in all_logs if log.intent in _GAME_INTENTS]

    if not logs:
        return []

    recent_logs = logs[-window:]
    older_logs = logs[: len(logs) - len(recent_logs)]

    history: list[dict] = []

    # 오래된 구간 요약 (캐시 활용) (#1)
    if older_logs:
        older_ids = tuple(log.id for log in older_logs)
        cached = _summary_cache.get(project_id)

        if cached and cached[0] == older_ids:
            summary = cached[1]
            logger.debug("[ConversationManager] 요약 캐시 hit | project_id=%d", project_id)
        else:
            older_text = "\n".join(
                f"[user] {log.user_input}\n[assistant] {log.agent_response or ''}"
                for log in older_logs
            )
            try:
                summary = await invoke_llm_simple(_SUMMARY_SYSTEM, older_text)
                _summary_cache[project_id] = (older_ids, summary)
                logger.debug("[ConversationManager] 요약 완료 | turns=%d", len(older_logs))
            except Exception:
                logger.warning("[ConversationManager] 요약 실패, 건너뜀", exc_info=True)
                summary = None

        if summary:
            history.append({"role": "assistant", "content": f"[이전 대화 요약] {summary}"})

    # 최근 구간 그대로 추가
    for log in recent_logs:
        history.append({"role": "user", "content": log.user_input})
        if log.agent_response:
            history.append({"role": "assistant", "content": log.agent_response})

    return history
