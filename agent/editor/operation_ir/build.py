"""operation_ir 빌드 (Step 5) — Step 1~4 결과에서 코드 기반 IR 직접 생성.

LLM 을 거치지 않고 (extractions + classifications + extracted_ids) 만으로
operation_tuples 를 만든다. 변환 불가능한 케이스는 빈 리스트 반환해 Step 6 LLM
fallback 신호로 삼는다.
"""

from __future__ import annotations

import logging

from agent.constants import CATEGORY_TO_FILE, EXP_CURVE_PRESETS, PROPERTY_TO_FIELD

logger = logging.getLogger(__name__)


_PARTY_ADD_KEYWORDS = (
    "파티에 포함",
    "파티에 추가",
    "파티에 넣",
    "파티에 합류",
    "파티원으로 추가",
    "동료로 추가",
    "동료로 영입",
)
_PARTY_REMOVE_KEYWORDS = (
    "파티에서 빼",
    "파티에서 제외",
    "파티에서 삭제",
    "파티에서 제거",
    "파티에서 내보",
    "파티에서 쫓아",
    "파티 해제",
    "동료에서 제외",
    "동료에서 빼",
)


def _detect_party_action(user_input: str) -> str | None:
    """user_input 에서 파티 편성 의도를 감지. add / remove / None."""
    text = (user_input or "").replace(" ", "")
    for kw in _PARTY_REMOVE_KEYWORDS:
        if kw.replace(" ", "") in text:
            return "remove"
    for kw in _PARTY_ADD_KEYWORDS:
        if kw.replace(" ", "") in text:
            return "add"
    return None


def _build_party_ops(
    classifications: list[dict], extracted_ids: dict, party_action: str
) -> list[dict]:
    """Actor 분류 각각에 대해 System.json partyMembers op 생성."""
    ops: list[dict] = []
    for cls in classifications:
        cat = str(cls.get("category") or "").lower()
        if cat != "actor":
            continue
        if cls.get("is_category_label"):
            continue
        name = (cls.get("name") or "").strip()
        if not name:
            continue
        mapped_id = cls.get("mapped_id")
        if isinstance(mapped_id, str):
            mapped_id = (
                None if mapped_id == "NEW" else (int(mapped_id) if mapped_id.isdigit() else None)
            )
        if mapped_id is None:
            mapped_id = extracted_ids.get(name)
        ops.append(
            {
                "op": "update",
                "file": "System.json",
                "subject": {"name": name, "id": mapped_id, "scope": "single"},
                "field": "partyMembers",
                "value": {
                    "kind": "party_op",
                    "ref": name,
                    "new_value": party_action,
                    "type_hint": None,
                    "array_op": party_action,
                    "match_hint": None,
                },
            }
        )
    return ops


def build_from_extractions(
    extractions: list[dict],
    classifications: list[dict],
    extracted_ids: dict,
    game_id: str,
    ranked_map_candidates: list[dict] | None = None,
    user_input: str = "",
) -> list[dict]:
    """Step 1~4 결과에서 직접 operation_tuples 를 생성한다.

    모든 extraction 을 변환할 수 없으면 빈 리스트를 반환 (fallback 신호).

    ranked_map_candidates: 게임 생성 시 계산된 맵 후보군 (점수 순 정렬).
        맵 추가 요청 시 이 목록에서 다음 후보를 선택해 original_file_name 을 주입한다.
        None 또는 빈 리스트이면 맵 CREATE 는 Step 6(LLM) 로 fallback.

    Returns:
        list[dict] — 성공 시 operation_tuples, 실패 시 [].
    """
    # classification 을 이름 기반 lookup 으로 구성
    cls_by_name: dict[str, dict] = {}
    for cls in classifications:
        name = cls.get("name", "").strip()
        if name:
            cls_by_name[name.lower()] = cls

    logger.debug(
        "[Step5] cls_by_name keys=%s, extractions=%d",
        list(cls_by_name.keys()),
        len(extractions),
    )

    # 파티 편성 의도 선감지 — Actor 분류가 있으면 partyMembers op 로 우선 변환
    party_action = _detect_party_action(user_input)
    if party_action:
        party_ops = _build_party_ops(classifications, extracted_ids, party_action)
        if party_ops:
            logger.info(
                "[Step5] 파티 편성(%s) 감지 → %d 개 partyMembers op 생성",
                party_action,
                len(party_ops),
            )
            return party_ops

    ops: list[dict] = []

    for ext in extractions:
        action = (ext.get("action") or "").upper().strip()
        subject = (ext.get("subject") or "").strip()
        prop = (ext.get("property") or "").strip()
        value_str = (ext.get("value") or "").strip()

        if not subject:
            return []  # 변환 불가

        # subject 의 분류 정보 찾기 — 완전 일치 → 부분 포함
        sub_cls = cls_by_name.get(subject.lower())
        if not sub_cls:
            # 부분 일치 fallback (예: subject="리드" vs cls name="리드 액터")
            for cname, cval in cls_by_name.items():
                if subject.lower() in cname or cname in subject.lower():
                    sub_cls = cval
                    break
        if not sub_cls:
            # System.json 수정: subject 가 카테고리 지칭어("게임", "시스템" 등)로 필터된 경우
            if prop and value_str and action == "UPDATE":
                sys_field = _detect_system_field(subject, prop)
                if sys_field:
                    logger.info(
                        "[Step5] System.json 수정 감지: %s.%s = %s", subject, sys_field, value_str
                    )
                    ops.append(
                        {
                            "op": "update",
                            "file": "System.json",
                            "subject": None,
                            "field": sys_field,
                            "value": {
                                "kind": "string",
                                "ref": None,
                                "new_value": value_str,
                                "type_hint": None,
                                "array_op": None,
                                "match_hint": None,
                            },
                        }
                    )
                    continue
            logger.info(
                "[Step5] subject '%s' not in cls_by_name %s → fallback",
                subject,
                list(cls_by_name.keys()),
            )
            return []

        sub_cat = (sub_cls.get("category") or "").lower()
        sub_id = sub_cls.get("mapped_id")
        if isinstance(sub_id, str):
            sub_id = None if sub_id == "NEW" else int(sub_id) if sub_id.isdigit() else None

        # extracted_ids 에서도 보완
        if sub_id is None:
            sub_id = extracted_ids.get(subject)

        sub_file = CATEGORY_TO_FILE.get(sub_cat)
        if not sub_file and sub_cat not in ("element", "system", "none"):
            return []

        # CREATE
        if action == "CREATE":
            if sub_cat == "map":
                # 맵 추가: ranked_map_candidates 가 있으면 최상위 후보를 사용.
                # 없으면 Step 6(LLM) 경로로 fallback.
                if ranked_map_candidates:
                    best = ranked_map_candidates[0]
                    original_file_name = best["entry"]["file_name"]
                    logger.info(
                        "[Step5] 맵 추가 요청 → 순위 후보 사용: %s (score=%.3f)",
                        original_file_name,
                        best.get("score", 0.0),
                    )
                    ops.append(
                        {
                            "op": "create",
                            "file": sub_file or "MapInfos.json",
                            "subject": {"name": subject, "id": None, "scope": "single"},
                            "field": None,
                            "value": {
                                "kind": "map_creation",
                                "original_file_name": original_file_name,
                            },
                        }
                    )
                    continue
                else:
                    # 후보군 없음 → Step 6(LLM) 에서 처리
                    logger.info(
                        "[Step5] 맵 추가 요청이지만 ranked_map_candidates 없음 → Step 6 fallback"
                    )
                    return []
            ops.append(
                {
                    "op": "create",
                    "file": sub_file or "System.json",
                    "subject": {"name": subject, "id": None, "scope": "single"},
                    "field": None,
                    "value": None,
                }
            )
            continue

        # DELETE
        if action == "DELETE":
            ops.append(
                {
                    "op": "delete",
                    "file": sub_file or "System.json",
                    "subject": {"name": subject, "id": sub_id, "scope": "single"},
                    "field": None,
                    "value": None,
                }
            )
            continue

        # READ
        if action == "READ":
            ops.append(
                {
                    "op": "read",
                    "file": sub_file or "System.json",
                    "subject": {"name": subject, "id": sub_id, "scope": "single"},
                    "field": prop if prop else None,
                    "value": None,
                }
            )
            continue

        # UPDATE — property 로 field 결정
        if action == "UPDATE":
            if not prop and not value_str:
                return []  # 뭘 수정하는지 모름

            # System.json 필드 우선 감지 — sub_cls 매칭 여부와 무관하게
            # "게임 화폐 단위를 크레딧으로"/"게임 타이틀을 리버스 월드로" 등
            sys_field = _detect_system_field(subject, prop)
            if sys_field and value_str:
                logger.info("[Step5] System.json 필드 우선 감지: %s = %s", sys_field, value_str)
                ops.append(
                    {
                        "op": "update",
                        "file": "System.json",
                        "subject": None,
                        "field": sys_field,
                        "value": {
                            "kind": "string",
                            "ref": None,
                            "new_value": value_str,
                            "type_hint": None,
                            "array_op": None,
                            "match_hint": None,
                        },
                    }
                )
                continue

            # value 에 대한 분류 정보 (참조 엔티티일 수 있음) — 완전 → 부분 일치
            val_cls = None
            if value_str:
                val_cls = cls_by_name.get(value_str.lower())
                if not val_cls:
                    for cname, cval in cls_by_name.items():
                        if value_str.lower() in cname or cname in value_str.lower():
                            val_cls = cval
                            break

            # property 가 없으면 value 의 카테고리로 추론
            if not prop and val_cls:
                val_cat = (val_cls.get("category") or "").lower()
                prop = _infer_property_from_value_category(val_cat)

            if not prop:
                return []  # field 결정 불가

            # property → field 매핑
            field_info = _lookup_property_field(prop)
            if not field_info:
                return []

            field, kind = field_info

            # 상대값 처리 ("1.5배"/"절반"/"50%") — param/param_slot 만 대상
            resolved_value_str = value_str
            if kind in ("param", "param_slot") and sub_id is not None and sub_file:
                abs_value = _resolve_relative_value(value_str, game_id, sub_file, sub_id, field)
                if abs_value is not None:
                    logger.info(
                        "[Step5] 상대값 변환: '%s' → %s (file=%s id=%s field=%s)",
                        value_str,
                        abs_value,
                        sub_file,
                        sub_id,
                        field,
                    )
                    resolved_value_str = str(abs_value)

            # value 구성
            ir_value = _build_direct_ir_value(
                field,
                kind,
                resolved_value_str,
                val_cls,
                extracted_ids,
                prop=prop,
            )

            ops.append(
                {
                    "op": "update",
                    "file": sub_file,
                    "subject": {"name": subject, "id": sub_id, "scope": "single"},
                    "field": field,
                    "value": ir_value,
                }
            )
            continue

        # 알 수 없는 action
        return []

    return ops


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────


_KOREAN_NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}


def _parse_relative_multiplier(value_str: str) -> float | None:
    """value_str 에서 상대 배율을 추출. 없으면 None.

    지원 패턴:
      - "1.5배", "2배", "0.5배"
      - "두배" / "세배"
      - "절반" / "반"
      - "50%" / "150%" / "50퍼센트"
    """
    import re

    s = (value_str or "").strip()
    if not s:
        return None

    if s in ("절반", "반"):
        return 0.5

    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*배\s*", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None

    for kw, n in _KOREAN_NUM.items():
        if s == f"{kw}배":
            return float(n)

    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:%|퍼센트)\s*", s)
    if m:
        try:
            return float(m.group(1)) / 100.0
        except ValueError:
            return None

    return None


def _resolve_relative_value(
    value_str: str, game_id: str, sub_file: str, sub_id: int, field: str
) -> int | float | None:
    """대상 entity 의 현재 필드 값을 읽어 상대값을 절대값으로 환산.

    field 예: "initialLevel", "params[2]". param_slot 은 params 배열 인덱스만 교체.
    변환 불가(매칭 안 됨, 현재 값 없음)면 None.
    """
    multiplier = _parse_relative_multiplier(value_str)
    if multiplier is None:
        return None

    try:
        from agent.utils.game_data_io import read_game_json

        data = read_game_json(game_id, sub_file)
    except Exception as e:
        logger.warning("[Step5] 상대값 변환 실패 — 파일 읽기 오류: %s", e)
        return None

    if not isinstance(data, list):
        return None

    entry = None
    for item in data:
        if isinstance(item, dict) and item.get("id") == sub_id:
            entry = item
            break
    if entry is None:
        return None

    # field = "params[N]" → params 배열 인덱스
    if field.startswith("params[") and field.endswith("]"):
        try:
            idx = int(field[len("params[") : -1])
        except ValueError:
            return None
        params_arr = entry.get("params")
        if not isinstance(params_arr, list) or idx >= len(params_arr):
            return None
        try:
            current = float(params_arr[idx])
        except (TypeError, ValueError):
            return None
    else:
        cur = entry.get(field)
        if cur is None:
            return None
        try:
            current = float(cur)
        except (TypeError, ValueError):
            return None

    result = current * multiplier
    # 정수였던 필드는 정수로 반환
    if float(int(result)) == result:
        return int(result)
    return result


def _lookup_property_field(prop: str) -> tuple[str, str] | None:
    """property 문자열에서 field 매핑을 찾는다. 완전 일치 → 부분 일치."""
    t = prop.lower().replace(" ", "")
    # 완전 일치
    for key, val in PROPERTY_TO_FIELD.items():
        if key.replace(" ", "") == t:
            return val
    # 부분 포함
    for key, val in PROPERTY_TO_FIELD.items():
        if key in prop or prop in key:
            return val
    return None


def _detect_system_field(subject: str, prop: str) -> str | None:
    """subject + property 에서 System.json 필드를 감지. 해당하면 필드명 반환."""
    combined = (subject + " " + prop).lower()
    if "제목" in combined or "타이틀" in combined:
        return "gameTitle"
    if "통화" in combined or "화폐" in combined:
        return "currencyUnit"
    return None


def _infer_property_from_value_category(val_cat: str) -> str:
    """value 의 카테고리에서 property 를 추론."""
    return {
        "skill": "스킬",
        "weapon": "무기",
        "armor": "장비",
        "class": "직업",
        "item": "드롭",
        "state": "속성",
        "element": "속성",
    }.get(val_cat, "")


def _build_direct_ir_value(
    field: str,
    kind: str,
    value_str: str,
    val_cls: dict | None,
    extracted_ids: dict,
    prop: str = "",
) -> dict:
    """직접 변환용 IR value 생성."""
    val_id = None
    if val_cls:
        mid = val_cls.get("mapped_id")
        if isinstance(mid, int):
            val_id = mid
        elif isinstance(mid, str) and mid.isdigit():
            val_id = int(mid)
    if val_id is None and value_str:
        val_id = extracted_ids.get(value_str)

    # 참조 필드 (learnings, equips, classId, actions, dropItems)
    if kind in ("skill", "weapon", "armor", "class", "item"):
        return {
            "kind": kind,
            "ref": value_str if value_str else None,
            "new_value": None,
            "type_hint": prop if prop else None,  # "방패", "장신구" 등 슬롯 힌트
            "array_op": None,
            "match_hint": None,
        }

    # trait 관련
    if kind == "trait":
        return {
            "kind": "trait",
            "ref": value_str if value_str else None,
            "new_value": None,
            "type_hint": None,
            "array_op": "update",
            "match_hint": "공격 속성" if "속성" in field or "공격" in (value_str or "") else None,
        }

    # 경험치 곡선 (Classes.expParams) — 의미 키워드 → 프리셋 배열 매핑
    if kind == "exp_curve":
        preset: list[int] | None = None
        if value_str:
            v = value_str.strip()
            for key, arr in EXP_CURVE_PRESETS.items():
                if key in v:
                    preset = list(arr)
                    break
        return {
            "kind": "exp_curve",
            "ref": None,
            "new_value": preset,
            "type_hint": None,
            "array_op": None,
            "match_hint": None,
        }

    # 능력치 슬롯 (params 배열 인덱스)
    if kind == "param_slot":
        try:
            num = int(value_str) if value_str else None
        except ValueError:
            try:
                num = float(value_str)
            except ValueError:
                num = None
        return {
            "kind": "param_slot",
            "ref": None,
            "new_value": num,
            "type_hint": None,
            "array_op": None,
            "match_hint": None,
        }

    # 단순 값 (string, param)
    if kind == "param":
        try:
            num = int(value_str) if value_str else None
        except ValueError:
            try:
                num = float(value_str)
            except ValueError:
                num = None
        return {
            "kind": "param",
            "ref": None,
            "new_value": num,
            "type_hint": None,
            "array_op": None,
            "match_hint": None,
        }

    # string
    return {
        "kind": "string",
        "ref": None,
        "new_value": value_str if value_str else None,
        "type_hint": None,
        "array_op": None,
        "match_hint": None,
    }
