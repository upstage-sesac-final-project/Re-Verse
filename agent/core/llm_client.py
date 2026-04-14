"""LLM 클라이언트 — Upstage Solar 및 OpenAI 호환 API를 지원한다."""

import asyncio
import logging
import os
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_upstage import ChatUpstage
from pydantic import BaseModel, SecretStr

from agent.core.config import agent_config

logger = logging.getLogger(__name__)

_llm_cache: dict[float, BaseChatModel] = {}
_llm_semaphore = asyncio.Semaphore(2)  # 동시 LLM 호출 최대 2개 (메모리 절약)


def get_llm(temperature: float | None = None) -> BaseChatModel:
    """temperature별로 캐시된 LLM 인스턴스를 반환한다."""
    temp = temperature if temperature is not None else agent_config.LLM_TEMPERATURE
    if temp not in _llm_cache:
        _llm_cache[temp] = _build_llm(temp)
    return _llm_cache[temp]


def _build_llm(temperature: float) -> BaseChatModel:
    """주어진 temperature로 LLM 인스턴스를 생성한다."""
    if not agent_config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY가 설정되지 않았습니다. 루트 .env 파일을 확인하세요.")

    # 라이브러리 호환성을 위해 환경 변수 명시적 설정
    os.environ["UPSTAGE_API_KEY"] = agent_config.LLM_API_KEY
    os.environ["OPENAI_API_KEY"] = agent_config.LLM_API_KEY

    llm: BaseChatModel

    # Upstage Solar 모델인 경우 전용 클래스 사용 (function_calling 호환성 최적화)
    if "solar" in agent_config.LLM_MODEL.lower():
        llm = ChatUpstage(
            api_key=SecretStr(agent_config.LLM_API_KEY),
            model=agent_config.LLM_MODEL,
            temperature=temperature,
        )
        logger.info(
            "Upstage 전용 LLM 초기화: model=%s temperature=%.1f",
            agent_config.LLM_MODEL,
            temperature,
        )
    else:
        # 기타 OpenAI 호환 모델
        init_kwargs: dict[str, Any] = {
            "api_key": SecretStr(agent_config.LLM_API_KEY),
            "model": agent_config.LLM_MODEL,
            "max_tokens": agent_config.LLM_MAX_TOKENS,
            "temperature": temperature,
        }
        if agent_config.LLM_BASE_URL:
            init_kwargs["base_url"] = agent_config.LLM_BASE_URL

        llm = ChatOpenAI(**init_kwargs)
        logger.info(
            "OpenAI 호환 LLM 초기화: model=%s temperature=%.1f", agent_config.LLM_MODEL, temperature
        )

    return llm


async def invoke_llm(
    messages: list[BaseMessage],
    structured_output: type[BaseModel] | None = None,
    temperature: float | None = None,
) -> str | BaseModel:
    """LLM을 비동기 호출한다.

    Args:
        messages: LangChain 메시지 목록
        structured_output: 지정하면 해당 Pydantic 모델로 파싱된 결과를 반환
        temperature: 호출별 temperature. None이면 config 기본값 사용

    Returns:
        structured_output 미지정 시 str, 지정 시 해당 Pydantic 인스턴스
    """
    llm = get_llm(temperature)
    timeout = agent_config.LLM_TIMEOUT

    async with _llm_semaphore:
        try:
            if structured_output is not None:
                logger.info("구조화된 응답 생성 시작 (%s)", structured_output.__name__)
                bound = llm.with_structured_output(
                    structured_output, method="json_schema", strict=True
                )
                result = await asyncio.wait_for(bound.ainvoke(messages), timeout=timeout)
                logger.info("구조화된 응답 수신 완료")
                if result is None:
                    raise ValueError(
                        f"LLM이 {structured_output.__name__} 형식으로 응답하지 못했습니다."
                    )
                return cast(BaseModel, result)

            response = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
            return cast(str, response.content)

        except TimeoutError:
            logger.error("LLM 호출 타임아웃 (%ds 초과) [%s]", timeout, agent_config.LLM_MODEL)
            raise
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
    """캐시를 초기화한다. 런타임 설정 변경 후 재초기화 시 사용."""
    _llm_cache.clear()
