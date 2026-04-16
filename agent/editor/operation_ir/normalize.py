"""operation_ir 정규화 (Step 6) — Step 5 fallback.

Definition Step 6 이 LLM 으로 생성한 modifications 를 operation_tuples 로 변환.
Step 5(build.py) 경로가 실패했을 때만 호출된다.

modification 형식 (LLM 출력):
    {
        "type": "create" | "update" | "delete" | "query",
        "target": "actor" | "enemy" | ...,
        "params": {
            # create: {"name": ..., "description": ..., ...}
            # update: {"selector": {...}, "updates": {...}}
            # query: {"searchTerm": ...}
        }
    }

operation_tuple 형식: agent/editor/operation_ir/types.py 참고.
"""

from __future__ import annotations

from agent.constants import CATEGORY_TO_FILE

# System.json 전용 확장 (element, system 카테고리를 System.json 으로 매핑)
_TARGET_TO_FILE: dict[str, str] = {
    **CATEGORY_TO_FILE,
    "element": "System.json",
    "system": "System.json",
}


def normalize_modifications(
    modifications: list[dict],
    extracted_ids: dict,
) -> list[dict]:
    """기존 modifications 를 operation_tuples (operation IR) 로 변환."""
    op_type_map = {
        "create": "create",
        "update": "update",
        "delete": "delete",
        "query": "read",
        "read": "read",
    }

    result: list[dict] = []
    for mod in modifications:
        mod_type = (mod.get("type") or "").lower()
        target = (mod.get("target") or "").lower()
        params = mod.get("params") or {}

        op = op_type_map.get(mod_type)
        file = _TARGET_TO_FILE.get(target)
        if not op or not file:
            continue

        if op == "create":
            tuples = _create_to_ir(file, target, params, extracted_ids)
        elif op == "update":
            tuples = _update_to_ir(file, target, params, extracted_ids)
        elif op == "delete":
            tuples = _delete_to_ir(file, target, params, extracted_ids)
        elif op == "read":
            tuples = _read_to_ir(file, target, params)
        else:
            tuples = []

        result.extend(tuples)

    return result


# ──────────────────────────────────────────────
# 내부 헬퍼 — op 종류별 변환
# ──────────────────────────────────────────────


def _create_to_ir(
    file: str,
    target: str,
    params: dict,
    extracted_ids: dict,
) -> list[dict]:
    """create modification → operation IR.

    profiler 가 세부 필드를 채우므로, IR 은 name 만 담는다.
    맵 생성 시 original_file_name 이 params 에 있으면 value 에 포함한다.
    """
    name = params.get("name") or params.get(f"{target}_name") or ""
    value = None
    if target == "map" and "original_file_name" in params:
        value = {"kind": "map_creation", "original_file_name": params["original_file_name"]}
    return [
        {
            "op": "create",
            "file": file,
            "subject": {"name": name, "id": None, "scope": "single"} if name else None,
            "field": None,
            "value": value,
        }
    ]


def _update_to_ir(
    file: str,
    target: str,
    params: dict,
    extracted_ids: dict,
) -> list[dict]:
    """update modification → operation IR.

    세부 필드 값(params, traits, effects 등)은 profiler 책임이므로 여기서는
    스칼라 필드(name, initialLevel 등)만 raw_updates 로 전달한다.
    배열/복합 필드는 field 이름만 남기고 값은 버린다.
    """
    selector = params.get("selector") or {}
    updates = params.get("updates") or {}

    # selector 분해
    if isinstance(selector, dict):
        scope = "all" if selector.get("mode") == "all" else "single"
        sub_name = selector.get("name")
        sub_id = selector.get("id")
    else:
        scope = "single"
        sub_name = params.get("name")
        sub_id = None

    # extracted_ids 에서 id 보완
    if sub_id is None and sub_name:
        sub_id = extracted_ids.get(sub_name)

    subject = None
    if scope == "all":
        subject = {"name": None, "id": None, "scope": "all"}
    elif sub_name or sub_id:
        subject = {"name": sub_name, "id": sub_id, "scope": "single"}

    if not updates or not isinstance(updates, dict):
        return []

    # profiler 가 채울 복합 필드(traits, effects, params 등)는 버리고,
    # 스칼라 + 참조 필드(equips, classId 등)는 남긴다.
    _PROFILER_FIELDS = {
        "traits",
        "effects",
        "damage",
        "params",
        "actions",
        "dropItems",
        "learnings",
    }
    filtered_updates = {k: v for k, v in updates.items() if k not in _PROFILER_FIELDS}

    if not filtered_updates:
        return []

    return [
        {
            "op": "update",
            "file": file,
            "subject": subject,
            "field": None,
            "value": {
                "kind": "updates",
                "ref": None,
                "new_value": None,
                "type_hint": None,
                "array_op": None,
                "match_hint": None,
                "raw_updates": filtered_updates,
            },
        }
    ]


def _delete_to_ir(
    file: str,
    target: str,
    params: dict,
    extracted_ids: dict,
) -> list[dict]:
    selector = params.get("selector") or {}
    if isinstance(selector, dict):
        sub_name = selector.get("name") or params.get("name")
        sub_id = selector.get("id")
    else:
        sub_name = params.get("name")
        sub_id = None
    if sub_id is None and sub_name:
        sub_id = extracted_ids.get(sub_name)

    return [
        {
            "op": "delete",
            "file": file,
            "subject": {"name": sub_name, "id": sub_id, "scope": "single"},
            "field": None,
            "value": None,
        }
    ]


def _read_to_ir(file: str, target: str, params: dict) -> list[dict]:
    name = params.get("searchTerm") or params.get("name")
    return [
        {
            "op": "read",
            "file": file,
            "subject": {"name": name, "id": None, "scope": "single"} if name else None,
            "field": params.get("property"),
            "value": None,
        }
    ]
