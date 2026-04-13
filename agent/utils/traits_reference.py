"""RPG Maker MZ traits / effects 코드 단일 원천.

profiler 의 프롬프트(코드 → 자연어 참조표)와 validator 의 feedback 생성 양쪽이
이 파일을 import 한다. 코드 지식이 흩어지지 않게 한다.

trait 은 Actors / Classes / Weapons / Armors / Enemies / States 6개 파일이 공유.
effect 는 Skills / Items 2개 파일이 공유.
"""

from __future__ import annotations

from typing import Any

from agent.constants import (
    EFFECT_CODES,
    PARAM_ALIASES,
    PARAM_KOREAN,
    PARAM_NAMES,
    TRAIT_CODES,
)

# TRAIT_CODES, EFFECT_CODES 는 agent.constants 에서 import


# ──────────────────────────────────────────────
# Param 인덱스 — 8개 기본 능력치
# ──────────────────────────────────────────────



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
