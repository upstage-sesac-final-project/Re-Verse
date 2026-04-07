"""Architect LLM 프롬프트."""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.registry.id_table import IdTable
from agent.generation.schemas.world_spec import WorldSpec

# ── 유효 리소스 파일명 ──

VALID_FACE_FILES = {
    "Actor1": "남성 주인공 스타일 (index 0~7)",
    "Actor2": "여성 주인공 스타일 (index 0~7)",
    "Actor3": "전사/기사 스타일 (index 0~7)",
    "People1": "마을 주민 (index 0~7)",
    "Evil": "악당 얼굴 (index 0~7)",
}

VALID_ENEMY_BATTLERS = [
    "Bat",
    "Bee",
    "Berserker",
    "Captain",
    "Cockatrice",
    "Darklord",
    "Dragon",
    "Gargoyle",
    "Ghost",
    "Goblin",
    "Hornet",
    "Lamia",
    "Minotaur",
    "Orc",
    "Rat",
    "Sahagin",
    "Skeleton",
    "Slime",
    "Snake",
    "Spider",
    "Vampire",
    "Werewolf",
    "Willowisp",
    "Zombie",
]

VALID_SV_ACTORS = {
    "Actor1_1": "남성 검사",
    "Actor1_2": "남성 마법사",
    "Actor1_3": "남성 성직자",
    "Actor2_1": "여성 검사",
    "Actor2_2": "여성 마법사",
    "Actor2_3": "여성 성직자",
}

_SYSTEM = """\
당신은 RPG Maker MZ 게임 설계자(Architect)입니다.
WorldSpec과 IdTable을 받아 GameBlueprint(창작 콘텐츠)를 JSON으로 출력합니다.

## 출력 형식

반드시 순수 JSON 객체만 출력하세요. 설명, 마크다운 코드블록, 추가 텍스트 없이 { } 로 시작하고 끝나는 JSON만 출력합니다.

## 핵심 원칙

1. **반드시 IdTable에서 제공된 ID만 사용하세요** (임의 변경 금지).
2. 창작 콘텐츠(이름, 설명, 스토리, 게임 디자인 의도)에만 집중하세요.
3. MZ 구조적 필드(damage 객체, effects[], hitType 등)는 출력하지 않아도 됩니다 — Builder가 조립합니다.

## 세계관 반영 원칙 (가장 중요!)

WorldSpec의 game_title, theme, story_synopsis를 읽고 **모든 창작 요소를 세계관에 맞게** 작성하세요.

- **스킬 이름**: 배경에 맞게 창작. 예) 해적RPG → "포탄 발사", "갈고리 낚아채기" / 좀비RPG → "헤드샷", "바리케이드" / 사무라이 → "일도양단", "무사의 기합"
- **아이템 이름**: 배경에 맞게 창작. 예) SF → "나노 치료제(소)", "에너지 팩" / 해적 → "럼주(소)", "선의의 약초" / 좀비 → "응급 붕대", "진통제"
- **무기 이름**: 직업과 배경에 맞게 창작. 예) 닌자 → "쿠나이", 사무라이 → "카타나", 저격수 → "저격 소총"
- **방어구 이름**: 배경에 맞게 창작. 예) SF → "전투 수트", "에너지 실드" / 해적 → "선원 코트", "가죽 조끼"
- **적 설명**: 세계관 내 존재감 있는 적으로 묘사

세계관과 어울리지 않는 일반적인 이름(HP포션, 검, 갑옷 등)은 사용하지 마세요.

## 유효 리소스 파일명

### faces/ (face_name)
- Actor1: 남성 주인공 스타일 (face_index 0~7)
- Actor2: 여성 주인공 스타일 (face_index 0~7)
- Actor3: 전사/기사 스타일 (face_index 0~7)
- People1: 마을 주민 (face_index 0~7)
- Evil: 악당 얼굴 (face_index 0~7)

### sv_actors/ (battler_name, character_name)
- Actor1_1: 남성 검사, Actor1_2: 남성 마법사, Actor1_3: 남성 성직자
- Actor2_1: 여성 검사, Actor2_2: 여성 마법사, Actor2_3: 여성 성직자

### enemies/ (battler_name)
유효한 적 이미지: Bat, Bee, Berserker, Captain, Cockatrice, Darklord, Dragon, Gargoyle, Ghost, Goblin,
Hornet, Lamia, Minotaur, Orc, Rat, Sahagin, Skeleton, Slime, Snake, Spider, Vampire, Werewolf, Willowisp, Zombie

## scope/occasion/damage_type 값

- scope: 0=없음, 1=적1명, 2=적전체, 7=아군1명, 8=아군전체, 11=사용자
- occasion: 0=항상, 1=전투중만, 2=메뉴에서만, 3=사용불가
- damage_type: 0=없음, 1=HP데미지, 2=MP데미지, 3=HP회복, 4=MP회복

## 밸런스 가이드라인

### 데미지 공식 참고
- 단일 물리: "a.atk * 2 - b.def"
- 전체 물리: "a.atk * 0.8 - b.def"
- 강력 단일: "a.atk * 3 - b.def * 0.5"
- 마법 단일: "a.mat * 2.5 - b.mdf"
- 마법 전체: "a.mat * 1.2 - b.mdf"
- 단일 회복: "a.mat * 1.5 + 50"
- 전체 회복: "a.mat * 0.8 + 30"

### MP 소비 기준 (일반 마법사 MMP 대비 %)
- 단일 공격: 8%, 전체 공격: 15%, 강력 단일: 20%
- 단일 회복: 10%, 전체 회복: 20%

## 주의사항

- skills 배열에는 id=1(공격), id=2(방어) 기본 스킬을 반드시 포함하세요. 단, 이름은 세계관에 맞게 변경 가능 (예: "베기", "조준사격").
- 각 직업의 고유 스킬은 IdTable에서 제공한 ID를 그대로 사용하되, 이름은 세계관에 맞게 창작하세요.
- actors의 equip_armor_ids는 [shield_id, head_id, body_id, accessory_id] 4개 정수 배열이어야 합니다.
- troops의 각 멤버는 IdTable의 enemies에서 정확한 enemy_id를 사용하세요.
- items 배열에는 IdTable에서 제공된 4개 item ID를 모두 사용하되, 이름은 세계관에 맞게 창작하세요. (HP 회복 2종 + MP 회복 2종 역할 유지)
"""


def build_architect_prompt(
    spec: WorldSpec,
    id_table: IdTable,
    asset_counts: dict,
) -> list[BaseMessage]:
    """Architect LLM 메시지 목록 생성."""
    id_table_str = _format_id_table(id_table)
    # compact JSON으로 토큰 절약
    spec_str = json.dumps(spec.model_dump(), ensure_ascii=False, separators=(",", ":"))
    counts_str = _format_asset_counts(asset_counts, id_table)

    user_content = f"""WorldSpec: {spec_str}

IdTable(이 ID를 반드시 그대로 사용):
{id_table_str}

생성 요건:
{counts_str}

순수 JSON만 출력하세요 (다른 텍스트 없이 {{ 로 시작해서 }} 로 끝냄):"""
    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=user_content),
    ]


def _format_id_table(table: IdTable) -> str:
    lines = []
    for cat in [
        "actors",
        "classes",
        "skills",
        "items",
        "weapons",
        "armors",
        "enemies",
        "troops",
        "maps",
    ]:
        mapping = getattr(table, cat)
        if mapping:
            entries = ", ".join(f'"{k}"={v}' for k, v in mapping.items())
            lines.append(f"{cat}: {{{entries}}}")
    return "\n".join(lines)


def _format_asset_counts(counts: dict, id_table: IdTable) -> str:
    lines = []

    # Skills per class
    skills_per_class = counts.get("skills_per_class", {})
    if skills_per_class:
        lines.append("### Skills")
        lines.append("- id=1: '공격' (기본 공격 스킬, damage_type=1, scope=1, element='물리적')")
        lines.append("- id=2: '방어' (기본 방어 스킬, damage_type=0, scope=11, occasion=1)")
        for cls_name, n_skills in skills_per_class.items():
            cls_skills = {
                k: v for k, v in id_table.skills.items() if k.startswith(f"{cls_name}_skill_")
            }
            for placeholder, sid in cls_skills.items():
                lines.append(f"- id={sid}: {cls_name}의 고유 스킬 (placeholder: {placeholder})")

    # Items
    item_count = counts.get("item_count", 4)
    lines.append(f"\n### Items ({item_count}개)")
    for name, iid in id_table.items.items():
        lines.append(f"- id={iid}: '{name}'")

    # Weapons
    weapon_count = counts.get("weapon_count", 0)
    lines.append(f"\n### Weapons ({weapon_count}개, 직업당 1개)")
    for name, wid in id_table.weapons.items():
        lines.append(f"- id={wid}: '{name}'")

    # Armors
    armor_count = counts.get("armor_count", 0)
    lines.append(f"\n### Armors ({armor_count}개)")
    for name, aid in id_table.armors.items():
        lines.append(f"- id={aid}: '{name}'")

    # Troops
    lines.append("\n### Troops (적 1종당 1그룹)")
    for name, tid in id_table.troops.items():
        lines.append(f"- id={tid}: '{name}'")

    return "\n".join(lines)
