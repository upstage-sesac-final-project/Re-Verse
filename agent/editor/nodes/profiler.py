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
        # Task 29: "직업" property 는 특수 처리 — Classes.json 을 db_lookup 해서
        # int classId 로 변환 후 주입. _apply_single_property 에서 감지.
        "직업": "classId",
        "클래스": "classId",
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


def _apply_single_property(
    target_info: dict,
    mapping: dict[str, str],
    prop: str,
    val_str: str,
    target_file: str,
    *,
    game_id: str = "",
) -> bool:
    """단일 (prop, val) 쌍을 target_info 에 주입. 성공 시 True.

    Task 29: Actors.json 의 "직업"/"클래스" property 는 db_lookup 으로 Classes.json
    에서 id 조회 후 int classId 로 주입. 못 찾으면 `_class_not_found` 힌트만 남김
    (validator 가 경고로 사용할 수 있게).
    """
    prop = (prop or "").strip()
    val_str = str(val_str or "").strip()
    if not prop or not val_str:
        return False
    field_path = mapping.get(prop.lower()) or mapping.get(prop)
    if not field_path:
        return False

    # "직업"/"클래스" 특수 처리 — 문자열 이름을 Classes.json 의 id 로 변환
    if target_file == "Actors.json" and field_path == "classId":
        class_id = _resolve_class_id(game_id, val_str)
        if class_id is None:
            # Task 33 / 36 follow-up: db 에 Class 가 없다는 건 같은 턴에 Class 를
            # 선행 create 하는 케이스. Profiler LLM 이 채운 잘못된 classId (기본
            # 1 등) 가 남아있으면 Actor 가 엉뚱한 Class 참조. None 으로 강제 덮어서
            # executor_v2 가 prev Class create 의 id 로 주입하도록 유도.
            logger.info(
                "[Profiler] 직업 '%s' 를 Classes.json 에서 찾지 못함 — classId=None 강제 "
                "(executor 가 prev Class create 에서 주입 예정)",
                val_str,
            )
            target_info["_class_not_found"] = val_str
            target_info["classId"] = None
            return False
        _set_by_path(target_info, "classId", class_id)
        logger.info(
            "[Profiler] 직업 '%s' → classId=%d 주입",
            val_str,
            class_id,
        )
        return True

    value = _coerce_value(val_str)
    if _set_by_path(target_info, field_path, value):
        logger.info(
            "[Profiler] parsed_command.value 강제 주입: %s.%s = %r",
            target_file,
            field_path,
            value,
        )
        return True
    return False


def _resolve_class_id(game_id: str, class_name: str) -> int | None:
    """Classes.json 에서 이름으로 id 조회. db_lookup 활용."""
    if not game_id or not class_name:
        return None
    try:
        from agent.editor.db_lookup import lookup_by_name

        result = lookup_by_name(game_id, "class", class_name)
        if result["status"] == "found" and result.get("exact_match"):
            return int(result["exact_match"]["id"])
        # ambiguous 인 경우 첫 candidate 를 사용할지 말지 — 안전하게 not_found 처리
        return None
    except Exception as e:  # pragma: no cover
        logger.warning("[Profiler] class 조회 실패: %s", e)
        return None


def _inject_parsed_command_value(
    step: dict, parsed_command: dict | None, *, game_id: str = ""
) -> dict:
    """step.target_info 에 parsed_command.property/value + additional_properties 를
    강제 주입.

    정책 (2026-04-19 sprint β):
    - 유저가 명시한 속성은 LLM 결과를 덮어쓴다
    - 유저가 지정 안 한 속성은 LLM/기본값 유지
    - 첫 속성: property/value
    - 나머지 속성들: additional_properties=[{property, value}, ...]

    user_input 에서 "체력 400, MP 30, 공격력 15" 같은 다중 지정이 LLM profile 에
    의해 일부 속성만 반영되는 사례 차단.

    Task 29: game_id 를 받아서 Actor.classId 를 Classes.json 에서 조회.
    """
    if not parsed_command:
        return step
    target_file = step.get("target_file", "")
    mapping = _PROPERTY_FIELD_MAP.get(target_file)
    if not mapping:
        return step

    target_info = dict(step.get("target_info") or {})

    # 1) 기본 property/value
    _apply_single_property(
        target_info,
        mapping,
        parsed_command.get("property") or "",
        str(parsed_command.get("value") or ""),
        target_file,
        game_id=game_id,
    )

    # 2) additional_properties 루프
    extras = parsed_command.get("additional_properties") or []
    if isinstance(extras, list):
        for item in extras:
            if not isinstance(item, dict):
                continue
            _apply_single_property(
                target_info,
                mapping,
                item.get("property") or "",
                str(item.get("value") or ""),
                target_file,
                game_id=game_id,
            )

    step = dict(step)
    step["target_info"] = target_info
    return step


def _inject_fixed_fields(step: dict) -> dict:
    """profile_one 호출 전에 fill_schema.fixed_fields 를 target_info 에 merge.

    이미 target_info 에 있는 키는 덮지 않음 (planner / definition 이 명시 세팅한 값 우선).
    """
    from agent.editor.nodes.planner.fill_schemas import get_fill_schema

    tf = step.get("target_file", "")
    schema = get_fill_schema(tf)
    if not schema:
        return step
    fixed = schema.get("fixed_fields") or {}
    if not fixed:
        return step
    target_info = dict(step.get("target_info") or {})
    added = False
    for k, v in fixed.items():
        if k not in target_info:
            target_info[k] = v
            added = True
    if added:
        step = dict(step)
        step["target_info"] = target_info
    return step


def _enforce_name_lock(original_step: dict, enriched_step: dict) -> dict:
    """LLM 이 target_info.name 을 엉뚱한 값 (기존 엔티티 복사 / hallucination) 으로
    덮는 경우 차단. planner 가 넣은 원본 name 을 유지.
    """
    original_name = (original_step.get("target_info") or {}).get("name")
    enriched_info = dict(enriched_step.get("target_info") or {})
    llm_name = enriched_info.get("name")
    if original_name and llm_name != original_name:
        logger.info(
            "[Profiler] name lock: LLM '%s' → 원본 '%s' 로 강제 복원",
            llm_name,
            original_name,
        )
        enriched_info["name"] = original_name
        enriched_step = dict(enriched_step)
        enriched_step["target_info"] = enriched_info
    return enriched_step


# Task 30 — LLM 이 RPG Maker MZ 기본 템플릿 (Actor1 nickname="용사" 등) 을 그대로
# 베껴오는 문제 차단. planner/definition 이 명시적으로 세팅했거나 비워둔 값은
# LLM 이 덮어쓰지 못하도록 파일별 lock 목록 정의.
_LOCKED_OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "Actors.json": (
        "nickname",
        "profile",
        # 이미지 관련 — user 가 명시적으로 지정 안 하면 LLM 이 "Actor1" 복사
        "faceName",
        "characterName",
        "battlerName",
    ),
    "Weapons.json": ("description", "note"),
    "Armors.json": ("description", "note"),
    "Items.json": ("description", "note"),
    "Skills.json": ("description", "note", "message1", "message2"),
    "Enemies.json": ("note",),
    "States.json": ("note", "message1", "message2", "message3", "message4"),
    "Classes.json": ("note",),
}


# ── Task 36: Classes.json rule-base profile ────────────────────────────
# Class.params 는 `list[list[int]]` 구조 (outer 8 고정, inner = 레벨별 곡선).
# LLM 이 이 구조를 일관되게 못 만들어 schema fail 반복 발생 (기사 직업 테스트에서
# 10 items flat list 로 만들어 validator retry 누적 → agent timeout).
# → Classes 생성은 rule-base 로 곡선 생성. LLM 호출 skip.

_CLASS_STAT_PROPERTY_TO_INDEX: dict[str, int] = {
    "hp": 0,
    "HP": 0,
    "체력": 0,
    "최대hp": 0,
    "최대체력": 0,
    "mp": 1,
    "MP": 1,
    "마나": 1,
    "최대mp": 1,
    "atk": 2,
    "ATK": 2,
    "공격": 2,
    "공격력": 2,
    "def": 3,
    "DEF": 3,
    "방어": 3,
    "방어력": 3,
    "mat": 4,
    "MAT": 4,
    "마공": 4,
    "마법공격력": 4,
    "mdf": 5,
    "MDF": 5,
    "마방": 5,
    "마법방어력": 5,
    "agi": 6,
    "AGI": 6,
    "민첩": 6,
    "민첩성": 6,
    "luk": 7,
    "LUK": 7,
    "운": 7,
}

# RPG Maker MZ 기본 Class "주인공" 등 기준. 레벨 1 표준 base.
_CLASS_STAT_DEFAULT_BASE: list[int] = [
    400,  # 0: MHP
    80,  # 1: MMP
    20,  # 2: ATK
    20,  # 3: DEF
    20,  # 4: MAT
    20,  # 5: MDF
    30,  # 6: AGI
    30,  # 7: LUK
]

_CLASS_PARAMS_CURVE_LEN = 100  # RPG Maker MZ 표준 (level 0 ~ 99)


def _build_class_curve(base_value: int) -> list[int]:
    """단순 선형 성장 곡선 생성.

    RPG Maker MZ 는 params[stat][level] 에서 level **1-indexed** 로 읽는다 (level 0 미사용).
    따라서 curve[1] = base, curve[99] = base * 3 이 되도록 설정.
    curve[0] 은 런타임에서 사용하지 않지만 배열 길이 유지 위해 0 으로 채움.
    """
    base = max(1, int(base_value))
    length = _CLASS_PARAMS_CURVE_LEN  # 100 → index 0..99
    result: list[int] = [0]  # index 0 unused
    # index 1..99 을 base ~ base*3 linear growth
    for lv in range(1, length):
        result.append(int(base * (1 + 2 * (lv - 1) / (length - 2))))
    return result


def _collect_class_stats_from_parsed(parsed_command: dict | None) -> dict[int, int]:
    """parsed_command (+ additional_properties) 에서 Class stat 을 추출.

    Returns:
        dict[param_index, base_value]. 지정 안 된 index 는 default 사용.
    """
    if not parsed_command:
        return {}
    stats: dict[int, int] = {}

    def _try_add(prop: str, val: str) -> None:
        idx = _CLASS_STAT_PROPERTY_TO_INDEX.get(prop) or _CLASS_STAT_PROPERTY_TO_INDEX.get(
            (prop or "").lower()
        )
        if idx is None:
            return
        try:
            stats[idx] = int(str(val).strip())
        except (TypeError, ValueError):
            return

    prop = (parsed_command.get("property") or "").strip()
    val = str(parsed_command.get("value") or "").strip()
    if prop and val:
        _try_add(prop, val)
    for extra in parsed_command.get("additional_properties") or []:
        if isinstance(extra, dict):
            _try_add(
                str(extra.get("property") or ""),
                str(extra.get("value") or ""),
            )
    return stats


def _build_class_profile(
    target_info: dict,
    parsed_command: dict | None,
) -> dict:
    """Classes.json 생성을 위한 rule-base target_info 완성.

    - user 지정 스탯은 해당 param index 의 base 로 사용
    - 지정 안 된 param 은 `_CLASS_STAT_DEFAULT_BASE` 사용
    - 각 param 은 길이 100 의 선형 성장 곡선으로 생성
    """
    result = dict(target_info)
    user_stats = _collect_class_stats_from_parsed(parsed_command)

    params: list[list[int]] = []
    for idx in range(8):
        base = user_stats.get(idx, _CLASS_STAT_DEFAULT_BASE[idx])
        params.append(_build_class_curve(base))
    result["params"] = params

    # expParams 는 Class 스키마 default 와 동일 — 명시 세팅으로 안정성 확보
    if "expParams" not in result:
        result["expParams"] = [30, 20, 20, 40]

    # 기타 기본 필드 (LLM 안 거치므로 직접 세팅)
    result.setdefault("learnings", [])
    result.setdefault("traits", [])
    result.setdefault("note", "")
    return result


def _enforce_default_field_lock(original_step: dict, enriched_step: dict) -> dict:
    """planner 가 target_info 에 명시적으로 세팅한 optional 기본 필드 (nickname 등)
    를 LLM 이 덮지 못하게 복원. 명시 세팅 없으면 (키 부재) LLM 자율.

    원본 target_info 에 해당 키가 **존재** 하면 (빈 문자열 포함) 그 값으로 고정.
    """
    target_file = enriched_step.get("target_file", "")
    locked = _LOCKED_OPTIONAL_FIELDS.get(target_file)
    if not locked:
        return enriched_step
    original_info = original_step.get("target_info") or {}
    enriched_info = dict(enriched_step.get("target_info") or {})
    changed = False
    for key in locked:
        if key in original_info and enriched_info.get(key) != original_info.get(key):
            logger.info(
                "[Profiler] default lock: %s.%s = %r (LLM %r 무시)",
                target_file,
                key,
                original_info.get(key),
                enriched_info.get(key),
            )
            enriched_info[key] = original_info[key]
            changed = True
    if changed:
        enriched_step = dict(enriched_step)
        enriched_step["target_info"] = enriched_info
    return enriched_step


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
    user_input: str = state.get("user_input", "") or ""

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
        # Task 30: profile 전에 fill_schema.fixed_fields 를 target_info 에 merge.
        # 이렇게 하면 LLM 이 이 필드에 기본값을 넣으려 해도 _enforce_default_field_lock
        # 이 원본 (= 여기서 세팅한 값) 으로 복원.
        step = _inject_fixed_fields(step)
        before_keys = set((step.get("target_info") or {}).keys())
        enriched = await profile_one(
            step,
            game_id=game_id,
            user_input=user_input,
            parsed_command=parsed_command,
        )
        # sprint β: LLM 이 name 을 엉뚱한 값으로 덮지 않도록 원본 name 강제 복원
        enriched = _enforce_name_lock(step, enriched)
        # Task 30: nickname / 이미지 등 optional 기본 필드도 lock
        enriched = _enforce_default_field_lock(step, enriched)
        # Task 19 + sprint β + Task 29: parsed_command.value + additional_properties +
        # "직업" → classId 해소 (game_id 필요)
        enriched = _inject_parsed_command_value(enriched, parsed_command, game_id=game_id)
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
    *,
    user_input: str | None = None,
    parsed_command: dict | None = None,
) -> dict:
    """단일 create step 의 target_info 를 의미적으로 채운다.

    validator 의 partial retry 에서도 직접 호출된다.
    Task 28: user_input / parsed_command 를 LLM 프롬프트에 함께 주입해
    template default 복사를 차단.
    Task 36: Classes.json 은 LLM 이 params `list[list[int]]` 구조를 일관되게
    못 만들어 rule-base 로 생성 (LLM skip).
    """
    target_file = step.get("target_file", "")
    target_info = dict(step.get("target_info") or {})

    # Task 36: Classes.json rule-base 경로 — LLM 호출 skip
    if target_file == "Classes.json":
        enriched_info = _build_class_profile(target_info, parsed_command)
        _coerce_int_fields(enriched_info, target_file)
        enriched_step = dict(step)
        enriched_step["target_info"] = enriched_info
        enriched_step.pop("_needs_profiling", None)
        logger.info(
            "[Profiler] Classes.json rule-base (LLM 0 회) name='%s' params curves=%d",
            enriched_info.get("name", "?"),
            len(enriched_info.get("params", [])),
        )
        return enriched_step

    # 기존 엔티티 예시 가져오기 (병목 해결을 위해 비활성화)
    # examples = _get_existing_examples(game_id, target_file)
    examples = []
    schema_excerpt = get_schema_reference(target_file)

    system_prompt = build_profiler_system_prompt()
    user_prompt = build_profiler_user_prompt(
        step,
        schema_excerpt,
        examples,
        feedback,
        user_input=user_input,
        parsed_command=parsed_command,
    )

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
