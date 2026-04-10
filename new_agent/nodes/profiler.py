"""Profiler node — create step 의 의미적 필드를 LLM 으로 채운다.

"슬라임" → 물리 내성, 화염 약점 등.
"치유의 목걸이" → HP 회복 trait 등.

step 단위로 독립 호출 가능: profile_one(step, feedback)
→ validator 의 partial retry 에서 실패한 step 만 재호출.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from app.backend.core.game_paths import get_game_data_path
from new_agent.prompts import build_profiler_system_prompt, build_profiler_user_prompt

logger = logging.getLogger(__name__)

# profiler 가 skip 하는 파일 (create 가 필요 없거나 의미적 생성이 불필요)
_SKIP_FILES = frozenset({"System.json", "MapInfos.json", "Map"})

# 파일별 주요 필드 스키마 발췌 (프롬프트용)
_SCHEMA_EXCERPTS: dict[str, str] = {
    "Enemies.json": (
        "필수: name, params(8개 정수배열), traits([{code,dataId,value}]), exp(정수), gold(정수), "
        "actions([{conditionParam1:정수, conditionParam2:정수, conditionType:정수(0~6), rating:정수(1~9), skillId:정수}]), "
        "dropItems([{dataId:정수, denominator:정수, kind:정수(0=없음,1=아이템,2=무기,3=방어구)}] 3개 고정). "
        "주의: actions/dropItems 의 모든 필드는 반드시 정수(int)여야 함. float 금지."
    ),
    "Actors.json": "필수: name, classId, equips(5개 정수배열), traits, initialLevel, maxLevel, profile",
    "Armors.json": "필수: name, atypeId, etypeId, price, params(8개 정수배열), traits, description",
    "Weapons.json": "필수: name, wtypeId, etypeId, price, params(8개 정수배열), traits, description",
    "Skills.json": "필수: name, stypeId, mpCost, scope, damage({type,elementId,formula}), effects, description",
    "Items.json": "필수: name, itypeId, price, scope, effects, description",
    "Classes.json": "필수: name, params(100레벨x8스탯 배열), traits, learnings, expParams",
    "States.json": "필수: name, priority, traits, restriction",
}


async def profiler(state: dict) -> dict:
    """Profiler node entry point.

    execution_plan 내 create step 에 _needs_profiling=True 인 것들에 대해 LLM 호출.
    """
    plan: list[dict] = state.get("execution_plan", [])
    game_id: str = state.get("game_id", "")

    enriched_plan = list(plan)  # shallow copy
    for idx, step in enumerate(enriched_plan):
        if not step.get("_needs_profiling"):
            continue
        target_file = step.get("target_file", "")
        if target_file in _SKIP_FILES:
            continue
        enriched = await profile_one(step, game_id=game_id)
        enriched_plan[idx] = enriched

    return {"execution_plan": enriched_plan}


async def profile_one(
    step: dict,
    game_id: str = "",
    feedback: str | None = None,
) -> dict:
    """단일 create step 의 target_info 를 의미적으로 채운다.

    validator 의 partial retry 에서도 직접 호출된다.
    """
    target_file = step.get("target_file", "")
    target_info = dict(step.get("target_info") or {})

    # 기존 엔티티 예시 가져오기
    examples = _get_existing_examples(game_id, target_file)
    schema_excerpt = _SCHEMA_EXCERPTS.get(target_file, "")

    system_prompt = build_profiler_system_prompt()
    user_prompt = build_profiler_user_prompt(step, schema_excerpt, examples, feedback)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        result = await invoke_llm(messages)
        response_text = str(result)
        enriched_info = _parse_json_from_response(response_text)
        if enriched_info:
            # LLM 이 생성한 필드를 기존 target_info 위에 merge
            for k, v in enriched_info.items():
                if v is not None:
                    target_info[k] = v
    except Exception as e:
        logger.error("[profiler] LLM 호출 실패 step=%s: %s", step.get("step_id"), e)

    # LLM 출력 후처리 — 알려진 정수 필드를 강제 변환
    _coerce_int_fields(target_info, target_file)

    enriched_step = dict(step)
    enriched_step["target_info"] = target_info
    enriched_step.pop("_needs_profiling", None)

    logger.info(
        "[profiler] step=%s file=%s name='%s' fields=%s",
        step.get("step_id"),
        target_file,
        target_info.get("name", "?"),
        sorted(target_info.keys()),
    )
    return enriched_step


def _get_existing_examples(game_id: str, target_file: str) -> list[dict]:
    """해당 파일에서 잘 채워진 기존 엔트리 1~2개를 가져온다."""
    if not game_id:
        return []
    try:
        data_path = get_game_data_path(game_id)
        fp = data_path / target_file
        if not fp.exists():
            return []
        data = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        examples = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if not entry.get("name"):
                continue
            examples.append(entry)
            if len(examples) >= 2:
                break
        return examples
    except Exception:
        return []


def _parse_json_from_response(text: str) -> dict | None:
    """LLM 응답에서 JSON dict 추출. markdown 코드블록 포함 처리."""
    text = text.strip()
    # ```json ... ``` 패턴 처리
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
    # 직접 JSON 파싱
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return None


# ──────────────────────────────────────────────
# 후처리 — LLM 이 잘못 넣은 타입을 강제 보정
# ──────────────────────────────────────────────

# 반드시 int 여야 하는 중첩 필드들
_INT_FIELDS_IN_ACTIONS = {"conditionParam1", "conditionParam2", "conditionType", "rating", "skillId"}
_INT_FIELDS_IN_DROP_ITEMS = {"dataId", "denominator", "kind"}
_INT_FIELDS_IN_LEARNINGS = {"level", "skillId"}
_INT_TOP_LEVEL = {"exp", "gold", "price", "stypeId", "mpCost", "tpCost", "scope",
                  "occasion", "hitType", "successRate", "repeats", "tpGain",
                  "animationId", "itypeId", "wtypeId", "etypeId", "atypeId",
                  "classId", "initialLevel", "maxLevel", "iconIndex",
                  "restriction", "priority"}


def _coerce_int_fields(info: dict, target_file: str) -> None:
    """알려진 정수 필드에 float 이 들어왔으면 int 로 변환."""
    # top-level
    for key in _INT_TOP_LEVEL:
        if key in info and isinstance(info[key], float):
            info[key] = int(info[key])

    # params
    if isinstance(info.get("params"), list):
        info["params"] = [int(v) if isinstance(v, float) else v for v in info["params"]]

    # actions
    if isinstance(info.get("actions"), list):
        for act in info["actions"]:
            if isinstance(act, dict):
                for k in _INT_FIELDS_IN_ACTIONS:
                    if k in act and isinstance(act[k], float):
                        act[k] = int(act[k])

    # dropItems
    if isinstance(info.get("dropItems"), list):
        for item in info["dropItems"]:
            if isinstance(item, dict):
                for k in _INT_FIELDS_IN_DROP_ITEMS:
                    if k in item and isinstance(item[k], float):
                        item[k] = int(item[k])

    # learnings
    if isinstance(info.get("learnings"), list):
        for lr in info["learnings"]:
            if isinstance(lr, dict):
                for k in _INT_FIELDS_IN_LEARNINGS:
                    if k in lr and isinstance(lr[k], float):
                        lr[k] = int(lr[k])

    # equips
    if isinstance(info.get("equips"), list):
        info["equips"] = [int(v) if isinstance(v, float) else v for v in info["equips"]]
