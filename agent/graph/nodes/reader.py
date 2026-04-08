"""Reader 노드 — 게임_요소_조회 빠른 처리 경로.

definition → planner → executor → validator → synthesizer 5단계를 건너뛰고
LLM 1회(+@) 및 직접 파일 읽기로 조회 결과를 즉시 반환한다.

입력 (state):
    user_input, game_id

출력 (state):
    final_response
"""

import logging
import statistics
import time
from difflib import SequenceMatcher
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.reader_prompt import (
    build_entity_name_match_prompt,
    build_entity_type_guess_prompt,
    build_prompt,
)
from agent.utils.game_data_io import CATEGORY_TO_PLURAL, read_game_json

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

_CATEGORY_DISPLAY: dict[str, str] = {
    "actor": "캐릭터",
    "enemy": "적",
    "item": "아이템",
    "weapon": "무기",
    "armor": "방어구",
    "class": "직업",
    "state": "상태이상",
    "skill": "스킬",
    "system": "시스템",
}

# RPG Maker MZ params 배열 인덱스 (enemy/actor 공통 8개 기본 스탯)
_PARAMS_INDEX: dict[str, int] = {
    "maxhp": 0,
    "mhp": 0,
    "maxmp": 1,
    "mmp": 1,
    "atk": 2,
    "def": 3,
    "mat": 4,
    "mdf": 5,
    "agi": 6,
    "luk": 7,
}

_FUZZY_THRESHOLD = 0.6
_FUZZY_SUGGESTION_THRESHOLD = 0.5
_BULK_LIST_TRUNCATE_THRESHOLD = 30

# ── 참조 해소 맵 ──────────────────────────────────────────────────────────────
# (entity_type, field_name) → 참조 정의
# type:
#   single       — 정수 ID 1개 → 대상 파일에서 이름 조회
#   system_list  — 정수 인덱스 → System.json 내 배열에서 문자열 조회
#   array        — 배열 내 각 항목의 ID → 대상 파일에서 다건 이름 조회
#   array_equip  — actor.equips 전용 (Weapons/Armors 혼합)

_REFERENCE_MAP: dict[tuple[str, str], dict] = {
    ("actor", "classId"): {"type": "single", "file": "Classes"},
    ("actor", "equips"): {"type": "array_equip"},
    ("class", "learnings"): {"type": "array", "file": "Skills", "id_field": "skillId"},
    ("enemy", "actions"): {"type": "array", "file": "Skills", "id_field": "skillId"},
    ("enemy", "dropItems"): {
        "type": "array",
        "file": "Items",
        "id_field": "dataId",
        "filter": {"kind": 1},
    },
    ("skill", "stypeId"): {"type": "system_list", "key": "skillTypes"},
    ("skill", "damage.elementId"): {"type": "system_list", "key": "elements"},
    ("skill", "elementId"): {"type": "system_list", "key": "elements"},
    ("skill", "effects"): {
        "type": "array",
        "file": "States",
        "id_field": "dataId",
        "filter": {"code": 21},
    },
    ("weapon", "wtypeId"): {"type": "system_list", "key": "weaponTypes"},
    ("weapon", "etypeId"): {"type": "system_list", "key": "equipTypes"},
    ("armor", "atypeId"): {"type": "system_list", "key": "armorTypes"},
    ("armor", "etypeId"): {"type": "system_list", "key": "equipTypes"},
}

# 역방향 참조 필터 맵 — bulk_list에서 참조된 엔티티 이름으로 필터링할 때 사용
# (entity_type, filter_field) → 필터 해소 방법
_FILTER_REF: dict[tuple[str, str], dict] = {
    # actor.classId == Classes["마법사"].id
    ("actor", "classId"): {"type": "single_id", "lookup_file": "Classes"},
    # skill.stypeId == System.skillTypes 인덱스
    ("skill", "stypeId"): {"type": "system_list_id", "key": "skillTypes"},
    # skill.effects[].dataId (code==21) == States["독"].id
    ("skill", "effects"): {
        "type": "array_ref",
        "lookup_file": "States",
        "id_field": "dataId",
        "array_filter": {"code": 21},
    },
    # enemy.actions[].skillId == Skills["이름"].id
    ("enemy", "actions"): {"type": "array_ref", "lookup_file": "Skills", "id_field": "skillId"},
    # enemy.dropItems[].dataId (kind==1) == Items["이름"].id
    ("enemy", "dropItems"): {
        "type": "array_ref",
        "lookup_file": "Items",
        "id_field": "dataId",
        "array_filter": {"kind": 1},
    },
    # weapon.wtypeId == System.weaponTypes 인덱스
    ("weapon", "wtypeId"): {"type": "system_list_id", "key": "weaponTypes"},
    # armor.atypeId == System.armorTypes 인덱스
    ("armor", "atypeId"): {"type": "system_list_id", "key": "armorTypes"},
}

# field_name → 유저 친화적 한국어 표시명
_FIELD_DISPLAY: dict[str, str] = {
    "classId": "직업",
    "stypeId": "스킬 유형",
    "elementId": "속성",
    "damage.elementId": "속성",
    "wtypeId": "무기 유형",
    "etypeId": "장비 유형",
    "atypeId": "방어구 유형",
    "equips": "장비",
    "learnings": "습득 스킬",
    "actions": "행동 패턴",
    "dropItems": "드롭 아이템",
    "effects": "상태이상 효과",
}


# ── 쿼리 스키마 ────────────────────────────────────────────────────────────────


class _EntityTypeGuess(BaseModel):
    entity_type: str | None = Field(default=None, description="추정 카테고리 영문 단수형")
    reasoning: str = Field(default="", description="분류 근거")


class _EntityNameMatch(BaseModel):
    matched_name: str | None = Field(
        default=None, description="가장 유사한 엔티티 이름. 없으면 null"
    )
    reasoning: str = Field(default="", description="선택 근거")


class _ReaderQuery(BaseModel):
    reasoning: str = Field(default="", description="분류 근거")
    query_type: Literal["single_entity", "field_value", "bulk_list", "existence", "aggregate"]
    entity_type: str | None = Field(
        default=None, description="카테고리 영문 단수형. 예: enemy, item"
    )
    entity_name: str | None = Field(
        default=None,
        description="영문 엔티티명. 한글 입력이어도 영문으로 변환. 예: 페가수스 → Pegasus",
    )
    field_name: str | None = Field(
        default=None,
        description="조회할 JSON 필드명 (영문). 예: maxHp, atk, price",
    )
    filters: dict | None = Field(
        default=None,
        description=(
            "역방향 참조 필터. bulk_list에서 참조 관계로 필터링할 때만 지정. "
            '예: 마법사인 액터 → {"classId": "마법사"}, 독 스킬 → {"effects": "독"}'
        ),
    )
    sort: str | None = Field(default=None, description="정렬 기준 필드명")
    limit: int | None = Field(default=None, description="반환 최대 개수")
    aggregate_fn: Literal["count", "min", "max", "avg", "sum"] | None = Field(
        default=None, description="집계 함수. aggregate 타입일 때만 지정"
    )


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _valid_items(data: list) -> list[dict]:
    """RPG Maker MZ JSON 배열에서 null 항목과 name이 빈 슬롯을 제거한다."""
    return [item for item in data if isinstance(item, dict) and item.get("name")]


def _fuzzy_match(
    entity_name: str, items: list[dict], threshold: float = _FUZZY_THRESHOLD
) -> list[dict]:
    """entity_name과 SequenceMatcher로 유사도 매칭, threshold 이상인 항목을 유사도 내림차순으로 반환한다."""
    scored: list[tuple[float, dict]] = []
    for item in items:
        name = item.get("name", "")
        if not name:
            continue
        ratio = SequenceMatcher(None, entity_name.lower(), name.lower()).ratio()
        if ratio >= threshold:
            scored.append((ratio, item))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [item for _, item in scored]


def _find_candidates(entity_name: str, items: list[dict]) -> list[dict]:
    """ID 숫자 > exact > case-insensitive exact > prefix > fuzzy 우선순위로 후보를 반환한다."""
    # 0. 숫자면 ID로 직접 접근
    if entity_name.isdigit():
        by_id = [
            item for item in items if isinstance(item, dict) and item.get("id") == int(entity_name)
        ]
        if by_id:
            return by_id
    # 1. 완전 일치
    exact = [item for item in items if isinstance(item, dict) and item.get("name") == entity_name]
    if exact:
        return exact
    # 2. 대소문자 무시 완전 일치
    ci = [
        item
        for item in items
        if isinstance(item, dict) and item.get("name", "").lower() == entity_name.lower()
    ]
    if ci:
        return ci
    # 3. prefix match (entity_name으로 시작하는 이름 전부)
    prefix = [
        item
        for item in items
        if isinstance(item, dict) and item.get("name", "").lower().startswith(entity_name.lower())
    ]
    if prefix:
        return prefix
    # 4. 퍼지 매칭
    return _fuzzy_match(entity_name, items)


def _get_field_value(entity: dict, field_name: str) -> tuple[Any, bool]:
    """엔티티에서 필드값을 추출한다. dot notation(damage.elementId)과 params 배열 접근도 처리한다."""
    # dot notation 처리 (예: damage.elementId)
    if "." in field_name:
        parts = field_name.split(".", 1)
        nested = entity.get(parts[0])
        if isinstance(nested, dict):
            return _get_field_value(nested, parts[1])
        return None, False
    if field_name in entity:
        return entity[field_name], True
    idx = _PARAMS_INDEX.get(field_name.lower())
    if idx is not None:
        params = entity.get("params", [])
        if isinstance(params, list) and len(params) > idx:
            # Classes.params는 list[list[int]]이므로 첫 원소가 int인지 확인
            if isinstance(params[idx], (int, float)):
                return params[idx], True
    return None, False


def _get_numeric_value(entity: dict, field_name: str) -> float | None:
    """엔티티에서 숫자 필드값을 추출한다. 숫자가 아니거나 없으면 None 반환."""
    value, found = _get_field_value(entity, field_name)
    if found and isinstance(value, (int, float)):
        return float(value)
    return None


def _get_category_display(entity_type: str | None) -> str:
    return _CATEGORY_DISPLAY.get(entity_type or "", "항목")


def _format_candidate_lines(candidates: list[dict]) -> str:
    return "\n".join(f" - {c['name']} (ID: {c['id']})" for c in candidates)


def _build_suggestion_hint(entity_name: str, items: list[dict]) -> str:
    suggestions = _fuzzy_match(entity_name, items, threshold=_FUZZY_SUGGESTION_THRESHOLD)[:3]
    if not suggestions:
        return ""
    return "\n유사한 이름: " + ", ".join(f"{s['name']} (ID: {s['id']})" for s in suggestions)


def _build_not_found_response(
    entity_name: str | None, entity_type: str | None, items: list[dict]
) -> str:
    return (
        f"'{entity_name}'이라는 {_get_category_display(entity_type)}을(를) 찾지 못했습니다."
        f"{_build_suggestion_hint(entity_name or '', items)}"
    )


def _build_ambiguous_response(entity_name: str | None, candidates: list[dict]) -> str:
    return (
        f"'{entity_name}'과(와) 유사한 이름이 여럿 있습니다. 어떤 것을 찾으시나요?\n"
        f"{_format_candidate_lines(candidates)}"
    )


def _build_id_name_map(data: list[Any]) -> dict[int, str]:
    return {item["id"]: item["name"] for item in data if isinstance(item, dict) and item.get("id")}


def _format_entity_summary(entity: dict) -> str:
    """엔티티의 주요 필드를 요약 문자열로 반환한다. 복잡한 중첩 구조는 제외한다."""
    skip_keys = {"id", "name", "note", "meta"}
    lines: list[str] = []

    # params 배열이 있으면 8개 기본 스탯을 한 줄로 표시
    params = entity.get("params")
    if isinstance(params, list) and len(params) >= 8:
        stat_names = ["maxHp", "maxMp", "atk", "def", "mat", "mdf", "agi", "luk"]
        stat_line = " / ".join(f"{k}: {params[i]}" for i, k in enumerate(stat_names))
        lines.append(f" - 스탯: {stat_line}")
        skip_keys.add("params")

    # 나머지 스칼라 필드 (list/dict 제외)
    for k, v in entity.items():
        if k in skip_keys:
            continue
        if isinstance(v, (str, int, float, bool)) and v != "" and v is not None:
            lines.append(f" - {k}: {v}")

    return "\n".join(lines) if lines else " - (표시할 필드 없음)"


# ── 참조 해소 ──────────────────────────────────────────────────────────────────


def _resolve_reference(game_id: str, entity_type: str, field_name: str, entity: dict) -> str | None:
    """참조 필드를 해소해 사람이 읽을 수 있는 문자열로 반환한다. 해당 없으면 None."""
    ref = _REFERENCE_MAP.get((entity_type, field_name))
    if not ref:
        return None

    ref_type = ref["type"]

    if ref_type == "single":
        # actor.classId → Classes[id].name
        value = entity.get(field_name)
        if not isinstance(value, int):
            return None
        target_data = read_game_json(game_id, ref["file"] + ".json")
        if not isinstance(target_data, list):
            return None
        matched = [i for i in target_data if isinstance(i, dict) and i.get("id") == value]
        if matched:
            return f"{matched[0].get('name', str(value))} (ID: {value})"
        return str(value)

    elif ref_type == "system_list":
        # skill.stypeId → System.skillTypes[index]
        if "." in field_name:
            parts = field_name.split(".", 1)
            nested = entity.get(parts[0])
            value = nested.get(parts[1]) if isinstance(nested, dict) else None
        else:
            value = entity.get(field_name)
        if not isinstance(value, int):
            return None
        sys_data = read_game_json(game_id, "System.json")
        if not isinstance(sys_data, dict):
            return None
        lst = sys_data.get(ref["key"], [])
        if isinstance(lst, list) and 0 < value < len(lst):
            return lst[value] or str(value)
        return str(value)

    elif ref_type == "array":
        # enemy.actions[].skillId → Skills 이름 목록
        arr = entity.get(field_name)
        if not isinstance(arr, list):
            return None
        filter_cond: dict = ref.get("filter", {})
        id_field: str = ref["id_field"]
        target_data = read_game_json(game_id, ref["file"] + ".json")
        if not isinstance(target_data, list):
            return None
        id_to_name = _build_id_name_map(target_data)
        results: list[str] = []
        seen: set[int] = set()
        for item in arr:
            if not isinstance(item, dict):
                continue
            if filter_cond and not all(item.get(k) == v for k, v in filter_cond.items()):
                continue
            ref_id = item.get(id_field)
            if isinstance(ref_id, int) and ref_id not in seen:
                seen.add(ref_id)
                name = id_to_name.get(ref_id, str(ref_id))
                results.append(f"{name} (ID: {ref_id})")
        if not results:
            return "(없음)"
        return "\n  ".join(results)

    elif ref_type == "array_equip":
        # actor.equips[] → Weapons/Armors 혼합
        equips = entity.get("equips", [])
        if not isinstance(equips, list):
            return None
        weapon_data = read_game_json(game_id, "Weapons.json")
        armor_data = read_game_json(game_id, "Armors.json")
        weapon_map = _build_id_name_map(weapon_data if isinstance(weapon_data, list) else [])
        armor_map = _build_id_name_map(armor_data if isinstance(armor_data, list) else [])
        slot_names = ["무기", "방패", "머리", "몸통", "장신구"]
        results = []
        for idx, equip_id in enumerate(equips):
            if equip_id == 0:
                continue
            slot = slot_names[idx] if idx < len(slot_names) else f"슬롯{idx + 1}"
            name = weapon_map.get(equip_id) or armor_map.get(equip_id) or str(equip_id)
            results.append(f"{slot}: {name} (ID: {equip_id})")
        if not results:
            return "(장비 없음)"
        return "\n  ".join(results)

    return None


# ── 시스템 조회 ────────────────────────────────────────────────────────────────

# System.json에서 유저에게 보여줄 주요 스칼라 필드 목록
_SYSTEM_DISPLAY_FIELDS = [
    "gameTitle",
    "currencyUnit",
    "locale",
    "optSideView",
    "optDisplayTp",
    "optExtraExp",
    "optFollowers",
]


def _execute_system_query(query: _ReaderQuery, data: dict) -> str:
    """System.json은 배열이 아닌 단일 dict이므로 별도 처리한다."""
    if query.query_type == "field_value" and query.field_name:
        value = data.get(query.field_name)
        if value is None:
            return f"시스템에서 '{query.field_name}' 항목을 찾지 못했습니다."
        return f"{query.field_name}: {value}"

    # single_entity / bulk_list → 주요 필드 목록 출력
    lines = ["[시스템 주요 설정]"]
    for k in _SYSTEM_DISPLAY_FIELDS:
        if k in data:
            lines.append(f" - {k}: {data[k]}")
    return "\n".join(lines)


# ── 조회 실행 ──────────────────────────────────────────────────────────────────


def _find_lookup_target_id(game_id: str, lookup_file: str, filter_value: Any) -> int | None:
    target_data = read_game_json(game_id, lookup_file + ".json")
    if not isinstance(target_data, list):
        return None
    cands = _find_candidates(str(filter_value), _valid_items(target_data))
    if not cands:
        return None
    return cands[0]["id"]


def _find_system_list_index(game_id: str, key: str, filter_value: Any) -> int | None:
    sys_data = read_game_json(game_id, "System.json")
    if not isinstance(sys_data, dict):
        return None
    lst = sys_data.get(key, [])
    fv_lower = str(filter_value).lower()
    for i, name in enumerate(lst):
        if name and fv_lower in str(name).lower():
            return i
    return None


def _execute_field_value(
    game_id: str, query: _ReaderQuery, items: list[dict], candidates: list[dict]
) -> str:
    if not candidates:
        return _build_not_found_response(query.entity_name, query.entity_type, items)

    if len(candidates) > 1:
        return _build_ambiguous_response(query.entity_name, candidates)

    entity = candidates[0]
    field_name = query.field_name or ""
    entity_type = query.entity_type or ""
    field_display = _FIELD_DISPLAY.get(field_name, field_name)

    # 참조 필드 해소 시도
    resolved = _resolve_reference(game_id, entity_type, field_name, entity)
    if resolved is not None:
        return f"{entity['name']}의 {field_display}:\n  {resolved}"

    # 일반 필드 조회
    value, found = _get_field_value(entity, field_name)
    if not found:
        return f"'{entity['name']}'에서 '{field_name}' 필드를 찾지 못했습니다."
    return f"{entity['name']}의 {field_display}은(는) {value}입니다."


def _execute_single_entity(query: _ReaderQuery, items: list[dict], candidates: list[dict]) -> str:
    if not candidates:
        return _build_not_found_response(query.entity_name, query.entity_type, items)

    if len(candidates) > 1:
        return _build_ambiguous_response(query.entity_name, candidates)

    entity = candidates[0]
    summary = _format_entity_summary(entity)
    return f"{entity['name']} (ID: {entity['id']})\n{summary}"


def _apply_filters(game_id: str, entity_type: str, items: list[dict], filters: dict) -> list[dict]:
    """filters dict를 해석해 items를 필터링한다. 역방향 참조 필터를 처리한다."""
    result = list(items)
    for filter_field, filter_value in filters.items():
        ref = _FILTER_REF.get((entity_type, filter_field))
        if ref is None:
            fv_str = str(filter_value).lower()
            result = [item for item in result if str(item.get(filter_field, "")).lower() == fv_str]
            continue

        ref_type = ref["type"]

        if ref_type == "single_id":
            target_id = _find_lookup_target_id(game_id, ref["lookup_file"], filter_value)
            if target_id is None:
                result = []
                continue
            result = [item for item in result if item.get(filter_field) == target_id]

        elif ref_type == "system_list_id":
            target_idx = _find_system_list_index(game_id, ref["key"], filter_value)
            if target_idx is None:
                result = []
                continue
            result = [item for item in result if item.get(filter_field) == target_idx]

        elif ref_type == "array_ref":
            lookup_file = ref["lookup_file"]
            id_field: str = ref["id_field"]
            array_filter: dict = ref.get("array_filter", {})

            target_id = _find_lookup_target_id(game_id, lookup_file, filter_value)
            if target_id is None:
                result = []
                continue

            def _matches_array_ref(item: dict) -> bool:
                arr = item.get(filter_field, [])
                if not isinstance(arr, list):
                    return False
                for entry in arr:
                    if not isinstance(entry, dict):
                        continue
                    if array_filter and not all(entry.get(k) == v for k, v in array_filter.items()):
                        continue
                    if entry.get(id_field) == target_id:
                        return True
                return False

            result = [item for item in result if _matches_array_ref(item)]

    return result


def _execute_bulk_list(game_id: str, query: _ReaderQuery, items: list[dict]) -> str:
    category_display = _get_category_display(query.entity_type)

    if query.filters:
        result_items = _apply_filters(game_id, query.entity_type or "", items, query.filters)
        filter_desc = "、".join(f"{k}={v}" for k, v in query.filters.items())
    else:
        result_items = list(items)
        filter_desc = None

    if query.sort:
        result_items.sort(
            key=lambda item: _get_numeric_value(item, query.sort) or 0.0,
            reverse=True,
        )

    total_count = len(result_items)
    truncated = False

    if query.limit is not None:
        result_items = result_items[: query.limit]
    elif total_count > _BULK_LIST_TRUNCATE_THRESHOLD:
        result_items = result_items[:_BULK_LIST_TRUNCATE_THRESHOLD]
        truncated = True

    if not result_items:
        if filter_desc:
            return f"조건({filter_desc})에 해당하는 {category_display}이(가) 없습니다."
        return f"현재 게임에 {category_display}이(가) 없습니다."

    if query.sort and query.limit:
        header = f"{query.sort} 상위 {query.limit}개 {category_display}:"
    elif filter_desc:
        header = f"{category_display} 목록 — {filter_desc} (총 {len(result_items)}개):"
    else:
        header = f"{category_display} 목록 (총 {len(result_items)}개):"

    lines = [header]
    for i, item in enumerate(result_items, 1):
        line = f" {i}. {item['name']} (ID: {item['id']})"
        if query.sort:
            v = _get_numeric_value(item, query.sort)
            if v is not None:
                line += f" — {query.sort}: {int(v)}"
        lines.append(line)

    if truncated:
        lines.append(
            f"\n(전체 {total_count}개 중 상위 {_BULK_LIST_TRUNCATE_THRESHOLD}개만 표시됩니다."
            " 범위를 좁혀서 다시 검색해보세요.)"
        )

    return "\n".join(lines)


def _execute_existence(query: _ReaderQuery, candidates: list[dict], items: list[dict]) -> str:
    category_display = _get_category_display(query.entity_type)

    if not candidates:
        return _build_not_found_response(query.entity_name, query.entity_type, items)

    if len(candidates) == 1:
        entity = candidates[0]
        return f"'{entity['name']}' {category_display}은(는) 현재 게임에 존재합니다. (ID: {entity['id']})"

    return _build_ambiguous_response(query.entity_name, candidates)


def _execute_aggregate(query: _ReaderQuery, items: list[dict]) -> str:
    category_display = _get_category_display(query.entity_type)
    fn = query.aggregate_fn or "count"

    if fn == "count":
        return f"현재 게임의 {category_display}은(는) 총 {len(items)}개입니다."

    field_name = query.field_name or query.sort
    if not field_name:
        return "집계할 필드가 지정되지 않았습니다."

    values: list[tuple[float, dict]] = []
    for item in items:
        v = _get_numeric_value(item, field_name)
        if v is not None:
            values.append((v, item))

    if not values:
        return f"'{field_name}' 필드를 집계할 수 없습니다."

    if fn == "max":
        best_v, best_item = max(values, key=lambda x: x[0])
        return (
            f"{field_name}이(가) 가장 높은 {category_display}은(는) "
            f"{best_item['name']} (ID: {best_item['id']})입니다. ({field_name}: {int(best_v)})"
        )

    if fn == "min":
        best_v, best_item = min(values, key=lambda x: x[0])
        return (
            f"{field_name}이(가) 가장 낮은 {category_display}은(는) "
            f"{best_item['name']} (ID: {best_item['id']})입니다. ({field_name}: {int(best_v)})"
        )

    nums = [v for v, _ in values]

    if fn == "sum":
        return f"{category_display} 전체 {field_name} 합계: {int(sum(nums))}"

    if fn == "avg":
        avg = statistics.mean(nums)
        return f"{category_display} 전체 {field_name} 평균: {avg:.1f}"

    return f"지원하지 않는 집계 함수입니다: {fn}"


# ── entity_type 추정 ───────────────────────────────────────────────────────────


async def _guess_entity_name(entity_name: str, items: list[dict]) -> str | None:
    """fuzzy 매칭 실패 시 LLM으로 동의어·번역어 기반 의미론적 이름 매핑을 시도한다."""
    names = [item["name"] for item in items]
    if not names:
        return None
    try:
        messages = build_entity_name_match_prompt(entity_name, names)
        result = cast(
            _EntityNameMatch, await invoke_llm(messages, structured_output=_EntityNameMatch)
        )
        matched = (result.matched_name or "").strip()
        logger.info(
            "  [name match] 입력=%r → 추정=%r (reasoning: %s)",
            entity_name,
            matched,
            result.reasoning,
        )
        return matched if matched in names else None
    except Exception as e:
        logger.error("[Reader] entity_name 매칭 LLM 호출 실패: %s", e)
        return None


async def _apply_semantic_name_match(
    query: _ReaderQuery, items: list[dict], candidates: list[dict]
) -> tuple[_ReaderQuery, list[dict]]:
    """candidates가 없을 때 semantic name matching을 시도해 query·candidates를 갱신한다."""
    if candidates:
        return query, candidates
    guessed_name = await _guess_entity_name(query.entity_name or "", items)
    if not guessed_name:
        return query, candidates
    matched = [item for item in items if item.get("name") == guessed_name]
    if not matched:
        return query, candidates
    logger.info("  semantic match 성공: %r → %r", query.entity_name, guessed_name)
    return query.model_copy(update={"entity_name": guessed_name}), matched


async def _guess_entity_type(entity_name: str) -> str | None:
    """LLM 2nd call로 엔티티 이름에서 카테고리를 추정한다."""
    try:
        messages = build_entity_type_guess_prompt(entity_name)
        guess = cast(
            _EntityTypeGuess, await invoke_llm(messages, structured_output=_EntityTypeGuess)
        )
        et = (guess.entity_type or "").lower().strip()
        logger.info("  [2nd call] entity_type 추정 결과: %r (reasoning: %s)", et, guess.reasoning)
        return et or None
    except Exception as e:
        logger.error("[Reader] entity_type 추정 LLM 호출 실패: %s", e)
        return None


def _load_items_for_entity_type(
    game_id: str, entity_type: str
) -> tuple[list[dict] | None, str | None]:
    plural = CATEGORY_TO_PLURAL.get(entity_type)
    if not plural:
        logger.warning("[Reader] 알 수 없는 entity_type: %s", entity_type)
        return None, f"'{entity_type}'은(는) 지원하지 않는 카테고리입니다."

    raw_data = read_game_json(game_id, plural + ".json")
    if raw_data is None:
        logger.warning("[Reader] 파일 없음: %s.json (game_id=%s)", plural, game_id)
        return None, "해당 카테고리의 데이터를 찾을 수 없습니다."
    if not isinstance(raw_data, list):
        return None, "게임 데이터를 읽는 중 오류가 발생했습니다."
    return _valid_items(raw_data), None


def _finish_reader(started_at: float, response: str) -> dict:
    logger.info(
        "─── ✅ Reader END (elapsed=%.2fs, response_len=%d) ────────────────────",
        time.perf_counter() - started_at,
        len(response),
    )
    return {"final_response": response}


# ── 노드 함수 ──────────────────────────────────────────────────────────────────


async def reader(state: AgentState) -> dict:
    _t0 = time.perf_counter()
    logger.info("─── 📖 Reader START ────────────────────────────────")
    logger.info("  input : %r", state.get("user_input"))
    logger.info("  game  : %s", state.get("game_id"))

    game_id = state.get("game_id", "game_001")

    messages = build_prompt(state)
    try:
        query = cast(_ReaderQuery, await invoke_llm(messages, structured_output=_ReaderQuery))
        logger.info(
            "  query_type=%s entity_type=%s entity_name=%r field_name=%r sort=%s limit=%s aggregate_fn=%s",
            query.query_type,
            query.entity_type,
            query.entity_name,
            query.field_name,
            query.sort,
            query.limit,
            query.aggregate_fn,
        )
        logger.info("  reasoning: %s", query.reasoning)
    except Exception as e:
        logger.error("[Reader] LLM 호출 실패: %s", e, exc_info=True)
        return {"final_response": "요청을 이해하지 못했습니다. 다시 입력해주세요."}

    entity_type = (query.entity_type or "").lower().strip()
    items: list[dict] = []
    candidates: list[dict] = []

    if entity_type == "system":
        raw_data = read_game_json(game_id, "System.json")
        if raw_data is None or not isinstance(raw_data, dict):
            return {"final_response": "시스템 데이터를 찾을 수 없습니다."}

        response = _execute_system_query(query, raw_data)
        return _finish_reader(_t0, response)

    elif entity_type:
        items, error_response = _load_items_for_entity_type(game_id, entity_type)
        if error_response:
            return {"final_response": error_response}

        items = items or []
        if query.entity_name:
            candidates = _find_candidates(query.entity_name, items)
            logger.info("  매칭 후보 %d개 (entity_name=%r)", len(candidates), query.entity_name)
            if not candidates:
                logger.info(
                    "  후보 없음 → semantic name matching 시도 (entity_name=%r)", query.entity_name
                )
                query, candidates = await _apply_semantic_name_match(query, items, candidates)

    elif query.entity_name:
        logger.info(
            "  entity_type 없음 → global entity lookup 시작 (entity_name=%r)", query.entity_name
        )
        found_in: list[tuple[str, list[dict], list[dict]]] = []

        for cat, plural in CATEGORY_TO_PLURAL.items():
            raw = read_game_json(game_id, plural + ".json")
            if raw is None or not isinstance(raw, list):
                continue
            cat_items = _valid_items(raw)

            cands = _find_candidates(query.entity_name, cat_items)
            if cands:
                found_in.append((cat, cat_items, cands))

        if len(found_in) == 1:
            entity_type, items, candidates = found_in[0]
            logger.info(
                "  global lookup 결과: category=%s, 후보 %d개", entity_type, len(candidates)
            )
            query = query.model_copy(update={"entity_type": entity_type})

        elif len(found_in) > 1:
            cat_names = ", ".join(_CATEGORY_DISPLAY.get(cat, cat) for cat, _, _ in found_in)
            return {
                "final_response": (
                    f"'{query.entity_name}'이라는 이름이 여러 카테고리({cat_names})에 걸쳐 있습니다."
                    " 어떤 카테고리를 찾으시나요? 예) '적 페가수스 정보 알려줘'"
                )
            }

        else:
            logger.info("  global lookup 미발견 → LLM 2nd call (entity_type 추정)")
            guessed = await _guess_entity_type(query.entity_name)

            if guessed and CATEGORY_TO_PLURAL.get(guessed):
                plural = CATEGORY_TO_PLURAL[guessed]

                raw = read_game_json(game_id, plural + ".json")
                if raw and isinstance(raw, list):
                    items = _valid_items(raw)

                    candidates = _find_candidates(query.entity_name, items)
                entity_type = guessed
                query = query.model_copy(update={"entity_type": entity_type})
                logger.info(
                    "  2nd call 후 재검색: category=%s, 후보 %d개", entity_type, len(candidates)
                )
                if not candidates:
                    logger.info(
                        "  후보 없음 → semantic name matching 시도 (entity_name=%r)",
                        query.entity_name,
                    )
                    query, candidates = await _apply_semantic_name_match(query, items, candidates)
            else:
                return {
                    "final_response": (
                        f"'{query.entity_name}'을(를) 찾지 못했습니다."
                        " 카테고리를 포함해서 다시 검색해보세요. 예) '적 페가수스 HP 알려줘'"
                    )
                }

    else:
        # entity_type도 없고 entity_name도 없음 (bulk_list/aggregate인데 카테고리 미지정)
        logger.warning("[Reader] entity_type, entity_name 모두 없음")
        return {
            "final_response": "조회할 카테고리를 파악하지 못했습니다. 예) '적 목록 보여줘', '아이템 가격 알려줘'"
        }

    if query.query_type == "field_value":
        response = _execute_field_value(game_id, query, items, candidates)

    elif query.query_type == "single_entity":
        response = _execute_single_entity(query, items, candidates)

    elif query.query_type == "bulk_list":
        response = _execute_bulk_list(game_id, query, items)

    elif query.query_type == "existence":
        response = _execute_existence(query, candidates, items)

    elif query.query_type == "aggregate":
        response = _execute_aggregate(query, items)

    else:
        response = "현재 지원하지 않는 조회 유형입니다."

    return _finish_reader(_t0, response)
