"""이벤트 기획자 프롬프트용 RAG 컨텍스트 조회."""

import logging

from agent.rag.knowledge_retriever import knowledge_retriever

logger = logging.getLogger(__name__)


def get_event_planner_context(map_type: str) -> str:
    """이벤트 기획자 프롬프트에 주입할 RAG 컨텍스트 반환.

    Returns empty string on error so callers don't need to guard.
    """
    query = f"RPG Maker MZ {map_type} map events DSL command codes examples"
    try:
        return knowledge_retriever.retrieve_knowledge(query, k=3)
    except Exception as exc:
        logger.warning("RAG 컨텍스트 조회 실패: %s", exc)
        return ""
