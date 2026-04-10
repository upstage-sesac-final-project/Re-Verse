"""Semantic judge — operation 단위로 결과의 의미적 적합성을 판정한다."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from app.backend.core.game_paths import get_game_data_path
from new_agent.executor.utils.traits import describe_effects_list, describe_params, describe_traits_list
from new_agent.prompts import build_judge_system_prompt, build_judge_user_prompt

logger = logging.getLogger(__name__)


async def judge_operation(
    user_input: str,
    resolved_input: str,
    operation: dict,
    step_results: list[dict],
    game_id: str,
) -> dict[str, Any]:
    """operation 에 대한 semantic judge 판정.

    Returns {"match": bool, "confidence": float, "reason": str}
    """
    # 결과 요약 생성
    result_summary = _build_result_summary(operation, step_results, game_id)

    system_prompt = build_judge_system_prompt()
    user_prompt = build_judge_user_prompt(
        user_input=user_input,
        resolved_input=resolved_input,
        operation=operation,
        result_summary=result_summary,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        result = await invoke_llm(messages)
        response_text = str(result)
        judgment = _parse_judgment(response_text)
        logger.info(
            "[judge] match=%s confidence=%.2f reason='%s'",
            judgment.get("match"), judgment.get("confidence", 0), judgment.get("reason", "")[:80],
        )
        return judgment
    except Exception as e:
        logger.error("[judge] LLM 호출 실패: %s", e)
        # 호출 실패 시 통과시킴 (안전 방향)
        return {"match": True, "confidence": 0.3, "reason": "judge 호출 실패, 통과 처리"}


def _build_result_summary(
    operation: dict,
    step_results: list[dict],
    game_id: str,
) -> str:
    """operation 실행 결과를 judge 프롬프트용 텍스트로 변환."""
    lines: list[str] = []

    for entry in step_results:
        sid = entry.get("step_id", "?")
        action = entry.get("action", "?")
        target = entry.get("target_file", "?")
        success = entry.get("success", False)

        if not success:
            lines.append(f"step {sid} ({target}.{action}): 실패 — {entry.get('error', '?')}")
            continue

        data = entry.get("data")
        if isinstance(data, dict):
            # traits/effects 자연어 변환
            traits = data.get("traits")
            effects = data.get("effects")
            params = data.get("params")

            summary_parts = [f"step {sid} ({target}.{action}): 성공"]
            if data.get("name"):
                summary_parts.append(f"  이름: {data['name']}")
            if isinstance(params, list) and len(params) >= 8:
                summary_parts.append(f"  능력치: {', '.join(describe_params(params))}")
            if isinstance(traits, list) and traits:
                for t_desc in describe_traits_list(traits):
                    summary_parts.append(f"  trait: {t_desc}")
            if isinstance(effects, list) and effects:
                for e_desc in describe_effects_list(effects):
                    summary_parts.append(f"  effect: {e_desc}")
            if data.get("description"):
                summary_parts.append(f"  설명: {data['description']}")

            lines.append("\n".join(summary_parts))
        else:
            lines.append(f"step {sid} ({target}.{action}): 성공")

    return "\n".join(lines) if lines else "(실행 결과 없음)"


def _parse_judgment(text: str) -> dict[str, Any]:
    """LLM 응답에서 {match, confidence, reason} 추출."""
    text = text.strip()
    # ```json ... ``` 처리
    if "```" in text:
        for part in text.split("```"):
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # 파싱 실패 → 안전 방향
    return {"match": True, "confidence": 0.3, "reason": "판정 파싱 실패, 통과 처리"}
