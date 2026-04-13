"""RPG Maker MZ 파일별 기본 엔티티 템플릿 및 스킬 서브타입 preset.

merge 우선순위: caller fields > SKILL_PRESETS[action] (Skills만) > DEFAULT_TEMPLATES[file]
id / name 은 RPGMakerCRUD.create() 에서 채운다.

Classes.json: 100레벨 × 8스탯 배열(params)은 의미있는 기본값을 제공할 수 없어 기본 템플릿에서 제외한다.
caller 가 params 를 제공하지 않으면 build_template() 에서 ValueError.
"""

from __future__ import annotations

import copy
from typing import Any

from agent.constants import DEFAULT_TEMPLATES, SKILL_PRESETS

# ──────────────────────────────────────────────
# DB 배열 파일 기본 템플릿
# id / name 은 create() 에서 채워짐
# ──────────────────────────────────────────────
# DEFAULT_TEMPLATES 는 agent.constants 에서 import

# ──────────────────────────────────────────────
# 스킬 서브타입 preset (4종)
# base 템플릿 위에 overlay 됨. damage 는 통째로 교체, effects 는 base 가 [] 일 때만 적용.
# ──────────────────────────────────────────────
# SKILL_PRESETS 는 agent.constants 에서 import


def build_template(file: str, action: str, fields: dict[str, Any]) -> dict[str, Any]:
    """파일 기본 템플릿 + 스킬 preset + caller fields 를 merge 해서 반환한다.

    merge 우선순위 (낮음 → 높음):
      1. DEFAULT_TEMPLATES[file]
      2. SKILL_PRESETS[action]  (Skills.json 이고 preset 이 있는 경우)
      3. fields  (caller 제공값, None 값은 무시)

    id / name 은 호출측(create)에서 덮어쓴다.

    Classes.json 에 params 없으면 ValueError.
    """
    base: dict[str, Any] = copy.deepcopy(DEFAULT_TEMPLATES.get(file, {}))

    # Skills.json preset overlay
    if file == "Skills.json" and action in SKILL_PRESETS:
        preset = SKILL_PRESETS[action]
        # damage: preset 이 base 를 통째로 교체
        if "damage" in preset:
            base["damage"] = copy.deepcopy(preset["damage"])
        # effects: base 가 빈 리스트일 때만 preset 적용
        if "effects" in preset and base.get("effects") == []:
            base["effects"] = copy.deepcopy(preset["effects"])
        # 나머지 preset 스칼라 필드
        for k, v in preset.items():
            if k not in ("damage", "effects"):
                base[k] = v

    # caller fields 최우선 (None 은 무시)
    for k, v in fields.items():
        if v is not None:
            base[k] = v

    # Classes.json params 필수 확인
    if file == "Classes.json" and "params" not in base:
        raise ValueError(
            "Classes.json create 에는 params(100레벨 × 8스탯 배열)가 필요합니다. "
            "planner 에서 params 를 반드시 제공해야 합니다."
        )

    return base
