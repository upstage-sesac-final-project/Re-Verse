"""LangSmith 트레이싱 설정.

앱 시작 시 setup_langsmith()를 한 번 호출하면
이후 모든 LangChain/LangGraph 호출이 자동으로 트레이싱된다.

사용법:
    # app/backend/main.py lifespan 에서 호출
    from agent.monitoring.langsmith_setup import setup_langsmith
    setup_langsmith()

비활성화:
    .env 에서 LANGSMITH_TRACING=False 로 설정하거나 LANGSMITH_API_KEY 를 비우면 된다.
"""

import logging
import os

from agent.core.config import agent_config

logger = logging.getLogger(__name__)


def setup_langsmith() -> None:
    """LangSmith 트레이싱 환경변수를 설정한다.

    LangChain은 LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY 환경변수를 읽어
    자동으로 모든 체인/그래프 호출을 트레이싱한다.
    """
    if not agent_config.LANGSMITH_TRACING:
        logger.info("LangSmith 트레이싱 비활성화 (LANGSMITH_TRACING=False)")
        return

    if not agent_config.LANGSMITH_API_KEY:
        logger.warning("LangSmith API 키 없음 — 트레이싱 건너뜀 (LANGSMITH_API_KEY 미설정)")
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = agent_config.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = agent_config.LANGSMITH_PROJECT

    logger.info("LangSmith 트레이싱 활성화 — 프로젝트: %s", agent_config.LANGSMITH_PROJECT)
