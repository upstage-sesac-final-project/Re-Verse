"""RPG Maker MZ 파일별 기본 엔티티 템플릿 및 스킬 서브타입 preset.

merge 우선순위: caller fields > SKILL_PRESETS[action] (Skills만) > DEFAULT_TEMPLATES[file]
id / name 은 RPGMakerCRUD.create() 에서 채운다.

Classes.json: 100레벨 × 8스탯 배열(params)은 의미있는 기본값을 제공할 수 없어 기본 템플릿에서 제외한다.
caller 가 params 를 제공하지 않으면 build_template() 에서 ValueError.
"""

from __future__ import annotations

import copy
from typing import Any

# ──────────────────────────────────────────────
# DB 배열 파일 기본 템플릿
# id / name 은 create() 에서 채워짐
# ──────────────────────────────────────────────
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
        "damage": {
            "type": 0,
            "elementId": -1,
            "formula": "0",
            "critical": False,
            "variance": 20,
        },
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
        "damage": {
            "type": 0,
            "elementId": 0,
            "formula": "0",
            "critical": False,
            "variance": 20,
        },
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
    # Classes.json: params 는 100레벨 × 8스탯 배열이라 기본값 없음 → caller 필수 제공
    "Classes.json": {
        "id": 0,
        "name": "",
        "note": "",
        "expParams": [30, 20, 30, 30],
        "traits": [],
        "learnings": [],
        # "params": 미포함 — create() 시 caller 가 반드시 제공해야 함
    },
}

# ──────────────────────────────────────────────
# 스킬 서브타입 preset (4종)
# base 템플릿 위에 overlay 됨. damage 는 통째로 교체, effects 는 base 가 [] 일 때만 적용.
# ──────────────────────────────────────────────
SKILL_PRESETS: dict[str, dict[str, Any]] = {
    "create_damage": {
        "stypeId": 1,
        "mpCost": 20,
        "scope": 1,  # 적 1명
        "occasion": 1,  # 전투 중
        "hitType": 1,  # 물리 공격
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
        "scope": 7,  # 아군 1명
        "occasion": 3,  # 전투/이동
        "hitType": 0,  # 확실히 명중
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
        "damage": {
            "type": 0,
            "elementId": -1,
            "formula": "0",
            "critical": False,
            "variance": 0,
        },
        "effects": [
            {"code": 31, "dataId": 2, "value1": 0, "value2": 0},  # ATK 버프
        ],
    },
    "create_state": {
        "stypeId": 1,
        "mpCost": 15,
        "scope": 1,
        "occasion": 1,
        "hitType": 1,
        "damage": {
            "type": 0,
            "elementId": -1,
            "formula": "0",
            "critical": False,
            "variance": 0,
        },
        "effects": [
            {"code": 21, "dataId": 1, "value1": 1.0, "value2": 0},  # 상태이상 부여
        ],
    },
}


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
