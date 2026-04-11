"""RPG Maker MZ traits / effects 코드 단일 원천.

profiler 의 프롬프트(코드 → 자연어 참조표)와 validator 의 feedback 생성 양쪽이
이 파일을 import 한다. 코드 지식이 흩어지지 않게 한다.

trait 은 Actors / Classes / Weapons / Armors / Enemies / States 6개 파일이 공유.
effect 는 Skills / Items 2개 파일이 공유.
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────
# Trait codes
# 형식: {code: int, dataId: int, value: int|float}
# code 의 의미와 dataId/value 의 해석을 한 곳에서 관리한다.
# ──────────────────────────────────────────────

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
    53: {
        "name": "장착 고정",
        "dataId_meaning": "etypeId",
        "value_meaning": "0",
        "example": "—",
    },
    54: {
        "name": "장착 봉인",
        "dataId_meaning": "etypeId",
        "value_meaning": "0",
        "example": "—",
    },
    55: {
        "name": "이도류 (양손 무기)",
        "dataId_meaning": "0",
        "value_meaning": "0",
        "example": "—",
    },
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
# Effect codes (Skills / Items)
# 형식: {code: int, dataId: int, value1: int|float, value2: int|float}
# ──────────────────────────────────────────────

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
# Param 인덱스 — 8개 기본 능력치
# ──────────────────────────────────────────────

PARAM_NAMES: list[str] = [
    "MaxHP",
    "MaxMP",
    "ATK",
    "DEF",
    "MAT",
    "MDF",
    "AGI",
    "LUK",
]

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

# 한국어 → paramId 역매핑 (intake/profiler 가 텍스트에서 추출 시 사용)
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
# 프롬프트용 참조표 생성
# profiler 가 시스템 프롬프트에 include 할 텍스트.
# ──────────────────────────────────────────────


def build_traits_reference_text() -> str:
    """profiler 프롬프트에 들어갈 trait 코드 참조표 (간결한 한국어)."""
    lines = ["[Trait 코드표 — 형식: {code, dataId, value}]"]
    for code in sorted(TRAIT_CODES.keys()):
        info = TRAIT_CODES[code]
        lines.append(f"  code={code}: {info['name']}")
        lines.append(f"    dataId = {info['dataId_meaning']}")
        lines.append(f"    value  = {info['value_meaning']}")
        if info["example"] != "—":
            lines.append(f"    예) {info['example']}")
    return "\n".join(lines)


def build_effects_reference_text() -> str:
    """profiler 프롬프트에 들어갈 effect 코드 참조표."""
    lines = ["[Effect 코드표 — 형식: {code, dataId, value1, value2}]"]
    for code in sorted(EFFECT_CODES.keys()):
        info = EFFECT_CODES[code]
        lines.append(f"  code={code}: {info['name']}")
        lines.append(f"    dataId = {info['dataId_meaning']}")
        lines.append(f"    value1 = {info['value1_meaning']}")
        lines.append(f"    value2 = {info['value2_meaning']}")
        if info["example"] != "—":
            lines.append(f"    예) {info['example']}")
    return "\n".join(lines)


def build_params_reference_text() -> str:
    """기본 능력치 인덱스 참조표 (params 배열용)."""
    lines = ["[Params 배열 인덱스 — 8개 기본 능력치]"]
    for idx, name in enumerate(PARAM_NAMES):
        lines.append(f"  [{idx}] {name} ({PARAM_KOREAN[idx]})")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 자연어 해석 — validator 가 결과를 judge 에게 보여줄 때 사용
# ──────────────────────────────────────────────


def describe_trait(trait: dict[str, Any]) -> str:
    """trait dict 를 한국어 한 줄로 해석한다."""
    code = trait.get("code")
    data_id = trait.get("dataId")
    value = trait.get("value")
    info = TRAIT_CODES.get(code) if isinstance(code, int) else None
    if info is None:
        return f"trait(code={code}, dataId={data_id}, value={value})"
    return f"{info['name']}: dataId={data_id}, value={value}"


def describe_effect(effect: dict[str, Any]) -> str:
    """effect dict 를 한국어 한 줄로 해석한다."""
    code = effect.get("code")
    data_id = effect.get("dataId")
    v1 = effect.get("value1")
    v2 = effect.get("value2")
    info = EFFECT_CODES.get(code) if isinstance(code, int) else None
    if info is None:
        return f"effect(code={code}, dataId={data_id}, value1={v1}, value2={v2})"
    return f"{info['name']}: dataId={data_id}, value1={v1}, value2={v2}"


def describe_traits_list(traits: list[dict[str, Any]]) -> list[str]:
    """traits 배열 전체를 한국어 한 줄씩 해석."""
    return [describe_trait(t) for t in traits if isinstance(t, dict)]


def describe_effects_list(effects: list[dict[str, Any]]) -> list[str]:
    """effects 배열 전체를 한국어 한 줄씩 해석."""
    return [describe_effect(e) for e in effects if isinstance(e, dict)]


def describe_params(params: list[int | float]) -> list[str]:
    """params 배열을 능력치 이름과 묶어서 해석."""
    out: list[str] = []
    for idx, val in enumerate(params or []):
        if idx >= len(PARAM_NAMES):
            break
        out.append(f"{PARAM_KOREAN[idx]}={val}")
    return out
