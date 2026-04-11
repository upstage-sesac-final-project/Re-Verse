"""배열 요소 조작 해석기 — match_hint + ref → 숫자 코드/ID 변환.

intake 가 "공격 속성", "빛" 같은 의미 표현을 내보내면
이 모듈이 trait code 31, dataId 8 같은 숫자로 변환한다.

사용처: rule_engine._build_updates_dict() 에서 field 가 배열 필드일 때 호출.
"""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# trait code 의미 매핑
# ──────────────────────────────────────────────

MATCH_HINT_TO_TRAIT_CODE: dict[str, int] = {
    # 11: 속성 내성
    "속성 내성": 11, "원소 내성": 11, "속성내성": 11,
    # 12: 약화 유효율
    "약화 유효율": 12, "디버프 유효율": 12,
    # 13: 상태 내성
    "상태 내성": 13, "상태내성": 13, "상태이상 내성": 13,
    # 21: 능력치 보정 (배율)
    "능력치 보정": 21, "능력치 배율": 21, "스탯 배율": 21,
    # 22: 추가 능력치
    "추가 능력치": 22, "명중": 22, "회피": 22,
    # 31: 공격 속성
    "공격 속성": 31, "공격속성": 31, "공격 원소": 31,
    # 32: 공격 시 상태 부여
    "공격 상태": 32, "공격 시 상태": 32, "공격 시 상태 부여": 32,
    # 33: 공격 속도 보정
    "공격 속도": 33, "공격속도": 33,
    # 34: 공격 추가 횟수
    "공격 횟수": 34, "공격 추가": 34,
    # 41: 스킬 유형 추가
    "스킬 유형 추가": 41, "스킬유형 추가": 41,
    # 42: 스킬 유형 봉인
    "스킬 유형 봉인": 42, "스킬유형 봉인": 42,
    # 43: 스킬 추가
    "스킬 추가": 43,
    # 44: 스킬 봉인
    "스킬 봉인": 44,
    # 51: 무기 유형 장비
    "무기 유형 장비": 51, "무기유형": 51,
    # 52: 방어구 유형 장비
    "방어구 유형 장비": 52, "방어구유형": 52,
    # 53: 장비 고정
    "장비 고정": 53,
    # 54: 장비 봉인
    "장비 봉인": 54,
    # 61: 추가 행동
    "추가 행동": 61,
    # 62: 특수 플래그
    "특수 플래그": 62, "자동전투": 62,
    # 63: 소멸 효과
    "소멸 효과": 63,
    # 64: 파티 능력
    "파티 능력": 64,
}

# trait code 별 dataId 해석 소스
# (resolve_type, source_key_or_file)
#   "system" → System.json 의 해당 배열에서 이름으로 index 검색
#   "entity" → 해당 파일에서 이름으로 entity id 검색
#   None     → dataId 가 고정 의미 (능력치 인덱스 등), ref 를 직접 숫자로 변환
TRAIT_DATAID_SOURCE: dict[int, tuple[str | None, str]] = {
    11: ("system", "elements"),
    13: ("entity", "States.json"),
    31: ("system", "elements"),
    32: ("entity", "States.json"),
    41: ("system", "skillTypes"),
    42: ("system", "skillTypes"),
    43: ("entity", "Skills.json"),
    44: ("entity", "Skills.json"),
    51: ("system", "weaponTypes"),
    52: ("system", "armorTypes"),
}

# ──────────────────────────────────────────────
# effect code 의미 매핑
# ──────────────────────────────────────────────

MATCH_HINT_TO_EFFECT_CODE: dict[str, int] = {
    "HP 회복": 11, "HP회복": 11,
    "MP 회복": 12, "MP회복": 12,
    "TP 획득": 13, "TP획득": 13,
    "상태 부여": 21, "상태부여": 21,
    "상태 해제": 22, "상태해제": 22,
    "버프": 31, "강화": 31,
    "디버프": 32, "약화": 32,
    "버프 해제": 33,
    "디버프 해제": 34,
    "특수 효과": 41, "도주": 41,
    "성장": 42,
    "스킬 습득": 43,
    "공용 이벤트": 44,
}


# ──────────────────────────────────────────────
# 이름 → ID 해석 유틸
# ──────────────────────────────────────────────

def _load_json(data_path: Path, filename: str) -> Any:
    fp = data_path / filename
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def _find_in_system_array(data_path: Path, system_key: str, name: str) -> int | None:
    """System.json 의 배열에서 이름으로 인덱스 검색."""
    system = _load_json(data_path, "System.json")
    if not isinstance(system, dict):
        return None
    arr = system.get(system_key)
    if not isinstance(arr, list):
        return None
    t = name.strip().lower()
    for idx, val in enumerate(arr):
        if isinstance(val, str) and val.strip().lower() == t:
            return idx
    # fuzzy
    best_idx, best_ratio = None, 0.0
    for idx, val in enumerate(arr):
        if isinstance(val, str) and val.strip():
            ratio = SequenceMatcher(None, t, val.strip().lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
    if best_ratio >= 0.6:
        return best_idx
    return None


def _find_entity_id(data_path: Path, filename: str, name: str) -> int | None:
    """엔티티 파일에서 이름으로 ID 검색."""
    data = _load_json(data_path, filename)
    if not isinstance(data, list):
        return None
    t = name.strip().lower()
    for entry in data:
        if isinstance(entry, dict) and str(entry.get("name") or "").strip().lower() == t:
            return entry.get("id")
    # fuzzy
    best_entry, best_ratio = None, 0.0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        n = str(entry.get("name") or "").strip().lower()
        if not n:
            continue
        ratio = SequenceMatcher(None, t, n).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_entry = entry
    if best_ratio >= 0.6 and best_entry:
        return best_entry.get("id")
    return None


def _resolve_ref_for_trait(
    code: int, ref: str, data_path: Path,
) -> int | None:
    """trait code 에 맞는 소스에서 ref 이름을 숫자 ID 로 변환."""
    source = TRAIT_DATAID_SOURCE.get(code)
    if source is None:
        # 숫자 직접 변환 시도 (능력치 인덱스 등)
        try:
            return int(ref)
        except (ValueError, TypeError):
            return None
    resolve_type, key_or_file = source
    if resolve_type == "system":
        return _find_in_system_array(data_path, key_or_file, ref)
    if resolve_type == "entity":
        return _find_entity_id(data_path, key_or_file, ref)
    return None


def _fuzzy_match_hint(hint: str, table: dict[str, int]) -> int | None:
    """match_hint 를 테이블에서 검색. 완전 일치 → fuzzy."""
    if not hint:
        return None
    t = hint.strip()
    # 완전 일치
    if t in table:
        return table[t]
    # 대소문자/공백 무시
    t_lower = t.lower().replace(" ", "")
    for key, code in table.items():
        if key.lower().replace(" ", "") == t_lower:
            return code
    # 부분 문자열 포함
    for key, code in table.items():
        if key in t or t in key:
            return code
    return None


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def resolve_array_op(
    target_file: str,
    field: str,
    value: dict,
    data_path: Path,
) -> dict[str, Any] | None:
    """intake 의 의미 표현을 완전히 해석된 _array_op 로 변환.

    Returns:
        {
            "array_field": str,
            "op": "update" | "add" | "remove",
            "match": dict,   # 조건
            "set": dict,     # 변경/추가할 필드
        }
        또는 해석 실패 시 None
    """
    array_op = value.get("array_op", "update")
    match_hint = value.get("match_hint") or ""
    ref = value.get("ref") or ""
    new_value = value.get("new_value")

    if field == "traits":
        return _resolve_trait_op(array_op, match_hint, ref, new_value, data_path)
    if field == "effects":
        return _resolve_effect_op(array_op, match_hint, ref, new_value, data_path)
    # actions, dropItems, learnings — ref 는 엔티티 이름
    if field == "actions":
        return _resolve_actions_op(array_op, ref, new_value, data_path)
    if field == "dropItems":
        return _resolve_drop_items_op(array_op, ref, new_value, data_path)
    if field == "learnings":
        return _resolve_learnings_op(array_op, ref, new_value, data_path)

    return None


def _resolve_trait_op(
    op: str, match_hint: str, ref: str, new_value: Any, data_path: Path,
) -> dict[str, Any] | None:
    code = _fuzzy_match_hint(match_hint, MATCH_HINT_TO_TRAIT_CODE)
    if code is None:
        logger.warning("[array_op] trait match_hint '%s' 해석 실패", match_hint)
        return None

    result: dict[str, Any] = {"array_field": "traits", "op": op}

    if op in ("update", "remove"):
        result["match"] = {"code": code}

    if op in ("update", "add"):
        set_fields: dict[str, Any] = {}
        if op == "add":
            set_fields["code"] = code
            set_fields["value"] = 0  # 기본값
        # ref → dataId 변환 (실패 시 new_value 를 ref 로 재시도)
        resolved_id = None
        for candidate in (ref, str(new_value) if isinstance(new_value, str) else None):
            if not candidate:
                continue
            resolved_id = _resolve_ref_for_trait(code, candidate, data_path)
            if resolved_id is not None:
                break
        if resolved_id is not None:
            set_fields["dataId"] = resolved_id
        elif ref or (isinstance(new_value, str) and new_value):
            logger.warning("[array_op] trait ref 해석 실패: ref='%s', new_value='%s' (code=%d)", ref, new_value, code)
            return None
        # new_value 가 숫자면 value 필드 (내성률 등)
        if isinstance(new_value, (int, float)):
            set_fields["value"] = new_value
        result["set"] = set_fields

    return result


def _resolve_effect_op(
    op: str, match_hint: str, ref: str, new_value: Any, data_path: Path,
) -> dict[str, Any] | None:
    code = _fuzzy_match_hint(match_hint, MATCH_HINT_TO_EFFECT_CODE)
    if code is None:
        logger.warning("[array_op] effect match_hint '%s' 해석 실패", match_hint)
        return None

    result: dict[str, Any] = {"array_field": "effects", "op": op}
    if op in ("update", "remove"):
        result["match"] = {"code": code}
    if op in ("update", "add"):
        set_fields: dict[str, Any] = {}
        if op == "add":
            set_fields["code"] = code
        if ref:
            # 상태/스킬 등 참조
            if code in (21, 22):
                sid = _find_entity_id(data_path, "States.json", ref)
                if sid is not None:
                    set_fields["dataId"] = sid
            elif code == 43:
                sid = _find_entity_id(data_path, "Skills.json", ref)
                if sid is not None:
                    set_fields["dataId"] = sid
        if new_value is not None:
            set_fields["value1"] = new_value
        result["set"] = set_fields
    return result


def _resolve_actions_op(
    op: str, ref: str, new_value: Any, data_path: Path,
) -> dict[str, Any] | None:
    result: dict[str, Any] = {"array_field": "actions", "op": op}
    skill_id = _find_entity_id(data_path, "Skills.json", ref) if ref else None

    if op == "add":
        if skill_id is None:
            return None
        result["set"] = {
            "skillId": skill_id,
            "conditionType": 0,
            "conditionParam1": 0,
            "conditionParam2": 0,
            "rating": 5,
        }
    elif op in ("update", "remove"):
        if skill_id is not None:
            result["match"] = {"skillId": skill_id}
        if op == "update" and new_value is not None:
            result["set"] = {"rating": int(new_value)}
    return result


def _resolve_drop_items_op(
    op: str, ref: str, new_value: Any, data_path: Path,
) -> dict[str, Any] | None:
    result: dict[str, Any] = {"array_field": "dropItems", "op": op}
    item_id = _find_entity_id(data_path, "Items.json", ref) if ref else None

    if op == "add":
        if item_id is None:
            return None
        result["set"] = {"kind": 1, "dataId": item_id, "denominator": 3}
        # 빈 슬롯(kind=0) 을 찾아 교체하는 것은 executor 측에서 처리
    elif op in ("update", "remove"):
        if item_id is not None:
            result["match"] = {"dataId": item_id}
    return result


def _resolve_learnings_op(
    op: str, ref: str, new_value: Any, data_path: Path,
) -> dict[str, Any] | None:
    result: dict[str, Any] = {"array_field": "learnings", "op": op}
    skill_id = _find_entity_id(data_path, "Skills.json", ref) if ref else None

    if op == "add":
        if skill_id is None:
            return None
        level = int(new_value) if isinstance(new_value, (int, float)) else 1
        result["set"] = {"skillId": skill_id, "level": level, "note": ""}
    elif op in ("update", "remove"):
        if skill_id is not None:
            result["match"] = {"skillId": skill_id}
        if op == "update" and new_value is not None:
            result["set"] = {"level": int(new_value)}
    return result
