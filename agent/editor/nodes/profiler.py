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
from agent.editor.prompts.profiler_prompt import (
    build_profiler_system_prompt,
    build_profiler_user_prompt,
)
from agent.utils.game_data_io import get_game_data_dir

logger = logging.getLogger(__name__)

# SKIP_FILES 는 agent.constants 에서 import

# ──────────────────────────────────────────────
# 스키마 레퍼런스 로더 — rpgmaker-mz-data-schema-update.md 에서
# target_file 에 해당하는 섹션만 추출하여 프롬프트에 주입한다.
# 모듈 로드 시 한 번만 파싱하고 dict 로 캐싱.
# ──────────────────────────────────────────────

_SCHEMA_REF_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "rpgmaker-mz-data-schema-update.md"
)

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
        "[Profiler] 스키마 레퍼런스 로드 완료: %d 섹션",
        len(_SCHEMA_SECTIONS),
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


# ── Task 19: parsed_command.value 강제 주입 ──────────────────────────────
# property 한국어 라벨 → (target_file, field_path) 매핑.
# field_path 는 dict 키 (예: "price") 또는 params[i] 형태 ("params[0]").

_PROPERTY_FIELD_MAP: dict[str, dict[str, str]] = {
    "Weapons.json": {
        "이름": "name",
        "설명": "description",
        "가격": "price",
        "hp": "params[0]",
        "체력": "params[0]",
        "mp": "params[1]",
        "마력": "params[1]",
        "공격": "params[2]",
        "공격력": "params[2]",
        "방어": "params[3]",
        "방어력": "params[3]",
        "마법공격력": "params[4]",
        "마법방어력": "params[5]",
        "민첩": "params[6]",
        "민첩성": "params[6]",
        "운": "params[7]",
    },
    "Armors.json": {
        "이름": "name",
        "설명": "description",
        "가격": "price",
        "hp": "params[0]",
        "체력": "params[0]",
        "mp": "params[1]",
        "마력": "params[1]",
        "공격": "params[2]",
        "공격력": "params[2]",
        "방어": "params[3]",
        "방어력": "params[3]",
    },
    "Enemies.json": {
        "이름": "name",
        "hp": "params[0]",
        "체력": "params[0]",
        "mp": "params[1]",
        "공격": "params[2]",
        "공격력": "params[2]",
        "방어": "params[3]",
        "방어력": "params[3]",
        "경험치": "exp",
        "exp": "exp",
        "골드": "gold",
        "돈": "gold",
    },
    "Actors.json": {
        "이름": "name",
        "별명": "nickname",
        "설명": "profile",
        "레벨": "initialLevel",
        "초기레벨": "initialLevel",
        "최대레벨": "maxLevel",
    },
    "Items.json": {
        "이름": "name",
        "설명": "description",
        "가격": "price",
    },
}


def _coerce_value(raw: str) -> int | float | str:
    """value 문자열을 숫자로 변환 가능하면 변환."""
    raw = raw.strip()
    if not raw:
        return raw
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _set_by_path(target_info: dict, path: str, value: int | float | str) -> bool:
    """'params[2]' 또는 'price' 같은 경로로 target_info 에 값 세팅. 성공 시 True."""
    import re as _re

    m = _re.match(r"^(\w+)\[(\d+)\]$", path)
    if m:
        key, idx = m.group(1), int(m.group(2))
        arr = target_info.get(key)
        if not isinstance(arr, list):
            # 길이 8 의 0 배열 생성 (params 는 길이 8)
            arr = [0] * 8
            target_info[key] = arr
        while len(arr) <= idx:
            arr.append(0)
        arr[idx] = value
        return True
    # 단순 키
    target_info[path] = value
    return True


def _inject_parsed_command_value(
    step: dict, parsed_command: dict | None
) -> dict:
    """step.target_info 에 parsed_command.property/value 를 강제 주입.

    user_input 에서 "공격력 50" 같은 명시적 값이 LLM profile 에 의해 덮이지 않도록
    profile_one **이후** 호출해 우선순위 역전.
    """
    if not parsed_command:
        return step
    prop = (parsed_command.get("property") or "").strip()
    val_str = str(parsed_command.get("value") or "").strip()
    if not prop or not val_str:
        return step
    target_file = step.get("target_file", "")
    mapping = _PROPERTY_FIELD_MAP.get(target_file)
    if not mapping:
        return step
    field_path = mapping.get(prop.lower()) or mapping.get(prop)
    if not field_path:
        return step
    target_info = dict(step.get("target_info") or {})
    value = _coerce_value(val_str)
    if _set_by_path(target_info, field_path, value):
        logger.info(
            "[Profiler] parsed_command.value 강제 주입: %s.%s = %r",
            target_file,
            field_path,
            value,
        )
    step = dict(step)
    step["target_info"] = target_info
    return step


async def profiler(state: dict) -> dict:
    """Profiler node entry point.

    execution_plan 내 create step 에 _needs_profiling=True 인 것들에 대해 LLM 호출.

    Phase D+E 통합에서 `filled_values` 출력 추가. planner 가 내려준
    `fill_slots` 에 대응하는 step 에 대해, LLM 결과를 `filled_values[step_id]`
    에 저장하여 YB.md 5-2 contract 맞춤. 기존 `target_info` merge 는 유지
    (executor 호환).
    """
    import time

    _t0 = time.perf_counter()
    logger.info("─── Profiler START ─────────────────────────────────")

    plan: list[dict] = state.get("execution_plan", [])
    game_id: str = state.get("game_id", "")
    fill_slots: list[dict] = state.get("fill_slots", []) or []
    parsed_command: dict = state.get("parsed_command", {}) or {}

    # step_id 가 fill_slots 에 포함된 set (새 contract 대상)
    fill_targeted_sids: set[int] = set()
    for slot in fill_slots:
        sid = slot.get("step_id")
        if sid is not None:
            try:
                fill_targeted_sids.add(int(sid))
            except (TypeError, ValueError):
                continue

    enriched_plan = list(plan)  # shallow copy
    filled_values: dict[int, dict] = {}
    profiled_count = 0
    for idx, step in enumerate(enriched_plan):
        if not step.get("_needs_profiling"):
            continue
        target_file = step.get("target_file", "")
        if target_file in SKIP_FILES:
            continue
        before_keys = set((step.get("target_info") or {}).keys())
        enriched = await profile_one(step, game_id=game_id)
        # Task 19: LLM 결과 뒤에 parsed_command.value 강제 주입 (명시 값이 덮이지 않도록)
        enriched = _inject_parsed_command_value(enriched, parsed_command)
        enriched_plan[idx] = enriched
        profiled_count += 1

        # filled_values 생성 — LLM 이 새로 넣은 키만 추려 YB.md contract 에 맞춘다
        try:
            sid = int(enriched.get("step_id", -1))
        except (TypeError, ValueError):
            continue
        if sid < 0:
            continue
        if sid not in fill_targeted_sids:
            # fill_slots 대상이 아니면 filled_values 채우지 않음 (기존 경로)
            continue
        after_info = enriched.get("target_info") or {}
        new_values = {k: v for k, v in after_info.items() if k not in before_keys}
        if new_values:
            filled_values[sid] = new_values

    elapsed = time.perf_counter() - _t0
    logger.info(
        "─── Profiler END (elapsed=%.2fs, profiled=%d/%d, fill_slot_steps=%d) ──",
        elapsed,
        profiled_count,
        len(plan),
        len(filled_values),
    )
    return {
        "execution_plan": enriched_plan,
        "filled_values": filled_values,
    }


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

    # 기존 엔티티 예시 가져오기 (병목 해결을 위해 비활성화)
    # examples = _get_existing_examples(game_id, target_file)
    examples = []
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
