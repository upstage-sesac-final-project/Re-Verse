"""Semantic judge — operation 단위로 결과의 의미적 적합성을 판정한다."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from agent.editor.prompts.validator_prompt import build_judge_system_prompt, build_judge_user_prompt
from agent.utils.traits_reference import (
    describe_effects_list,
    describe_params,
    describe_traits_list,
)

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
            judgment.get("match"),
            judgment.get("confidence", 0),
            judgment.get("reason", "")[:80],
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

        # MCP executor 경로는 data 를 안 남기는 경우가 있다.
        # 이때 entity_id + target_file 로 실제 파일에서 읽어 보강.
        if not isinstance(data, dict) and entry.get("entity_id") is not None:
            data = _load_entity_from_file(game_id, target, entry["entity_id"])

        if isinstance(data, dict):
            summary_parts = [f"step {sid} ({target}.{action}): 성공"]
            if data.get("name"):
                summary_parts.append(f"  이름: {data['name']}")

            # 능력치
            params = data.get("params")
            if isinstance(params, list) and len(params) >= 8:
                summary_parts.append(f"  능력치: {', '.join(describe_params(params))}")

            # traits
            traits = data.get("traits")
            if isinstance(traits, list) and traits:
                for t_desc in describe_traits_list(traits):
                    summary_parts.append(f"  trait: {t_desc}")

            # effects
            effects = data.get("effects")
            if isinstance(effects, list) and effects:
                for e_desc in describe_effects_list(effects):
                    summary_parts.append(f"  effect: {e_desc}")

            # learnings
            learnings = data.get("learnings")
            if isinstance(learnings, list) and learnings:
                for lr in learnings:
                    if isinstance(lr, dict):
                        summary_parts.append(
                            f"  learning: Lv.{lr.get('level', '?')} → skillId={lr.get('skillId', '?')}"
                        )

            # actions
            actions = data.get("actions")
            if isinstance(actions, list) and actions:
                for act in actions:
                    if isinstance(act, dict):
                        summary_parts.append(
                            f"  action: skillId={act.get('skillId', '?')} rating={act.get('rating', '?')}"
                        )

            # dropItems
            drop_items = data.get("dropItems")
            if isinstance(drop_items, list):
                for di in drop_items:
                    if isinstance(di, dict) and di.get("kind", 0) > 0:
                        summary_parts.append(
                            f"  dropItem: kind={di.get('kind')} dataId={di.get('dataId')} 1/{di.get('denominator', '?')}"
                        )

            # equips — ID를 이름으로 변환하여 judge 가 판단 가능하게
            equips = data.get("equips")
            if isinstance(equips, list):
                equip_descs = _describe_equips(equips, game_id)
                summary_parts.append(f"  equips: {equip_descs}")

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


def _describe_equips(equips: list, game_id: str) -> str:
    """equips 배열의 ID를 게임 데이터에서 실제 이름으로 변환."""
    try:
        from agent.utils.game_data_io import read_game_json

        # equipTypes 로 슬롯 이름
        system = read_game_json(game_id, "System.json")
        equip_types = system.get("equipTypes", []) if isinstance(system, dict) else []

        # Weapons + Armors 로 장비 이름 lookup
        weapons = read_game_json(game_id, "Weapons.json") or []
        armors = read_game_json(game_id, "Armors.json") or []

        parts = []
        for slot_idx, item_id in enumerate(equips):
            slot_name = equip_types[slot_idx] if slot_idx < len(equip_types) else f"슬롯{slot_idx}"
            if not item_id or item_id == 0:
                parts.append(f"{slot_name}=없음")
                continue

            # 슬롯 0=무기 → Weapons, 나머지 → Armors
            name = "?"
            if slot_idx == 0:
                for w in weapons:
                    if isinstance(w, dict) and w.get("id") == item_id:
                        name = w.get("name", "?")
                        break
            else:
                for a in armors:
                    if isinstance(a, dict) and a.get("id") == item_id:
                        name = a.get("name", "?")
                        break

            parts.append(f"{slot_name}={name}(id={item_id})")

        return "[" + ", ".join(parts) + "]"
    except Exception:
        return str(equips)


def _load_entity_from_file(game_id: str, target_file: str, entity_id: int) -> dict | None:
    """게임 파일에서 entity_id 에 해당하는 엔트리를 직접 읽어온다."""
    try:
        from agent.utils.game_data_io import read_game_json

        data = read_game_json(game_id, target_file)
        if not isinstance(data, list):
            return None
        for entry in data:
            if isinstance(entry, dict) and entry.get("id") == entity_id:
                return entry
    except Exception:
        pass
    return None
