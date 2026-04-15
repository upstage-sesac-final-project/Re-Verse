"""agent 전역 상수 — RPG Maker MZ 카테고리/파일/필드 매핑.

여러 노드(definition, planner, resolver, profiler 등)가 공유하는 매핑을
한 곳에서 관리한다.
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────
# 카테고리 ↔ 파일 매핑
# ──────────────────────────────────────────────

# 사용: definition.py, operation_ir/resolve.py, operation_ir/normalize.py
CATEGORY_TO_FILE: dict[str, str] = {
    "actor": "Actors.json",
    "enemy": "Enemies.json",
    "item": "Items.json",
    "skill": "Skills.json",
    "weapon": "Weapons.json",
    "armor": "Armors.json",
    "class": "Classes.json",
    "state": "States.json",
    "map": "MapInfos.json",
}

FILE_TO_CATEGORY: dict[str, str] = {v: k for k, v in CATEGORY_TO_FILE.items()}

# 사용: definition.py, reader.py, game_data_io.py
CATEGORY_TO_PLURAL: dict[str, str] = {
    "actor": "Actors",
    "enemy": "Enemies",
    "item": "Items",
    "skill": "Skills",
    "weapon": "Weapons",
    "armor": "Armors",
    "class": "Classes",
    "state": "States",
    "element": "System",
    "system": "System",
}

# 사용: definition.py
CATEGORY_TO_ID_FIELD: dict[str, str] = {
    "actor": "actor_id",
    "enemy": "enemy_id",
    "item": "item_id",
    "skill": "skill_id",
    "weapon": "weapon_id",
    "armor": "armor_id",
    "class": "class_id",
    "state": "state_id",
    "element": "element_id",
}

# 사용: planner/rule_engine.py
ALL_ENTITY_FILES: tuple[str, ...] = tuple(CATEGORY_TO_FILE.values())

# ──────────────────────────────────────────────
# 엔티티 파일 집합
# ──────────────────────────────────────────────

# 사용: executor_v2/handlers/entity.py
ENTITY_FILES: frozenset[str] = frozenset(CATEGORY_TO_FILE.values())
ALL_SUPPORTED_FILES: frozenset[str] = ENTITY_FILES | {"System.json"}

# ──────────────────────────────────────────────
# 한국어 키워드 → 카테고리 매핑
# ──────────────────────────────────────────────

# 사용: definition.py — Step 2 이후 category 보정
# LLM이 분류를 놓치는 경우에 대한 하드코딩 fallback
KEYWORD_TO_CATEGORY: dict[str, str] = {
    "주인공": "Actor",
    "캐릭터": "Actor",
    "액터": "Actor",
    "적": "Enemy",
    "몬스터": "Enemy",
    "아이템": "Item",
    "스킬": "Skill",
    "무기": "Weapon",
    "방어구": "Armor",
    "직업": "Class",
    "상태이상": "State",
}

# ──────────────────────────────────────────────
# 배열 필드
# ──────────────────────────────────────────────

# 사용: definition.py, planner/rule_engine.py
ARRAY_FIELDS: frozenset[str] = frozenset(
    {
        "traits",
        "effects",
        "actions",
        "dropItems",
        "learnings",
    }
)

# ──────────────────────────────────────────────
# System.json 관련
# ──────────────────────────────────────────────

# 사용: planner/rule_engine.py
SYSTEM_TYPE_ARRAYS: dict[str, str] = {
    "elements": "elements",
    "skillTypes": "skillTypes",
    "weaponTypes": "weaponTypes",
    "armorTypes": "armorTypes",
    "equipTypes": "equipTypes",
}

# 사용: operation_ir/resolve.py
KIND_TO_SYSTEM_KEY: dict[str, str] = {
    "element": "elements",
    "weapon_type": "weaponTypes",
    "armor_type": "armorTypes",
    "skill_type": "skillTypes",
    "equip_type": "equipTypes",
}

# 사용: planner/rule_engine.py
SYSTEM_DEDICATED_FIELDS: dict[str, str] = {
    "gameTitle": "update_game_title",
    "game_title": "update_game_title",
}

# 사용: planner/rule_engine.py
SYSTEM_TYPE_ARRAY_NAMES: frozenset[str] = frozenset(
    {
        "skillTypes",
        "weaponTypes",
        "armorTypes",
        "equipTypes",
        "elements",
    }
)

# ──────────────────────────────────────────────
# 검색 임계값 / 전역 설정
# ──────────────────────────────────────────────

# 사용: planner/rule_engine.py
FUZZY_THRESHOLD: float = 0.6

# 사용: validator/__init__.py
MAX_RETRY: int = 2

# ──────────────────────────────────────────────
# 능력치 (params) 매핑
# ──────────────────────────────────────────────

# 사용: utils/traits_reference.py
PARAM_NAMES: list[str] = ["MaxHP", "MaxMP", "ATK", "DEF", "MAT", "MDF", "AGI", "LUK"]

# 사용: utils/traits_reference.py
PARAM_KOREAN: dict[int, str] = {
    0: "최대 HP",
    1: "최대 MP",
    2: "공격력",
    3: "방어력",
    4: "마법력",
    5: "마법방어",
    6: "민첩성",
    7: "행운",
}

# 사용: utils/traits_reference.py
PARAM_ALIASES: dict[str, int] = {
    "hp": 0,
    "체력": 0,
    "최대hp": 0,
    "최대 hp": 0,
    "mp": 1,
    "마나": 1,
    "최대mp": 1,
    "공격력": 2,
    "공격": 2,
    "atk": 2,
    "방어력": 3,
    "방어": 3,
    "def": 3,
    "마법력": 4,
    "마공": 4,
    "마법공격": 4,
    "mat": 4,
    "마법방어": 5,
    "마방": 5,
    "mdf": 5,
    "민첩": 6,
    "민첩성": 6,
    "스피드": 6,
    "agi": 6,
    "행운": 7,
    "luk": 7,
}

# ──────────────────────────────────────────────
# trait/effect 허용 코드 (스키마 검증용)
# ──────────────────────────────────────────────

# 사용: schemas/traits.py
ALLOWED_TRAIT_CODES: set[int] = {
    11,
    12,
    13,
    14,
    21,
    22,
    23,
    31,
    32,
    33,
    34,
    35,
    41,
    42,
    43,
    44,
    51,
    52,
    53,
    54,
    55,
    61,
    62,
    63,
    64,
}

# 사용: schemas/effects.py
ALLOWED_EFFECT_CODES: set[int] = {11, 12, 13, 21, 22, 31, 32, 33, 34, 41, 42, 43, 44}

# ──────────────────────────────────────────────
# trait/effect 코드 매핑 (RPG Maker MZ 엔진 스펙)
# ──────────────────────────────────────────────

# 사용: definition.py
TRAIT_CODE_TO_HINT: dict[int, str] = {
    11: "속성 내성",
    13: "상태 내성",
    21: "능력치 보정",
    22: "추가 능력치",
    31: "공격 속성",
    32: "공격 상태",
    41: "스킬 유형 추가",
    42: "스킬 유형 봉인",
    43: "스킬 추가",
    44: "스킬 봉인",
    51: "무기 유형 장비",
    52: "방어구 유형 장비",
}

# ──────────────────────────────────────────────
# trait/effect 의미→코드 매핑 (array_op 해석용)
# ──────────────────────────────────────────────

# 사용: planner/array_op_resolver.py
MATCH_HINT_TO_TRAIT_CODE: dict[str, int] = {
    "속성 내성": 11,
    "원소 내성": 11,
    "속성내성": 11,
    "약화 유효율": 12,
    "디버프 유효율": 12,
    "상태 내성": 13,
    "상태내성": 13,
    "상태이상 내성": 13,
    "능력치 보정": 21,
    "능력치 배율": 21,
    "스탯 배율": 21,
    "추가 능력치": 22,
    "명중": 22,
    "회피": 22,
    "공격 속성": 31,
    "공격속성": 31,
    "공격 원소": 31,
    "공격 상태": 32,
    "공격 시 상태": 32,
    "공격 시 상태 부여": 32,
    "공격 속도": 33,
    "공격속도": 33,
    "공격 횟수": 34,
    "공격 추가": 34,
    "스킬 유형 추가": 41,
    "스킬유형 추가": 41,
    "스킬 유형 봉인": 42,
    "스킬유형 봉인": 42,
    "스킬 추가": 43,
    "스킬 봉인": 44,
    "무기 유형 장비": 51,
    "무기유형": 51,
    "방어구 유형 장비": 52,
    "방어구유형": 52,
    "장비 고정": 53,
    "장비 봉인": 54,
    "추가 행동": 61,
    "특수 플래그": 62,
    "자동전투": 62,
    "소멸 효과": 63,
    "파티 능력": 64,
}

# 사용: planner/array_op_resolver.py
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

# 사용: planner/array_op_resolver.py
MATCH_HINT_TO_EFFECT_CODE: dict[str, int] = {
    "HP 회복": 11,
    "HP회복": 11,
    "MP 회복": 12,
    "MP회복": 12,
    "TP 획득": 13,
    "TP획득": 13,
    "상태 부여": 21,
    "상태부여": 21,
    "상태 해제": 22,
    "상태해제": 22,
    "버프": 31,
    "강화": 31,
    "디버프": 32,
    "약화": 32,
    "버프 해제": 33,
    "디버프 해제": 34,
    "특수 효과": 41,
    "도주": 41,
    "성장": 42,
    "스킬 습득": 43,
    "공용 이벤트": 44,
}

# ──────────────────────────────────────────────
# 파일 재라우팅 시 field 교정 (planner)
# TODO: Step4.6 안정화 시 제거 가능
# ──────────────────────────────────────────────

# 사용: planner/rule_engine.py
FIELD_REROUTE_FIXES: dict[str, dict[str, str | dict]] = {
    "damage.elementId": {
        "field": "traits",
        "value_patch": {"array_op": "update", "match_hint": "공격 속성"},
    },
    "elementId": {
        "field": "traits",
        "value_patch": {"array_op": "update", "match_hint": "공격 속성"},
    },
}

# ──────────────────────────────────────────────
# 한국어 property → RPG Maker field 매핑
# ──────────────────────────────────────────────

# 사용: definition.py
PROPERTY_TO_FIELD: dict[str, tuple[str, str]] = {
    # 스킬 관련
    "스킬": ("learnings", "skill"),
    "기술": ("learnings", "skill"),
    "마법": ("learnings", "skill"),
    # 장비 관련
    "장비": ("equips", "armor"),
    "무기": ("equips", "weapon"),
    "방어구": ("equips", "armor"),
    "장신구": ("equips", "armor"),
    "방패": ("equips", "armor"),
    "머리": ("equips", "armor"),
    "몸": ("equips", "armor"),
    "장착": ("equips", "armor"),
    # 직업 관련
    "직업": ("classId", "class"),
    "클래스": ("classId", "class"),
    # 단순 필드
    "이름": ("name", "string"),
    "닉네임": ("nickname", "string"),
    "프로필": ("profile", "string"),
    "설명": ("description", "string"),
    "레벨": ("initialLevel", "param"),
    "초기레벨": ("initialLevel", "param"),
    "최대레벨": ("maxLevel", "param"),
    "가격": ("price", "param"),
    "경험치": ("exp", "param"),
    "골드": ("gold", "param"),
    # 속성/특성 관련
    "속성": ("traits", "trait"),
    "공격속성": ("traits", "trait"),
    "내성": ("traits", "trait"),
    "약점": ("traits", "trait"),
    # 행동 관련
    "행동": ("actions", "skill"),
    "행동패턴": ("actions", "skill"),
    "드롭": ("dropItems", "item"),
    "드롭아이템": ("dropItems", "item"),
}

# ──────────────────────────────────────────────
# 정수 필드 집합 — LLM float→int 후처리용
# ──────────────────────────────────────────────

# 사용: profiler.py
INT_FIELDS_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "exp",
        "gold",
        "price",
        "stypeId",
        "mpCost",
        "tpCost",
        "scope",
        "occasion",
        "hitType",
        "successRate",
        "repeats",
        "tpGain",
        "animationId",
        "itypeId",
        "wtypeId",
        "etypeId",
        "atypeId",
        "classId",
        "initialLevel",
        "maxLevel",
        "iconIndex",
        "restriction",
        "priority",
    }
)

# 사용: profiler.py
INT_FIELDS_IN_ACTIONS: frozenset[str] = frozenset(
    {
        "conditionParam1",
        "conditionParam2",
        "conditionType",
        "rating",
        "skillId",
    }
)

# 사용: profiler.py
INT_FIELDS_IN_DROP_ITEMS: frozenset[str] = frozenset(
    {
        "dataId",
        "denominator",
        "kind",
    }
)

# 사용: profiler.py
INT_FIELDS_IN_LEARNINGS: frozenset[str] = frozenset(
    {
        "level",
        "skillId",
    }
)

# ──────────────────────────────────────────────
# profiler 전용
# ──────────────────────────────────────────────

# 사용: profiler.py
SKIP_FILES: frozenset[str] = frozenset({"System.json", "MapInfos.json", "Map"})

# 사용: profiler.py
FILE_NEEDS_COMMON: dict[str, list[str]] = {
    "Enemies.json": ["Trait"],
    "Actors.json": ["Trait"],
    "Armors.json": ["Trait"],
    "Weapons.json": ["Trait"],
    "Skills.json": ["Damage", "Effect", "scope"],
    "Items.json": ["Damage", "Effect", "scope"],
    "Classes.json": ["Trait"],
    "States.json": ["Trait"],
}

# ──────────────────────────────────────────────
# Trait 코드 상세 (프롬프트 빌더용)
# ──────────────────────────────────────────────

# 사용: utils/traits_reference.py
TRAIT_CODES: dict[int, dict[str, Any]] = {
    11: {
        "name": "원소 내성률",
        "dataId_meaning": "elementId — System.json elements 의 인덱스 (1=물리, 2=불, 3=얼음, ...)",
        "value_meaning": "배율 (1.0=정상, 0.0=완전 면역, 0.5=절반 피해, 2.0=2배 약점)",
        "example": '"슬라임이 불에 약함" → {code:11, dataId:2, value:2.0}',
    },
    12: {
        "name": "약화 유효율",
        "dataId_meaning": "paramId (0=HP, 1=MP, 2=ATK, 3=DEF, 4=MAT, 5=MDF, 6=AGI, 7=LUK)",
        "value_meaning": "배율 (1.0=정상, 0.0=면역)",
        "example": '"공격력 약화 면역" → {code:12, dataId:2, value:0.0}',
    },
    13: {
        "name": "상태이상 유효율",
        "dataId_meaning": "stateId — States.json 의 id",
        "value_meaning": "배율 (1.0=정상, 0.0=완전 면역)",
        "example": '"독 면역" → {code:13, dataId:<독 stateId>, value:0.0}',
    },
    14: {
        "name": "상태 무효화",
        "dataId_meaning": "stateId",
        "value_meaning": "0 (고정)",
        "example": '"수면 상태 무효" → {code:14, dataId:<수면 stateId>, value:0}',
    },
    21: {
        "name": "능력치 배율",
        "dataId_meaning": "paramId (0=HP, 1=MP, 2=ATK, 3=DEF, 4=MAT, 5=MDF, 6=AGI, 7=LUK)",
        "value_meaning": "배율 (1.0=기본, 1.2=+20%, 0.8=-20%)",
        "example": '"HP 20% 증가" → {code:21, dataId:0, value:1.2}',
    },
    22: {
        "name": "특수 능력치",
        "dataId_meaning": "0=명중, 1=회피, 2=치명타, 3=치명타회피, 4=마법회피, 5=마법반사, 6=반격, 7=HP재생, 8=MP재생, 9=TP재생",
        "value_meaning": "비율 (0.0~1.0, 0.1=10%)",
        "example": '"HP 자동 회복 5%" → {code:22, dataId:7, value:0.05}',
    },
    23: {
        "name": "추가 능력치",
        "dataId_meaning": "0=어그로, 1=방어효과, 2=회복효과, 3=약리지식, 4=MP소비, 5=TP충전, 6=물리피해, 7=마법피해, 8=지형피해, 9=경험치획득",
        "value_meaning": "배율",
        "example": '"경험치 2배" → {code:23, dataId:9, value:2.0}',
    },
    31: {
        "name": "공격 시 원소 부여",
        "dataId_meaning": "elementId",
        "value_meaning": "0 (고정)",
        "example": '"불 속성 공격" → {code:31, dataId:2, value:0}',
    },
    32: {
        "name": "공격 시 상태 부여",
        "dataId_meaning": "stateId",
        "value_meaning": "확률 (0.0~1.0)",
        "example": '"30% 확률로 독" → {code:32, dataId:<독>, value:0.3}',
    },
    33: {
        "name": "공격 속도 보정",
        "dataId_meaning": "0",
        "value_meaning": "정수 (-/+)",
        "example": '"선공" → {code:33, dataId:0, value:1}',
    },
    34: {
        "name": "공격 횟수 추가",
        "dataId_meaning": "0",
        "value_meaning": "정수 (추가 횟수)",
        "example": '"2회 공격" → {code:34, dataId:0, value:1}',
    },
    35: {
        "name": "공격 스킬",
        "dataId_meaning": "skillId — 평타 대신 사용할 스킬",
        "value_meaning": "0",
        "example": '"평타가 화염볼" → {code:35, dataId:<화염볼 id>, value:0}',
    },
    41: {
        "name": "사용 가능 스킬 타입 추가",
        "dataId_meaning": "stypeId",
        "value_meaning": "0",
        "example": "—",
    },
    42: {
        "name": "사용 가능 스킬 타입 봉인",
        "dataId_meaning": "stypeId",
        "value_meaning": "0",
        "example": "—",
    },
    43: {
        "name": "사용 가능 스킬 추가",
        "dataId_meaning": "skillId",
        "value_meaning": "0",
        "example": '"기본 스킬로 치유 보유" → {code:43, dataId:<치유 id>, value:0}',
    },
    44: {
        "name": "사용 가능 스킬 봉인",
        "dataId_meaning": "skillId",
        "value_meaning": "0",
        "example": "—",
    },
    51: {
        "name": "장착 가능 무기 타입",
        "dataId_meaning": "wtypeId",
        "value_meaning": "0",
        "example": "—",
    },
    52: {
        "name": "장착 가능 방어구 타입",
        "dataId_meaning": "atypeId",
        "value_meaning": "0",
        "example": "—",
    },
    53: {"name": "장착 고정", "dataId_meaning": "etypeId", "value_meaning": "0", "example": "—"},
    54: {"name": "장착 봉인", "dataId_meaning": "etypeId", "value_meaning": "0", "example": "—"},
    55: {"name": "이도류 (양손 무기)", "dataId_meaning": "0", "value_meaning": "0", "example": "—"},
    61: {
        "name": "행동 횟수 추가",
        "dataId_meaning": "0",
        "value_meaning": "확률 (0.0~1.0)",
        "example": "—",
    },
    62: {
        "name": "특수 플래그",
        "dataId_meaning": "0=자동 전투, 1=방어, 2=엄호, 3=TP 유지",
        "value_meaning": "0",
        "example": "—",
    },
    63: {
        "name": "소멸 효과",
        "dataId_meaning": "0=소멸 없음, 1=즉시 소멸, 2=목소리만",
        "value_meaning": "0",
        "example": "—",
    },
    64: {
        "name": "파티 능력",
        "dataId_meaning": "0=인카운트 절반, 1=무인카운트, 2=선제공격, 3=선제기습 무효, 4=골드 2배, 5=드롭 2배",
        "value_meaning": "0",
        "example": "—",
    },
}

# ──────────────────────────────────────────────
# Effect 코드 상세 (프롬프트 빌더용)
# ──────────────────────────────────────────────

# 사용: utils/traits_reference.py
EFFECT_CODES: dict[int, dict[str, Any]] = {
    11: {
        "name": "HP 회복",
        "dataId_meaning": "0",
        "value1_meaning": "% 회복 (0.0~1.0, 0.5 = 최대 HP 의 50%)",
        "value2_meaning": "고정 회복량 (정수)",
        "example": '"HP 50% 회복" → {code:11, dataId:0, value1:0.5, value2:0}',
    },
    12: {
        "name": "MP 회복",
        "dataId_meaning": "0",
        "value1_meaning": "% 회복",
        "value2_meaning": "고정 회복량",
        "example": '"MP 30 회복" → {code:12, dataId:0, value1:0, value2:30}',
    },
    13: {
        "name": "TP 회복",
        "dataId_meaning": "0",
        "value1_meaning": "고정 회복량",
        "value2_meaning": "0",
        "example": '"TP 10 회복" → {code:13, dataId:0, value1:10, value2:0}',
    },
    21: {
        "name": "상태 부여",
        "dataId_meaning": "stateId",
        "value1_meaning": "성공 확률 (0.0~1.0)",
        "value2_meaning": "0",
        "example": '"독 부여" → {code:21, dataId:<독>, value1:0.8, value2:0}',
    },
    22: {
        "name": "상태 해제",
        "dataId_meaning": "stateId",
        "value1_meaning": "성공 확률 (0.0~1.0)",
        "value2_meaning": "0",
        "example": '"독 해제" → {code:22, dataId:<독>, value1:1.0, value2:0}',
    },
    31: {
        "name": "강화 (능력치 ↑)",
        "dataId_meaning": "paramId 0~7",
        "value1_meaning": "지속 턴 (정수)",
        "value2_meaning": "0",
        "example": '"공격력 5턴 강화" → {code:31, dataId:2, value1:5, value2:0}',
    },
    32: {
        "name": "약화 (능력치 ↓)",
        "dataId_meaning": "paramId 0~7",
        "value1_meaning": "지속 턴",
        "value2_meaning": "0",
        "example": "—",
    },
    33: {
        "name": "강화 해제",
        "dataId_meaning": "paramId 0~7",
        "value1_meaning": "0",
        "value2_meaning": "0",
        "example": "—",
    },
    34: {
        "name": "약화 해제",
        "dataId_meaning": "paramId 0~7",
        "value1_meaning": "0",
        "value2_meaning": "0",
        "example": "—",
    },
    41: {
        "name": "특수 효과",
        "dataId_meaning": "0",
        "value1_meaning": "0=탈출, 1=생환",
        "value2_meaning": "0",
        "example": "—",
    },
    42: {
        "name": "능력치 성장",
        "dataId_meaning": "paramId 0~7",
        "value1_meaning": "성장량",
        "value2_meaning": "0",
        "example": "—",
    },
    43: {
        "name": "스킬 습득",
        "dataId_meaning": "skillId",
        "value1_meaning": "1 (고정)",
        "value2_meaning": "0",
        "example": "—",
    },
    44: {
        "name": "공통 이벤트 호출",
        "dataId_meaning": "commonEventId",
        "value1_meaning": "1 (고정)",
        "value2_meaning": "0",
        "example": "—",
    },
}

# ──────────────────────────────────────────────
# Effect 검증 규칙 (스키마 검증용)
# ──────────────────────────────────────────────

# 사용: schemas/effects.py
STATE_MAX_ID: int = 9999

# 사용: schemas/effects.py
EFFECT_RULES: dict[int, dict[str, Any]] = {
    11: {
        "name": "HP 회복",
        "dataId": {"type": "range", "min": 0},
        "value1": {"type": "range", "min": 0, "max": 10},
        "value2": {"type": "range", "min": 0},
    },
    12: {
        "name": "MP 회복",
        "dataId": {"type": "range", "min": 0},
        "value1": {"type": "range", "min": 0, "max": 10},
        "value2": {"type": "range", "min": 0},
    },
    13: {
        "name": "TP 회복",
        "dataId": {"type": "range", "min": 0},
        "value1": {"type": "range", "min": 0, "max": 99},
        "value2": {"type": "range", "min": 0},
    },
    21: {
        "name": "상태 추가",
        "dataId": {"type": "range", "min": 0},
        "value1": {"type": "range", "min": 0, "max": 10},
        "value2": {"type": "range", "min": 0},
    },
    22: {
        "name": "상태 해제",
        "dataId": {"type": "range", "min": 0},
        "value1": {"type": "range", "min": 0, "max": 10},
        "value2": {"type": "range", "min": 0},
    },
    31: {
        "name": "강화",
        "dataId": {"type": "range", "min": 0, "max": 7},
        "value1": {"type": "range", "min": 1, "max": 1000},
        "value2": {"type": "exact", "value": 0},
    },
    32: {
        "name": "약화",
        "dataId": {"type": "range", "min": 0, "max": 7},
        "value1": {"type": "range", "min": 1, "max": 1000},
        "value2": {"type": "exact", "value": 0},
    },
    33: {
        "name": "강화 해제",
        "dataId": {"type": "range", "min": 0, "max": 7},
        "value1": {"type": "range", "min": 0, "max": 10},
        "value2": {"type": "exact", "value": 0},
    },
    34: {
        "name": "약화 해제",
        "dataId": {"type": "range", "min": 0, "max": 7},
        "value1": {"type": "range", "min": 0, "max": 10},
        "value2": {"type": "exact", "value": 0},
    },
    41: {
        "name": "특수 효과",
        "dataId": {"type": "exact", "value": 0},
        "value1": {"type": "range", "min": 0, "max": 1},
        "value2": {"type": "exact", "value": 0},
    },
    42: {
        "name": "성장",
        "dataId": {"type": "range", "min": 0, "max": 7},
        "value1": {"type": "range", "min": 0},
        "value2": {"type": "exact", "value": 0},
    },
    43: {
        "name": "스킬 습득",
        "dataId": {"type": "range", "min": 1},
        "value1": {"type": "exact", "value": 1},
        "value2": {"type": "exact", "value": 0},
    },
    44: {
        "name": "공통 이벤트",
        "dataId": {"type": "range", "min": 1},
        "value1": {"type": "exact", "value": 1},
        "value2": {"type": "exact", "value": 0},
    },
}

# ──────────────────────────────────────────────
# 엔티티 기본 템플릿 + 스킬 프리셋
# ──────────────────────────────────────────────

# 사용: tools/entity_templates.py, tools/rpgmaker_crud.py
DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "Actors.json": {
        "id": 0,
        "name": "",
        "nickname": "",
        "classId": 1,
        "initialLevel": 1,
        "maxLevel": 99,
        "profile": "",
        "note": "",
        "faceName": "",
        "faceIndex": 0,
        "characterName": "",
        "characterIndex": 0,
        "battlerName": "",
        "equips": [0, 0, 0, 0, 0],
        "traits": [],
    },
    "Skills.json": {
        "id": 0,
        "name": "",
        "iconIndex": 0,
        "description": "",
        "note": "",
        "stypeId": 1,
        "mpCost": 10,
        "tpCost": 0,
        "scope": 1,
        "occasion": 1,
        "speed": 0,
        "successRate": 100,
        "repeats": 1,
        "tpGain": 0,
        "hitType": 1,
        "animationId": -1,
        "message1": "",
        "message2": "",
        "messageType": 0,
        "requiredWtypeId1": 0,
        "requiredWtypeId2": 0,
        "damage": {"type": 0, "elementId": -1, "formula": "0", "critical": False, "variance": 20},
        "effects": [],
    },
    "Items.json": {
        "id": 0,
        "name": "",
        "iconIndex": 0,
        "description": "",
        "note": "",
        "itypeId": 1,
        "price": 100,
        "consumable": True,
        "scope": 7,
        "occasion": 3,
        "speed": 0,
        "successRate": 100,
        "repeats": 1,
        "tpGain": 0,
        "hitType": 0,
        "animationId": 0,
        "damage": {"type": 0, "elementId": 0, "formula": "0", "critical": False, "variance": 20},
        "effects": [],
    },
    "Weapons.json": {
        "id": 0,
        "name": "",
        "iconIndex": 0,
        "description": "",
        "note": "",
        "wtypeId": 1,
        "etypeId": 1,
        "price": 100,
        "animationId": 6,
        "params": [0, 0, 0, 0, 0, 0, 0, 0],
        "traits": [],
    },
    "Armors.json": {
        "id": 0,
        "name": "",
        "iconIndex": 0,
        "description": "",
        "note": "",
        "atypeId": 1,
        "etypeId": 2,
        "price": 100,
        "params": [0, 0, 0, 0, 0, 0, 0, 0],
        "traits": [],
    },
    "Enemies.json": {
        "id": 0,
        "name": "",
        "note": "",
        "battlerName": "",
        "battlerHue": 0,
        "params": [100, 0, 10, 10, 10, 10, 10, 10],
        "exp": 10,
        "gold": 5,
        "actions": [
            {
                "conditionParam1": 0,
                "conditionParam2": 0,
                "conditionType": 0,
                "rating": 5,
                "skillId": 1,
            }
        ],
        "dropItems": [
            {"dataId": 1, "denominator": 1, "kind": 0},
            {"dataId": 1, "denominator": 1, "kind": 0},
            {"dataId": 1, "denominator": 1, "kind": 0},
        ],
        "traits": [],
    },
    "States.json": {
        "id": 0,
        "name": "",
        "iconIndex": 0,
        "note": "",
        "restriction": 0,
        "priority": 50,
        "removeAtBattleEnd": False,
        "removeByRestriction": False,
        "autoRemovalTiming": 0,
        "minTurns": 1,
        "maxTurns": 1,
        "removeByDamage": False,
        "chanceByDamage": 100,
        "removeByWalking": False,
        "stepsToRemove": 100,
        "motion": 0,
        "overlay": 0,
        "message1": "",
        "message2": "",
        "message3": "",
        "message4": "",
        "messageType": 0,
        "traits": [],
    },
    "Classes.json": {
        "id": 0,
        "name": "",
        "note": "",
        "expParams": [30, 20, 30, 30],
        "traits": [],
        "learnings": [],
    },
}

# 사용: tools/entity_templates.py, tools/rpgmaker_crud.py
SKILL_PRESETS: dict[str, dict[str, Any]] = {
    "create_damage": {
        "stypeId": 1,
        "mpCost": 20,
        "scope": 1,
        "occasion": 1,
        "hitType": 1,
        "damage": {
            "type": 1,
            "elementId": -1,
            "formula": "a.atk * 4 - b.def * 2",
            "critical": True,
            "variance": 20,
        },
        "effects": [],
    },
    "create_healing": {
        "stypeId": 1,
        "mpCost": 15,
        "scope": 7,
        "occasion": 3,
        "hitType": 0,
        "damage": {
            "type": 3,
            "elementId": -1,
            "formula": "a.mat * 4",
            "critical": False,
            "variance": 10,
        },
        "effects": [],
    },
    "create_buff": {
        "stypeId": 1,
        "mpCost": 10,
        "scope": 7,
        "occasion": 1,
        "hitType": 0,
        "damage": {"type": 0, "elementId": -1, "formula": "0", "critical": False, "variance": 0},
        "effects": [{"code": 31, "dataId": 2, "value1": 0, "value2": 0}],
    },
    "create_state": {
        "stypeId": 1,
        "mpCost": 15,
        "scope": 1,
        "occasion": 1,
        "hitType": 1,
        "damage": {"type": 0, "elementId": -1, "formula": "0", "critical": False, "variance": 0},
        "effects": [{"code": 21, "dataId": 1, "value1": 1.0, "value2": 0}],
    },
}
