"""fill_schemas — planner 가 profiler 에게 전달하는 "빈칸 명세" 상수.

YB.md 4 / 8-9 기반. pydantic 모델 (`agent/schemas/*.py`) 을 그대로 유지하되
profiler 가 LLM 에게 지시할 때 쓸 메타데이터 레이어를 별도로 둔다.

Phase E 1차: Weapons / Armor / Actor 3 종.
Phase E 2차: Skill / Items / Class / Enemy / State / System / Event 확장 예정.
"""

from __future__ import annotations

from typing import Any

# ── Trait 프리셋 ─────────────────────────────────────────────────
# YB.md 8-9 미확정 메모: 복잡한 Trait (code/dataId/value) 를 profiler 가 직접
# 만들기보다 프리셋 이름 → Trait dict 변환으로 안전성 확보.
# 여기서는 최소 preset 만 정의하고 Phase I / I+ 에서 확장.

TRAIT_PRESETS: dict[str, dict[str, Any]] = {
    # 속성 부여 / 저항 관련 대표 프리셋
    # code 11 = 요소 효과 (dataId = element id, value = multiplier)
    "불속성_부여_1.5x": {"code": 11, "dataId": 2, "value": 1.5},
    "물속성_부여_1.5x": {"code": 11, "dataId": 3, "value": 1.5},
    "바람속성_부여_1.5x": {"code": 11, "dataId": 4, "value": 1.5},
    "땅속성_부여_1.5x": {"code": 11, "dataId": 5, "value": 1.5},
    # 상태 내성 (code 13 = 상태 저항)
    "독저항_50%": {"code": 13, "dataId": 4, "value": 0.5},
    "침묵저항_50%": {"code": 13, "dataId": 6, "value": 0.5},
}


# ── Weapons.json ────────────────────────────────────────────────
WEAPONS_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Weapons.json",
    "base_fields": ["name"],
    "fixed_fields": {"etypeId": 1},  # 무기는 etypeId=1 고정
    "required_slots": [
        {
            "name": "wtypeId",
            "type": "int",
            "ge": 0,
            "hint": "무기 유형 (검=1, 도끼=2, 활=3, 지팡이=4 등 Types.json weaponTypes 참조)",
        },
        {
            "name": "price",
            "type": "int",
            "ge": 0,
            "le": 999999,
            "hint": "가격. 보통 공격력 × 50 기준. 기존 최상위 무기 대비 상대 조정",
        },
        {
            "name": "animationId",
            "type": "int",
            "ge": -1,
            "le": 120,
            "hint": "공격 모션 애니메이션 id. 검류 표준 / 원거리 표준 등",
        },
        {
            "name": "iconIndex",
            "type": "int",
            "ge": 0,
            "hint": "아이콘 시트 인덱스. 무기 유형별 표준값",
        },
        {
            "name": "params",
            "type": "list[int]",
            "length": 8,
            "hint": "[MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK] 능력치 변화량. ATK 외 대부분 0",
        },
    ],
    "optional_slots": [
        {"name": "description", "type": "str", "hint": "장비 설명 한 줄"},
        {"name": "note", "type": "str", "hint": "노트 필드. 비워도 무방"},
        {
            "name": "traits",
            "type": "list[Trait]",
            "hint": "특성. 요소 속성·상태 부여·저항 등. TRAIT_PRESETS 참조",
        },
    ],
}


# ── Armors.json ─────────────────────────────────────────────────
ARMOR_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Armors.json",
    "base_fields": ["name"],
    "fixed_fields": {},  # etypeId 는 유저 의도에 따라 결정 (방패=2, 머리=3, 몸=4, 장신구=5)
    "required_slots": [
        {
            "name": "atypeId",
            "type": "int",
            "ge": 0,
            "le": 6,
            "hint": "방어구 유형 (일반=1, 마법=2 등 Types.json armorTypes 참조)",
        },
        {
            "name": "etypeId",
            "type": "int",
            "ge": 2,
            "le": 5,
            "hint": "장비 슬롯 (방패=2, 머리=3, 몸=4, 장신구=5). 유저 언급으로 결정",
        },
        {
            "name": "price",
            "type": "int",
            "ge": 0,
            "le": 999999,
            "hint": "가격. 보통 방어력 × 60 기준",
        },
        {
            "name": "iconIndex",
            "type": "int",
            "ge": 0,
            "hint": "아이콘 인덱스. 방어구 유형별 표준",
        },
        {
            "name": "params",
            "type": "list[int]",
            "length": 8,
            "hint": "[MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]. 방어구는 DEF/MDF 위주",
        },
    ],
    "optional_slots": [
        {"name": "description", "type": "str"},
        {"name": "note", "type": "str"},
        {
            "name": "traits",
            "type": "list[Trait]",
            "hint": "속성 저항·상태 저항 등. TRAIT_PRESETS 참조",
        },
    ],
}


# ── Actors.json ─────────────────────────────────────────────────
ACTOR_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Actors.json",
    "base_fields": ["name"],
    "required_slots": [
        {
            "name": "classId",
            "type": "int",
            "ge": 1,
            "hint": "직업 id. reference_checks 로 확인됨. 없으면 definition hold",
        },
        {
            "name": "initialLevel",
            "type": "int",
            "ge": 1,
            "le": 99,
            "hint": "초기 레벨. 주인공은 1, 동료는 합류 시점 레벨",
        },
        {
            "name": "maxLevel",
            "type": "int",
            "ge": 1,
            "le": 99,
            "hint": "최대 레벨. 기본 99",
        },
        {
            "name": "faceName",
            "type": "str",
            "hint": "얼굴 이미지 파일명 (예: 'Actor1'). 리소스 존재 여부 확인 필요",
        },
        {"name": "faceIndex", "type": "int", "ge": 0, "le": 7, "hint": "얼굴 시트 인덱스"},
        {"name": "characterName", "type": "str", "hint": "보행 캐릭터 파일명"},
        {"name": "characterIndex", "type": "int", "ge": 0, "le": 7},
        {"name": "battlerName", "type": "str", "hint": "전투 스프라이트 파일명 (예: 'Actor1_1')"},
    ],
    "optional_slots": [
        {"name": "nickname", "type": "str", "hint": "별명. 유저가 말 안 하면 빈 문자열"},
        {"name": "profile", "type": "str", "hint": "설명. 캐릭터 배경 한두 문장"},
        {
            "name": "equips",
            "type": "list[int]",
            "hint": "초기 장비 id 리스트. 길이는 classId 설정을 따름",
        },
        {"name": "note", "type": "str"},
        {"name": "traits", "type": "list[Trait]"},
    ],
    "resource_fields": ["faceName", "characterName", "battlerName"],
}


# ── 레지스트리 ──────────────────────────────────────────────────
FILL_SCHEMAS: dict[str, dict[str, Any]] = {
    "Weapons.json": WEAPONS_FILL_SCHEMA,
    "Armors.json": ARMOR_FILL_SCHEMA,
    "Actors.json": ACTOR_FILL_SCHEMA,
}


def get_fill_schema(target_file: str) -> dict[str, Any] | None:
    """target_file 에 해당하는 fill_schema 반환. 없으면 None.

    Phase E 1차 범위: Weapons.json / Armors.json / Actors.json.
    그 외 target_file 은 None → planner 가 fill_slots 미생성 (profiler 가 기존 경로 사용).
    """
    return FILL_SCHEMAS.get(target_file)


def build_fill_slots(step_id: int, target_file: str) -> list[dict[str, Any]]:
    """한 step 의 required_slots 를 fill_slots 포맷으로 평탄화.

    optional_slots 는 유저 description 언급 시에만 채우니 planner 단에서는 생략.
    Profiler 가 description 을 보고 추가 fill_slot 을 동적으로 주입할 수 있다.
    """
    schema = get_fill_schema(target_file)
    if not schema:
        return []
    slots: list[dict[str, Any]] = []
    for s in schema.get("required_slots", []):
        slots.append(
            {
                "step_id": step_id,
                "field_name": s["name"],
                "type": s.get("type", "str"),
                "hint": s.get("hint", ""),
                # bounds / length 정보도 통째로 실어 보냄
                **{k: v for k, v in s.items() if k not in ("name", "type", "hint")},
            }
        )
    return slots
