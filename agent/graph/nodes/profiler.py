"""Profiler node — create step 의 의미적 필드를 LLM 으로 채운다.

"슬라임" → 물리 내성, 화염 약점 등.
"치유의 목걸이" → HP 회복 trait 등.

step 단위로 독립 호출 가능: profile_one(step, feedback)
→ validator 의 partial retry 에서 실패한 step 만 재호출.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.constants import (
    FILE_NEEDS_COMMON,
    INT_FIELDS_IN_ACTIONS,
    INT_FIELDS_IN_DROP_ITEMS,
    INT_FIELDS_IN_LEARNINGS,
    INT_FIELDS_TOP_LEVEL,
    SKIP_FILES,
)
from agent.core.llm_client import invoke_llm
from agent.utils.game_data_io import get_game_data_dir
from agent.prompts.profiler_prompt import build_profiler_system_prompt, build_profiler_user_prompt

logger = logging.getLogger(__name__)

# SKIP_FILES 는 agent.constants 에서 import

# ──────────────────────────────────────────────
# 스키마 레퍼런스 로더 — rpgmaker-mz-data-schema-update.md 에서
# target_file 에 해당하는 섹션만 추출하여 프롬프트에 주입한다.
# 모듈 로드 시 한 번만 파싱하고 dict 로 캐싱.
# ──────────────────────────────────────────────

_SCHEMA_REF_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rpgmaker-mz-data-schema-update.md"

# {section_header: section_text} — _load_schema_sections() 가 채움
_SCHEMA_SECTIONS: dict[str, str] = {}
# 공통 서브구조 텍스트 (Trait, Damage, Effect, scope 등)
_COMMON_SUB_SECTIONS: str = ""

# FILE_NEEDS_COMMON 는 agent.constants 에서 import


def _load_schema_sections() -> None:
    """md 파일을 ## 헤더 기준으로 파싱하여 _SCHEMA_SECTIONS 에 캐싱."""
    global _SCHEMA_SECTIONS, _COMMON_SUB_SECTIONS

    if _SCHEMA_SECTIONS:
        return  # 이미 로드됨

    if not _SCHEMA_REF_PATH.exists():
        logger.warning("[Profiler] 스키마 레퍼런스 파일 없음: %s", _SCHEMA_REF_PATH)
        return

    text = _SCHEMA_REF_PATH.read_text(encoding="utf-8")
    # ## 헤더 기준 분할
    parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)

    for part in parts:
        part = part.strip()
        if not part.startswith("## "):
            continue
        first_line = part.split("\n", 1)[0]
        header = first_line.removeprefix("## ").strip()

        if header == "공통 서브구조":
            _COMMON_SUB_SECTIONS = part
        elif header not in ("목차", "파일 공통 규칙"):
            _SCHEMA_SECTIONS[header] = part

    logger.info(
        "[Profiler] 스키마 레퍼런스 로드 완료: %d 섹션", len(_SCHEMA_SECTIONS),
    )


def get_schema_reference(target_file: str) -> str:
    """target_file 에 해당하는 스키마 레퍼런스 텍스트를 반환.

    해당 파일 섹션 + 필요한 공통 서브구조를 합쳐서 돌려준다.
    """
    _load_schema_sections()

    section = _SCHEMA_SECTIONS.get(target_file, "")
    if not section:
        return ""

    # 공통 서브구조 중 이 파일이 참조하는 부분만 추출
    needed = FILE_NEEDS_COMMON.get(target_file, [])
    common_parts: list[str] = []
    if needed and _COMMON_SUB_SECTIONS:
        # ### 헤더 기준으로 서브섹션 분할
        sub_parts = re.split(r"(?=^### )", _COMMON_SUB_SECTIONS, flags=re.MULTILINE)
        for sp in sub_parts:
            sp = sp.strip()
            if not sp.startswith("### "):
                continue
            sub_header = sp.split("\n", 1)[0].removeprefix("### ").strip()
            # "Trait", "Damage 구조", "Effect 구조", "scope (효과 범위)" 등
            for keyword in needed:
                if keyword.lower() in sub_header.lower():
                    common_parts.append(sp)
                    break

    result = section
    if common_parts:
        result += "\n\n---\n\n" + "\n\n".join(common_parts)

    return result


async def profiler(state: dict) -> dict:
    """Profiler node entry point.

    execution_plan 내 create step 에 _needs_profiling=True 인 것들에 대해 LLM 호출.
    """
    import time
    _t0 = time.perf_counter()
    logger.info("─── Profiler START ─────────────────────────────────")

    plan: list[dict] = state.get("execution_plan", [])
    game_id: str = state.get("game_id", "")

    enriched_plan = list(plan)  # shallow copy
    profiled_count = 0
    for idx, step in enumerate(enriched_plan):
        if not step.get("_needs_profiling"):
            continue
        target_file = step.get("target_file", "")
        if target_file in SKIP_FILES:
            continue
        enriched = await profile_one(step, game_id=game_id)
        enriched_plan[idx] = enriched
        profiled_count += 1

    elapsed = time.perf_counter() - _t0
    logger.info(
        "─── Profiler END (elapsed=%.2fs, profiled=%d/%d) ──────────",
        elapsed, profiled_count, len(plan),
    )
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
    schema_excerpt = get_schema_reference(target_file)

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
        logger.error("[Profiler] LLM 호출 실패 step=%s: %s", step.get("step_id"), e)

    # LLM 출력 후처리 — 알려진 정수 필드를 강제 변환
    _coerce_int_fields(target_info, target_file)

    enriched_step = dict(step)
    enriched_step["target_info"] = target_info
    enriched_step.pop("_needs_profiling", None)

    logger.info(
        "[Profiler] step=%s file=%s name='%s' fields=%s",
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
        data_path = Path(get_game_data_dir(game_id))
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

# 정수 필드 집합은 agent.constants 에서 import


def _coerce_int_fields(info: dict, target_file: str) -> None:
    """알려진 정수 필드에 float 이 들어왔으면 int 로 변환."""
    # top-level
    for key in INT_FIELDS_TOP_LEVEL:
        if key in info and isinstance(info[key], float):
            info[key] = int(info[key])

    # params
    if isinstance(info.get("params"), list):
        info["params"] = [int(v) if isinstance(v, float) else v for v in info["params"]]

    # actions
    if isinstance(info.get("actions"), list):
        for act in info["actions"]:
            if isinstance(act, dict):
                for k in INT_FIELDS_IN_ACTIONS:
                    if k in act and isinstance(act[k], float):
                        act[k] = int(act[k])

    # dropItems
    if isinstance(info.get("dropItems"), list):
        for item in info["dropItems"]:
            if isinstance(item, dict):
                for k in INT_FIELDS_IN_DROP_ITEMS:
                    if k in item and isinstance(item[k], float):
                        item[k] = int(item[k])

    # learnings
    if isinstance(info.get("learnings"), list):
        for lr in info["learnings"]:
            if isinstance(lr, dict):
                for k in INT_FIELDS_IN_LEARNINGS:
                    if k in lr and isinstance(lr[k], float):
                        lr[k] = int(lr[k])

    # equips
    if isinstance(info.get("equips"), list):
        info["equips"] = [int(v) if isinstance(v, float) else v for v in info["equips"]]
