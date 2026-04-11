"""RPG Maker MZ 쓰기 의존성 그래프.

reader 의 _REFERENCE_MAP 이 "읽기 방향 (id → 이름)" 이라면,
여기는 "쓰기 방향 (필드에 값을 넣으려면 먼저 무엇이 존재해야 하는가)" 이다.

사용처:
  - planner/rule_engine.py 가 operation_tuples 를 받아 이 그래프를 walk 해서
    선행 조건(Requirement) 목록을 만든다.

커버리지 원칙:
  - entity JSON 8종 + System.json 에 대해 "참조 ID 를 가진 필드" 전부 기재.
  - Map 관련은 MapInfos 의 메타데이터 작업만 (L1).
  - 여기에 없는 (file, field) 조합은 선행 조건 없이 통과시킨다.

형식:
  키 = (target_file, field[, value_kind])
  값 = Requirement 리스트 (선행 조건, 순서대로 실행)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Requirement:
    """planner 가 체크해야 하는 하나의 선행 조건.

    resolve_key 는 rule_engine 이 이전 requirement 의 결과를 주입할 때
    target_info 에 넣을 키 이름이다.
    """

    # 어느 파일에서 확인?
    file: str
    # 확인 방법
    lookup: Literal[
        "by_name",          # 이름으로 entity 검색 (DB 배열 파일)
        "system_type_list", # System.json 내 배열(armorTypes 등)에서 문자열 검색
        "by_id",            # id 로 entity 확인
        "map_info",         # MapInfos.json 에서 확인
    ]
    # 검색 대상 키 (system_type_list 전용: "armorTypes" / "weaponTypes" / ...)
    system_key: str | None = None
    # 이전 step 결과에서 채워지는 placeholder 이름
    # 예: "{slot_type}" → intake 의 operation tuple 에서 치환
    placeholder: str | None = None
    # 못 찾았을 때 행동
    if_missing: Literal["create_entity", "create_type", "error"] = "error"
    # 찾은 id 를 어떤 이름으로 후속 step 의 target_info 에 넣을 것인가
    resolve_key: str | None = None
    # create 시 필요한 추가 바인딩 (이전 step 결과 참조)
    creation_bindings: dict[str, str] = field(default_factory=dict)


# ──────────────────────────────────────────────
# 의존성 그래프 본체
# ──────────────────────────────────────────────
#
# 키 형식: (target_file, field) 또는 (target_file, field, value_kind)
#   - value_kind 가 있으면 더 구체적 매칭이 먼저 시도됨
#   - 없으면 해당 field 전체에 적용
#
# 값: list[Requirement] — 선행 조건, 리스트 순서가 실행 순서.
#

WriteDependencyKey = tuple[str, ...] # 2-tuple or 3-tuple

WRITE_DEPENDENCIES: dict[WriteDependencyKey, list[Requirement]] = {
    # ================================================================
    # ACTORS
    # ================================================================

    # actor.equips 에 armor 추가 → System.equipTypes + Armors
    ("Actors.json", "equips", "armor"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="equipTypes",
            placeholder="{slot_type}",
            if_missing="create_type",
            resolve_key="etypeId",
        ),
        Requirement(
            file="Armors.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="armor_id",
            creation_bindings={"etypeId": "prev:etypeId"},
        ),
        Requirement(
            file="Actors.json",
            lookup="by_name",
            placeholder="{subject_name}",
            if_missing="error",
            resolve_key="actor_id",
        ),
    ],

    # actor.equips 에 weapon 추가
    ("Actors.json", "equips", "weapon"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="weaponTypes",
            placeholder="{weapon_type}",
            if_missing="create_type",
            resolve_key="wtypeId",
        ),
        Requirement(
            file="Weapons.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="weapon_id",
            creation_bindings={"wtypeId": "prev:wtypeId"},
        ),
        Requirement(
            file="Actors.json",
            lookup="by_name",
            placeholder="{subject_name}",
            if_missing="error",
            resolve_key="actor_id",
        ),
    ],

    # actor.classId → Classes 참조
    ("Actors.json", "classId"): [
        Requirement(
            file="Classes.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="class_id",
        ),
        Requirement(
            file="Actors.json",
            lookup="by_name",
            placeholder="{subject_name}",
            if_missing="error",
            resolve_key="actor_id",
        ),
    ],

    # actor 에게 스킬 부여 → Skills 참조 (trait code 43 으로 직접 부여)
    ("Actors.json", "learnings"): [
        Requirement(
            file="Skills.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="skill_id",
        ),
        Requirement(
            file="Actors.json",
            lookup="by_name",
            placeholder="{subject_name}",
            if_missing="error",
            resolve_key="actor_id",
        ),
    ],

    # actor 전체를 create
    ("Actors.json", None): [
        # actor create 시 classId 기본은 1. 명시적 class 가 있으면 intake 가 별도
        # operation 으로 뽑는다.
    ],

    # ================================================================
    # CLASSES
    # ================================================================

    # class.learnings 에 skill 추가
    ("Classes.json", "learnings"): [
        Requirement(
            file="Skills.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="skill_id",
        ),
        Requirement(
            file="Classes.json",
            lookup="by_name",
            placeholder="{subject_name}",
            if_missing="error",
            resolve_key="class_id",
        ),
    ],

    # ================================================================
    # SKILLS
    # ================================================================

    # skill.stypeId → System.skillTypes
    ("Skills.json", "stypeId"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="skillTypes",
            placeholder="{value_name}",
            if_missing="create_type",
            resolve_key="stypeId",
        ),
    ],

    # skill.damage.elementId → System.elements
    ("Skills.json", "elementId"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="elements",
            placeholder="{value_name}",
            if_missing="error",
            resolve_key="elementId",
        ),
    ],

    # ================================================================
    # WEAPONS
    # ================================================================

    # weapon.wtypeId → System.weaponTypes
    ("Weapons.json", "wtypeId"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="weaponTypes",
            placeholder="{value_name}",
            if_missing="create_type",
            resolve_key="wtypeId",
        ),
    ],

    # weapon.etypeId → System.equipTypes
    ("Weapons.json", "etypeId"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="equipTypes",
            placeholder="{value_name}",
            if_missing="create_type",
            resolve_key="etypeId",
        ),
    ],

    # ================================================================
    # ARMORS
    # ================================================================

    # armor.atypeId → System.armorTypes
    ("Armors.json", "atypeId"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="armorTypes",
            placeholder="{value_name}",
            if_missing="create_type",
            resolve_key="atypeId",
        ),
    ],

    # armor.etypeId → System.equipTypes
    ("Armors.json", "etypeId"): [
        Requirement(
            file="System.json",
            lookup="system_type_list",
            system_key="equipTypes",
            placeholder="{value_name}",
            if_missing="create_type",
            resolve_key="etypeId",
        ),
    ],

    # ================================================================
    # ENEMIES
    # ================================================================

    # enemy.actions[].skillId → Skills
    ("Enemies.json", "actions"): [
        Requirement(
            file="Skills.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="skill_id",
        ),
    ],

    # enemy.dropItems[].dataId → Items
    ("Enemies.json", "dropItems"): [
        Requirement(
            file="Items.json",
            lookup="by_name",
            placeholder="{value_name}",
            if_missing="create_entity",
            resolve_key="item_id",
        ),
    ],

    # ================================================================
    # ITEMS / STATES — 대부분 독립 entity. 특별한 write 의존성 없음.
    # ================================================================

    # ================================================================
    # MAPS (L1 메타데이터)
    # ================================================================

    # Map 생성 시 MapInfos.json 에 엔트리 추가 필요
    ("Map", "create"): [
        Requirement(
            file="MapInfos.json",
            lookup="map_info",
            if_missing="create_entity",
            resolve_key="map_id",
        ),
    ],
}


def lookup_requirements(
    target_file: str,
    field: str | None,
    value_kind: str | None = None,
) -> list[Requirement]:
    """의존성 그래프에서 requirements 를 찾는다.

    매칭 우선순위:
      1. (file, field, value_kind) — 가장 구체적
      2. (file, field) — 필드 수준
      3. (file, None) — 파일 수준 기본값
      4. 빈 리스트 — 의존성 없음

    Returns:
        Requirement 리스트 (원본 복사본). 비면 선행 조건 없음을 의미.
    """
    if value_kind and field:
        key3 = (target_file, field, value_kind)
        if key3 in WRITE_DEPENDENCIES:
            return list(WRITE_DEPENDENCIES[key3])

    if field:
        key2 = (target_file, field)
        if key2 in WRITE_DEPENDENCIES:
            return list(WRITE_DEPENDENCIES[key2])

    # equips fallback — kind 가 armor/weapon 이 아닐 때 armor 경로로
    if field == "equips" and target_file == "Actors.json":
        fallback = (target_file, field, "armor")
        if fallback in WRITE_DEPENDENCIES:
            return list(WRITE_DEPENDENCIES[fallback])

    key1 = (target_file, None)
    if key1 in WRITE_DEPENDENCIES:
        return list(WRITE_DEPENDENCIES[key1])

    return []
