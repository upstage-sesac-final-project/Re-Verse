"""C 노드 (asset_generator) 프롬프트 빌더.

canonical: docs/The_world/asset_generation.md
canonical: docs/The_world/classes_params_generation.md
"""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec
from agent.generation.registry.id_table import IdTable

# ── Classes ──────────────────────────────────────────────────────────────────

_CLASSES_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 직업 데이터(Classes.json)를 생성합니다.

## 규칙
1. 모든 직업을 누락 없이 생성하세요.
2. id는 제공된 값을 그대로 사용하세요.
3. expParams: [basis, extra, acc_a, acc_b] 형식의 4개 정수
   - 일반: [30, 20, 30, 30]
   - 마법사(성장 느림): [30, 20, 15, 30]
   - 빠른 성장: [30, 20, 40, 30]
4. learnings: 레벨별 스킬 습득. level 1~20 사이, skillId는 제공된 목록에서만.
5. params 배열은 생성하지 않습니다 (알고리즘으로 별도 생성됨).
"""


def build_classes_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    class_lines = []
    for cls_name, cls_id in sorted(id_table.classes.items(), key=lambda x: x[1]):
        char = next((c for c in spec.characters if c.class_name == cls_name), None)
        role = char.role if char else "전사"
        class_lines.append(f"  - id={cls_id}, name={cls_name}, role={role}")

    skill_lines = [
        f"  - id={sid}, name={sname}"
        for sname, sid in sorted(id_table.skills.items(), key=lambda x: x[1])
    ]

    human = f"""## 직업 목록 (모두 생성하세요)
{chr(10).join(class_lines)}

## 사용 가능한 스킬 ID (learnings에 이 ID만 사용)
{chr(10).join(skill_lines) if skill_lines else "  (없음)"}

## 게임 테마
{spec.theme}

위 직업 목록 전체의 Classes 데이터를 JSON으로 생성하세요.
"""
    return [SystemMessage(content=_CLASSES_SYSTEM), HumanMessage(content=human)]


# ── Skills ───────────────────────────────────────────────────────────────────

_SKILLS_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 스킬 데이터(Skills.json)를 생성합니다.

## 규칙
1. id는 제공된 값을 사용하세요.
2. mpCost: 0~30 (지속 사용 가능해야 함)
3. scope: 1=적1체, 2=적전체, 7=아군1체, 8=아군전체
4. damage.type: 0=없음, 1=HP대미지, 3=HP회복
5. damage.formula 예시:
   - 물리 공격: "a.atk * 2 - b.def"
   - 마법 공격: "a.mat * 2.5 - b.mdf"
   - 회복: "a.mat * 1.5 + 50"
6. stypeId: 1=마법, 2=특수기
"""


def build_skills_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    skill_lines = [
        f"  - id={sid}, name={sname}"
        for sname, sid in sorted(id_table.skills.items(), key=lambda x: x[1])
    ]

    human = f"""## 스킬 목록
{chr(10).join(skill_lines) if skill_lines else "  (없음)"}

## 게임 테마 및 캐릭터
{spec.theme}
{", ".join(f"{c.name}({c.class_name})" for c in spec.characters)}

모든 스킬의 Skills 데이터를 JSON으로 생성하세요.
"""
    return [SystemMessage(content=_SKILLS_SYSTEM), HumanMessage(content=human)]


# ── Items ────────────────────────────────────────────────────────────────────

_ITEMS_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 아이템 데이터(Items.json)를 생성합니다.

## 규칙
1. id는 제공된 값을 사용하세요.
2. effects 예시:
   - HP 회복 (50%+50): [{"code": 11, "dataId": 0, "value1": 0.5, "value2": 50}]
   - MP 회복: [{"code": 12, "dataId": 0, "value1": 0.3, "value2": 30}]
3. consumable: 회복 아이템=true, 핵심 아이템=false
4. itype_id: 1=일반, 2=핵심아이템
5. scope: 7=아군 1체 (회복), 0=없음 (핵심아이템)
6. price: 100~2000 사이
"""


def build_items_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    item_lines = [
        f"  - id={iid}, name={iname}"
        for iname, iid in sorted(id_table.items.items(), key=lambda x: x[1])
    ]

    # 회복 아이템 기본 제안 (최소 3개)
    extra = "\n또한 아래 기본 회복 아이템을 추가로 생성하세요 (id는 기존 목록 이후부터):"

    human = f"""## 핵심 아이템 목록
{chr(10).join(item_lines) if item_lines else "  (없음)"}

{extra if not item_lines else ""}

## 게임 테마
{spec.theme}

Items 데이터를 JSON으로 생성하세요. 최소 3개 이상 (회복 아이템 포함).
"""
    return [SystemMessage(content=_ITEMS_SYSTEM), HumanMessage(content=human)]


# ── Weapons ──────────────────────────────────────────────────────────────────

_WEAPONS_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 무기 데이터(Weapons.json)를 생성합니다.

## 규칙
1. id는 제공된 값을 사용하세요.
2. wtypeId: 1=단검, 2=검, 3=도끼, 4=창, 5=도리깨, 6=지팡이
3. params: [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK] 8개 보정값
   - 검: ATK+15~25
   - 지팡이: MAT+15~25
4. price: 초반 300~800, 중반 1000~2500, 후반 3000~8000
"""


def build_weapons_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    weapon_lines = [
        f"  - id={wid}, name={wname}"
        for wname, wid in sorted(id_table.weapons.items(), key=lambda x: x[1])
    ]

    human = f"""## 무기 목록
{chr(10).join(weapon_lines)}

## 캐릭터 및 테마
{spec.theme}
{", ".join(f"{c.name}({c.class_name})" for c in spec.characters)}

Weapons 데이터를 JSON으로 생성하세요.
"""
    return [SystemMessage(content=_WEAPONS_SYSTEM), HumanMessage(content=human)]


# ── Armors ───────────────────────────────────────────────────────────────────

_ARMORS_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 방어구 데이터(Armors.json)를 생성합니다.

## 규칙
1. id는 제공된 값을 사용하세요.
2. atypeId: 1=일반방어구, 2=방패, 3=투구, 4=갑옷, 5=장신구
3. etypeId: 2=방패, 3=머리, 4=몸통, 5=장신구 (슬롯 ID)
4. params: DEF, MDF 위주 보정
5. price: 초반 200~600, 중반 800~2000, 후반 2500~6000
"""


def build_armors_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    armor_lines = [
        f"  - id={aid}, name={aname}"
        for aname, aid in sorted(id_table.armors.items(), key=lambda x: x[1])
    ]

    human = f"""## 방어구 목록
{chr(10).join(armor_lines)}

## 캐릭터 및 테마
{spec.theme}
{", ".join(f"{c.name}({c.class_name})" for c in spec.characters)}

Armors 데이터를 JSON으로 생성하세요.
"""
    return [SystemMessage(content=_ARMORS_SYSTEM), HumanMessage(content=human)]


# ── Enemies ──────────────────────────────────────────────────────────────────

_ENEMIES_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 적 데이터(Enemies.json)를 생성합니다.

## 티어별 스탯 기준 (플레이어 기준 HP=150, ATK=15)
- weak:   HP=60~90,    ATK=8~12,  EXP=20~50,   GOLD=10~30
- normal: HP=120~200,  ATK=12~18, EXP=50~100,  GOLD=30~80
- elite:  HP=300~500,  ATK=20~28, EXP=200~400, GOLD=100~300
- boss:   HP=2000~4000, ATK=30~45, EXP=1000~3000, GOLD=500~2000

## params 순서
[MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK] (8개)

## 규칙
1. id는 제공된 값을 사용하세요.
2. battlerName: 아래 목록에서만 선택 (img/enemies/ 실제 파일명 기준)
   판타지: Goblin, Dragon, Lich, Zombie, Witch, Demon, Harpy, Medusa, Unicorn, Treant,
           Siren, Berserker, Birdman, Blackknight, Captain, Crow, Darkelf, Demoncount,
           Demonpot, Evilbook, Evilgod, Foxman, Gatekeeper, Gnome, Goddess, Hakutaku,
           Highking, Hydra, Ketos, Kraken, Machinerybee, Matango, Mechascorpion,
           Mercenary, Mimic, Petitdevil, Salamander, Sandworm, Sorcerer, Stoneknight,
           Sylph, Tigerbunny, Undine, Wolfman, Wraith
   SF:     SF_Agent, SF_Boss, SF_Cyborg, SF_Drone, SF_Madclown, SF_Phoenix,
           SF_Securityrobot, SF_Shadow, SF_Slaughterrobot, SF_Wolf, SF_Zombiedog
3. actions: 기본 공격만 (skillId=1)
4. dropItems: [{"kind": 1, "dataId": 아이템ID, "denominator": 4}] 형식
"""


def build_enemies_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    enemy_lines = [
        f"  - id={eid}, name={en.name}, tier={en.tier}, location={en.location}"
        for en in spec.enemies
        for eid in [id_table.enemies.get(en.name, 0)]
        if eid > 0
    ]

    item_ref = json.dumps({k: v for k, v in list(id_table.items.items())[:5]}, ensure_ascii=False)

    human = f"""## 적 목록
{chr(10).join(enemy_lines)}

## 아이템 ID 참조 (드롭용)
{item_ref}

Enemies 데이터를 JSON으로 생성하세요.
"""
    return [SystemMessage(content=_ENEMIES_SYSTEM), HumanMessage(content=human)]


# ── Actors ───────────────────────────────────────────────────────────────────

_ACTORS_SYSTEM = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 캐릭터 데이터(Actors.json)를 생성합니다.

## 규칙
1. id, classId는 제공된 값을 반드시 사용하세요.
2. Actor에는 params 필드 없음 — 스탯 성장은 Classes.json에서 관리.
3. equips: [무기ID, 방패ID, 머리ID, 몸통ID, 장신구ID] (0=미착용)
4. initialLevel: 1

## 이미지 파일명 — 반드시 아래 목록에서만 선택

characterName (img/characters/ 파일명, 확장자 제외):
  일반: Actor1, Actor2, Actor3, People1, People2, People3, People4, Evil, Monster
  SF:   SF_Actor1, SF_Actor2, SF_Actor3, SF_People1, SF_People2, SF_People3
characterIndex: 0~7 정수 (같은 파일 내 다른 캐릭터 선택)

faceName (img/faces/ 파일명, 확장자 제외):
  일반: Actor1, Actor2, Actor3, People1, People2, People3, People4, Evil, Monster, Nature
  SF:   SF_Actor1, SF_Actor2, SF_Actor3, SF_Monster, SF_People1
faceIndex: 0~7 정수

battlerName (img/sv_actors/ 파일명, 확장자 제외):
  Actor1_1 ~ Actor1_8, Actor2_1 ~ Actor2_8, Actor3_5 ~ Actor3_8
  SF_Actor1_1 ~ SF_Actor1_8, SF_Actor2_1 ~ SF_Actor2_8, SF_Actor3_5 ~ SF_Actor3_8
  (또는 "" 빈 문자열: SV 전투 미사용)

## 할당 가이드
- 주인공/전사: characterName="Actor1" 또는 "Actor2", faceName도 동일
- 마법사/성직자: characterName="Actor2" 또는 "Actor3"
- 도적/닌자: characterName="Actor1" index 4~7
- SF 배경: SF_ 접두사 계열 사용
- 여러 캐릭터가 같은 파일 공유 가능 (characterIndex로 구분)
"""


def build_actors_prompt(
    spec: GameSpec,
    id_table: IdTable,
    classes_json: list,
) -> list[BaseMessage]:
    char_lines = [
        f"  - id={id_table.actors.get(c.name, 0)}, name={c.name}, "
        f"classId={id_table.classes.get(c.class_name, 0)}, "
        f"role={c.role}, personality={c.personality}"
        for c in spec.characters
    ]

    human = f"""## 캐릭터 목록
{chr(10).join(char_lines)}

## 초기 장비 참조
무기 ID: {json.dumps({k: v for k, v in list(id_table.weapons.items())[:4]}, ensure_ascii=False)}
방어구 ID: {json.dumps({k: v for k, v in list(id_table.armors.items())[:4]}, ensure_ascii=False)}

Actors 데이터를 JSON으로 생성하세요 (배열 첫 요소는 null).
"""
    return [SystemMessage(content=_ACTORS_SYSTEM), HumanMessage(content=human)]
