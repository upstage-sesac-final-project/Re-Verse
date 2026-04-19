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


# ── Skills.json ─────────────────────────────────────────────────
SKILL_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Skills.json",
    "base_fields": ["name"],
    "fixed_fields": {"messageType": 1},
    "required_slots": [
        {"name": "stypeId", "type": "int", "ge": 0, "hint": "스킬 유형 (공격=1, 특수=2 등 System.skillTypes)"},
        {"name": "mpCost", "type": "int", "ge": 0, "le": 9999, "hint": "소비 MP. 공격 스킬은 보통 4-20"},
        {"name": "tpCost", "type": "int", "ge": 0, "le": 100, "hint": "소비 TP. 기본 0"},
        {"name": "scope", "type": "int", "ge": 0, "le": 14, "hint": "범위 (1=적 1, 2=적 전체, 7=아군 1 등)"},
        {"name": "occasion", "type": "int", "ge": 0, "le": 3, "hint": "사용 가능 시점 (0=언제나, 1=전투 중, 3=메뉴 전용)"},
        {"name": "speed", "type": "int", "ge": -2000, "le": 2000, "hint": "속도 보정. 보통 0"},
        {"name": "successRate", "type": "int", "ge": 1, "le": 100, "hint": "성공률. 기본 100"},
        {"name": "repeats", "type": "int", "ge": 1, "le": 9, "hint": "연속 횟수. 기본 1"},
        {"name": "tpGain", "type": "int", "ge": 0, "le": 100, "hint": "TP 획득. 공격 스킬 10 표준"},
        {"name": "hitType", "type": "int", "ge": 0, "le": 2, "hint": "명중 유형 (0=확정, 1=물리, 2=마법)"},
        {"name": "animationId", "type": "int", "ge": -1, "hint": "애니메이션 id"},
        {
            "name": "damage",
            "type": "dict",
            "hint": "damage = {type, elementId, formula, critical, variance}. formula 는 'a.atk*4 - b.def*2' 같은 문자열",
        },
    ],
    "optional_slots": [
        {"name": "description", "type": "str"},
        {"name": "iconIndex", "type": "int", "ge": 0},
        {"name": "message1", "type": "str", "hint": "행동 메시지 첫 줄"},
        {"name": "message2", "type": "str", "hint": "행동 메시지 둘째 줄"},
        {"name": "requiredWtypeId1", "type": "int", "ge": 0, "hint": "필요 무기 유형 1. 없으면 0"},
        {"name": "requiredWtypeId2", "type": "int", "ge": 0, "hint": "필요 무기 유형 2. 없으면 0"},
        {"name": "effects", "type": "list[Effect]", "hint": "추가 효과. 상태 부여·HP 회복 등"},
    ],
}


# ── Items.json ──────────────────────────────────────────────────
ITEM_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Items.json",
    "base_fields": ["name"],
    "required_slots": [
        {
            "name": "itypeId",
            "type": "int",
            "ge": 1,
            "le": 4,
            "hint": "아이템 유형 (1=일반, 2=key 아이템)",
        },
        {"name": "price", "type": "int", "ge": 0, "le": 999999},
        {"name": "consumable", "type": "bool", "hint": "소모품 여부"},
        {"name": "scope", "type": "int", "ge": 0, "le": 14, "hint": "사용 범위"},
        {"name": "occasion", "type": "int", "ge": 0, "le": 3, "hint": "사용 시점"},
        {"name": "speed", "type": "int", "ge": 0, "le": 2000},
        {"name": "successRate", "type": "int", "ge": 1, "le": 100},
        {"name": "repeats", "type": "int", "ge": 1, "le": 9},
        {"name": "tpGain", "type": "int", "ge": 0, "le": 100},
        {"name": "hitType", "type": "int", "ge": 0, "le": 2},
        {"name": "animationId", "type": "int", "ge": -1},
        {"name": "damage", "type": "dict", "hint": "피해 정의 — 회복 아이템은 type=3 (HP 회복)"},
    ],
    "optional_slots": [
        {"name": "description", "type": "str"},
        {"name": "iconIndex", "type": "int", "ge": 0},
        {
            "name": "effects",
            "type": "list[Effect]",
            "hint": "효과. 회복 아이템은 [{code:11, value1>=1, ...}] 형태 (value1>=1 필수)",
        },
    ],
}


# ── Classes.json ────────────────────────────────────────────────
CLASS_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Classes.json",
    "base_fields": ["name"],
    "required_slots": [
        {
            "name": "expParams",
            "type": "list[int]",
            "length": 4,
            "hint": "EXP 곡선 [base, extra, acc_a, acc_b]. 표준 [30, 20, 20, 40]",
        },
        {
            "name": "params",
            "type": "list[list[int]]",
            "length": 8,
            "hint": "능력치 곡선 [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK]. 각 요소는 레벨별 값 리스트",
        },
    ],
    "optional_slots": [
        {
            "name": "learnings",
            "type": "list[Learning]",
            "hint": "[{level, skillId, note}] — 레벨별 습득 스킬",
        },
        {"name": "traits", "type": "list[Trait]", "hint": "장비 유형/스킬 유형 허용 등"},
    ],
}


# ── Enemies.json ────────────────────────────────────────────────
ENEMY_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "Enemies.json",
    "base_fields": ["name"],
    "required_slots": [
        {"name": "battlerName", "type": "str", "hint": "전투 스프라이트 파일명 (예: 'Bat')"},
        {"name": "battlerHue", "type": "int", "ge": 0, "le": 360, "hint": "색조 (보통 0)"},
        {
            "name": "params",
            "type": "list[int]",
            "length": 8,
            "hint": "[MHP>=1, MMP, ATK, DEF, MAT, MDF, AGI, LUK]. 파티 레벨 대비 조정",
        },
        {"name": "exp", "type": "int", "ge": 0, "le": 9999999, "hint": "처치 시 EXP"},
        {"name": "gold", "type": "int", "ge": 0, "le": 9999999, "hint": "처치 시 소지금"},
    ],
    "optional_slots": [
        {"name": "dropItems", "type": "list[DropItem]", "hint": "[{kind, dataId, denominator}]"},
        {"name": "actions", "type": "list[Action]", "hint": "행동 패턴"},
        {"name": "traits", "type": "list[Trait]", "hint": "속성 내성·저항"},
    ],
    "resource_fields": ["battlerName"],
}


# ── States.json ─────────────────────────────────────────────────
STATE_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "States.json",
    "base_fields": ["name"],
    "fixed_fields": {"messageType": 1, "overlay": 0},
    "required_slots": [
        {"name": "iconIndex", "type": "int", "ge": 0, "hint": "상태 아이콘 인덱스"},
        {"name": "restriction", "type": "int", "ge": 0, "le": 4, "hint": "행동 제한 (0=없음, 2=적으로 공격 등)"},
        {"name": "priority", "type": "int", "ge": 0, "le": 100, "hint": "우선권. 기본 50"},
        {"name": "motion", "type": "int", "ge": 0, "le": 3, "hint": "[SV] 모션 번호"},
        {
            "name": "autoRemovalTiming",
            "type": "int",
            "ge": 0,
            "le": 2,
            "hint": "자동 해제 타이밍 (0=없음, 1=행동 종료시, 2=턴 종료시)",
        },
        {"name": "minTurns", "type": "int", "ge": 0, "le": 9999, "hint": "지속 최소 턴"},
        {"name": "maxTurns", "type": "int", "ge": 0, "le": 9999, "hint": "지속 최대 턴"},
        {"name": "chanceByDamage", "type": "int", "ge": 0, "le": 100, "hint": "피해 해제 확률"},
        {"name": "stepsToRemove", "type": "int", "ge": 1, "le": 9999, "hint": "보행 해제 걸음 수"},
    ],
    "optional_slots": [
        {"name": "removeAtBattleEnd", "type": "bool"},
        {"name": "removeByRestriction", "type": "bool"},
        {"name": "removeByDamage", "type": "bool"},
        {"name": "removeByWalking", "type": "bool"},
        {"name": "releaseByDamage", "type": "bool"},
        {"name": "message1", "type": "str", "hint": "액터가 해당 상태 됐을 때"},
        {"name": "message2", "type": "str", "hint": "적이 해당 상태 됐을 때"},
        {"name": "message3", "type": "str", "hint": "지속 메시지"},
        {"name": "message4", "type": "str", "hint": "해제 메시지"},
        {"name": "traits", "type": "list[Trait]"},
    ],
}


# ── System.json ─────────────────────────────────────────────────
# System 은 단일 dict 파일. create 는 없고 update 만 있으므로 "append_system_type"
# 액션에서만 쓰임. 일반 create 경로는 미사용.
SYSTEM_FILL_SCHEMA: dict[str, Any] = {
    "target_file": "System.json",
    "base_fields": [],
    "required_slots": [
        {
            "name": "value",
            "type": "str",
            "hint": "System.json 배열 (elements/weaponTypes 등) 에 추가할 값",
        },
    ],
    "optional_slots": [],
}


# ── 레지스트리 ──────────────────────────────────────────────────
FILL_SCHEMAS: dict[str, dict[str, Any]] = {
    "Weapons.json": WEAPONS_FILL_SCHEMA,
    "Armors.json": ARMOR_FILL_SCHEMA,
    "Actors.json": ACTOR_FILL_SCHEMA,
    # Phase E-2 신규
    "Skills.json": SKILL_FILL_SCHEMA,
    "Items.json": ITEM_FILL_SCHEMA,
    "Classes.json": CLASS_FILL_SCHEMA,
    "Enemies.json": ENEMY_FILL_SCHEMA,
    "States.json": STATE_FILL_SCHEMA,
    "System.json": SYSTEM_FILL_SCHEMA,
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
