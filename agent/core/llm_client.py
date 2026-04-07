"""LLM 클라이언트 — Upstage Solar 및 OpenAI 호환 API를 지원한다."""

import asyncio
import json
import logging
import os
import re
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_upstage import ChatUpstage
from pydantic import BaseModel, SecretStr

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
    """AgentConfig 설정으로 적절한 LLM 인스턴스를 생성한다."""
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
            temperature=agent_config.LLM_TEMPERATURE,
            max_tokens=agent_config.LLM_MAX_TOKENS,
        )
        logger.info(
            "Upstage 전용 LLM 초기화: model=%s, max_tokens=%d",
            agent_config.LLM_MODEL,
            agent_config.LLM_MAX_TOKENS,
        )
    else:
        # 기타 OpenAI 호환 모델
        init_kwargs: dict[str, Any] = {
            "api_key": SecretStr(agent_config.LLM_API_KEY),
            "model": agent_config.LLM_MODEL,
            "max_tokens": agent_config.LLM_MAX_TOKENS,
            "temperature": agent_config.LLM_TEMPERATURE,
        }
        if agent_config.LLM_BASE_URL:
            init_kwargs["base_url"] = agent_config.LLM_BASE_URL

        llm = ChatOpenAI(**init_kwargs)
        logger.info("OpenAI 호환 LLM 초기화: model=%s", agent_config.LLM_MODEL)

    return llm


async def invoke_llm(
    messages: list[BaseMessage],
    structured_output: type[BaseModel] | None = None,
    timeout: float | None = None,
) -> str | BaseModel:
    """LLM을 비동기 호출한다.

    Args:
        messages: LangChain 메시지 목록
        structured_output: 지정하면 해당 Pydantic 모델로 파싱된 결과를 반환
        timeout: 초 단위 타임아웃 (None이면 무제한)

    Returns:
        structured_output 미지정 시 str, 지정 시 해당 Pydantic 인스턴스
    """
    llm = get_llm()

    try:
        if structured_output is not None:
            logger.info("구조화된 응답 생성 시작 (%s)", structured_output.__name__)
            bound = llm.with_structured_output(structured_output, method="function_calling")
            coro = bound.ainvoke(messages)
            result = await (asyncio.wait_for(coro, timeout=timeout) if timeout else coro)
            logger.info("구조화된 응답 수신 완료")
            if result is None:
                raise ValueError(
                    f"LLM이 {structured_output.__name__} 형식으로 응답하지 못했습니다."
                )
            return cast(BaseModel, result)

        coro = llm.ainvoke(messages)
        response = await (asyncio.wait_for(coro, timeout=timeout) if timeout else coro)
        return cast(str, response.content)

    except TimeoutError:
        logger.error("LLM 호출 타임아웃 [%s]: %.0fs 초과", agent_config.LLM_MODEL, timeout)
        raise TimeoutError(f"LLM 응답 타임아웃: {timeout}초 초과 ({agent_config.LLM_MODEL})")
    except Exception as e:
        logger.error("LLM 호출 실패 [%s]: %s", agent_config.LLM_MODEL, e)
        raise


async def invoke_llm_json(
    messages: list[BaseMessage],
    model: type[BaseModel],
    timeout: float | None = None,
) -> BaseModel:
    """LLM에게 JSON 텍스트로 응답받아 Pydantic 모델로 파싱한다.

    function_calling 대신 순수 텍스트 JSON 방식을 사용하므로
    복잡한 스키마(GameBlueprint 등)에서 더 안정적이다.
    """
    llm = get_llm()
    logger.info("JSON 텍스트 응답 생성 시작 (%s)", model.__name__)

    try:
        coro = llm.ainvoke(messages)
        response = await (asyncio.wait_for(coro, timeout=timeout) if timeout else coro)
        raw = str(response.content)
        logger.info("JSON 텍스트 응답 수신 완료 (%d chars)", len(raw))

        parsed = _extract_and_parse_json(raw, model)
        return parsed

    except TimeoutError:
        logger.error("LLM 호출 타임아웃 [%s]: %.0fs 초과", agent_config.LLM_MODEL, timeout)
        raise TimeoutError(f"LLM 응답 타임아웃: {timeout}초 초과 ({agent_config.LLM_MODEL})")
    except Exception as e:
        logger.error("LLM JSON 응답 처리 실패 [%s]: %s", agent_config.LLM_MODEL, e)
        raise


def _extract_and_parse_json(text: str, model: type[BaseModel]) -> BaseModel:
    """응답 텍스트에서 JSON을 추출해 Pydantic 모델로 파싱한다."""
    original = text

    # ```json ... ``` 또는 ``` ... ``` 코드블록 제거
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block:
        text = code_block.group(1).strip()
    else:
        # 첫 번째 { 부터 마지막 } 까지만 추출
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        else:
            raise ValueError(f"JSON 블록을 찾을 수 없음. 응답 앞 200자: {original[:200]}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # LLM이 문자열 내부에 리터럴 개행/탭 등 제어문자를 삽입하는 경우 재시도
        try:
            data = json.loads(text, strict=False)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 실패: {e}. 앞 200자: {text[:200]}") from e

    try:
        return model.model_validate(data)
    except Exception as e:
        logger.error("Pydantic 검증 실패 (%s): %s", model.__name__, e)
        raise ValueError(f"Pydantic 검증 실패 ({model.__name__}): {e}") from e


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
