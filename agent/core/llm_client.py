"""LLM 클라이언트 — Upstage Solar 및 OpenAI 호환 API를 지원한다."""

import asyncio
import logging
import os
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI
from langchain_upstage import ChatUpstage
from pydantic import BaseModel, SecretStr

from agent.core.config import agent_config

logger = logging.getLogger(__name__)

_llm_cache: dict[float, BaseChatModel] = {}
_llm_semaphore = asyncio.Semaphore(4)  # 동시 LLM 호출 최대 4개 (t3.small 기준)


def get_llm(temperature: float | None = None) -> BaseChatModel:
    """temperature별로 캐시된 LLM 인스턴스를 반환한다."""
    temp = temperature if temperature is not None else agent_config.LLM_TEMPERATURE
    if temp not in _llm_cache:
        _llm_cache[temp] = _build_llm(temp)
    return _llm_cache[temp]


def _build_llm(temperature: float) -> BaseChatModel:
    """주어진 temperature로 LLM 인스턴스를 생성한다."""
    _model_lower = agent_config.LLM_MODEL.lower()
    is_gemini = "gemini" in _model_lower

    if not agent_config.LLM_API_KEY and not is_gemini:
        raise RuntimeError("LLM_API_KEY가 설정되지 않았습니다. 루트 .env 파일을 확인하세요.")

    # 라이브러리 호환성을 위해 환경 변수 명시적 설정
    # Gemini 등 일부 API에서 중복 인증 에러가 발생하므로, 기존 환경 변수가 있다면 모두 제거합니다.
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("GOOGLE_API_KEY", None)

    llm: BaseChatModel

    # 1. Google Vertex AI (Gemini 모델)
    if is_gemini:
        if not agent_config.GCP_PROJECT_ID:
            logger.warning(
                "GCP_PROJECT_ID가 설정되지 않았습니다. Vertex AI 호출이 실패할 수 있습니다."
            )

        llm = ChatVertexAI(
            model_name=agent_config.LLM_MODEL,
            project=agent_config.GCP_PROJECT_ID,
            location=agent_config.GCP_LOCATION,
            temperature=temperature,
            max_output_tokens=agent_config.LLM_MAX_TOKENS,
        )
        logger.info(
            "Vertex AI 초기화: model=%s project=%s location=%s",
            agent_config.LLM_MODEL,
            agent_config.GCP_PROJECT_ID,
            agent_config.GCP_LOCATION,
        )
    # 2. Upstage Solar 모델
    elif "solar" in _model_lower:
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

    _sem_t0 = asyncio.get_event_loop().time()
    logger.info(
        "[LLM] semaphore 대기 시작 (available=%d/%d)",
        _llm_semaphore._value,  # type: ignore[attr-defined]
        2,
    )
    async with _llm_semaphore:
        _sem_wait = asyncio.get_event_loop().time() - _sem_t0
        logger.info("[LLM] semaphore 획득 (wait=%.2fs)", _sem_wait)
        try:
            # 메시지 크기(프롬프트 총 길이) 측정 — 느린 호출 진단용
            _prompt_chars = sum(len(str(getattr(m, "content", ""))) for m in messages)
            logger.info("[LLM] ainvoke 호출 (prompt_chars=%d)", _prompt_chars)
            _api_t0 = asyncio.get_event_loop().time()

            if structured_output is not None:
                logger.info("구조화된 응답 생성 시작 (%s)", structured_output.__name__)
                # provider별 structured_output 호출 방식:
                # - OpenAI / Solar: json_schema + strict 가 가장 정확
                # - Gemini (OpenAI 호환 엔드포인트): strict json_schema 미지원 →
                #   function_calling 사용. 네이티브 google SDK 로 넘어갈 때까지는 호환 모드.
                _model_lower = agent_config.LLM_MODEL.lower()
                if "gemini" in _model_lower:
                    bound = llm.with_structured_output(structured_output, method="function_calling")
                else:
                    bound = llm.with_structured_output(
                        structured_output, method="json_schema", strict=True
                    )
                result = await asyncio.wait_for(bound.ainvoke(messages), timeout=timeout)
                logger.info(
                    "[LLM] ainvoke 응답 수신 (api=%.2fs, structured)",
                    asyncio.get_event_loop().time() - _api_t0,
                )
                logger.info("구조화된 응답 수신 완료")
                if result is None:
                    raise ValueError(
                        f"LLM이 {structured_output.__name__} 형식으로 응답하지 못했습니다."
                    )
                return cast(BaseModel, result)

            response = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
            logger.info(
                "[LLM] ainvoke 응답 수신 (api=%.2fs, plain)",
                asyncio.get_event_loop().time() - _api_t0,
            )
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
