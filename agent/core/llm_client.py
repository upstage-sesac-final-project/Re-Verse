"""LLM 클라이언트 — OpenAI 호환 API를 통합 지원한다.

Solar, OpenAI, vLLM 등 OpenAI 호환 모든 API를 ChatOpenAI 하나로 처리한다.
프로바이더 전환은 .env 의 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY 만 수정하면 된다.

사용 예시:
    from agent.core.llm_client import invoke_llm, invoke_llm_simple

    # 단순 호출
    text = await invoke_llm_simple("시스템 프롬프트", "유저 메시지")

    # Structured Output
    result: MyModel = await invoke_llm(messages, structured_output=MyModel)
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent.core.config import agent_config

logger = logging.getLogger(__name__)

_llm: BaseChatModel | None = None


def get_llm() -> BaseChatModel:
    """싱글톤 LLM 인스턴스를 반환한다."""
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm


def _build_llm() -> BaseChatModel:
    """AgentConfig 설정으로 ChatOpenAI 인스턴스를 생성한다."""
    if not agent_config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY가 설정되지 않았습니다. 루트 .env 파일을 확인하세요.")

    init_kwargs: dict[str, Any] = {
        "api_key": agent_config.LLM_API_KEY,
        "model": agent_config.LLM_MODEL,
        "max_tokens": agent_config.LLM_MAX_TOKENS,
        "temperature": agent_config.LLM_TEMPERATURE,
    }
    if agent_config.LLM_BASE_URL:
        init_kwargs["base_url"] = agent_config.LLM_BASE_URL

    llm = ChatOpenAI(**init_kwargs)
    logger.info(
        "LLM 초기화: model=%s, base_url=%s",
        agent_config.LLM_MODEL,
        agent_config.LLM_BASE_URL or "(OpenAI 기본)",
    )
    return llm


async def invoke_llm(
    messages: list[BaseMessage],
    structured_output: type[BaseModel] | None = None,
) -> str | BaseModel:
    """LLM을 비동기 호출한다.

    Args:
        messages: LangChain 메시지 목록
        structured_output: 지정하면 해당 Pydantic 모델로 파싱된 결과를 반환

    Returns:
        structured_output 미지정 시 str, 지정 시 해당 Pydantic 인스턴스
    """
    llm = get_llm()

    try:
        if structured_output is not None:
            bound = llm.with_structured_output(structured_output)
            result = await bound.ainvoke(messages)
            if result is None:
                raise ValueError(
                    f"LLM이 {structured_output.__name__} 형식으로 응답하지 못했습니다."
                )
            return result

        response = await llm.ainvoke(messages)
        return response.content

    except Exception as e:
        logger.error("LLM 호출 실패 [%s]: %s", agent_config.LLM_MODEL, e)
        raise


async def invoke_llm_simple(system_prompt: str, user_message: str) -> str:
    """시스템 + 유저 메시지로 LLM을 호출하는 편의 함수."""
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    result = await invoke_llm(messages)
    return str(result)


def reset_llm() -> None:
    """싱글톤을 초기화한다. 런타임 설정 변경 후 재초기화 시 사용."""
    global _llm
    _llm = None
