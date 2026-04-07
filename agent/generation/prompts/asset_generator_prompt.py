"""에셋 생성 노드용 LLM 프롬프트 빌더.
제공된 metadata.txt의 지식을 기반으로 실존하는 그래픽 에셋을 매핑합니다.
"""

import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_RPG_BASE = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
공통 규칙:
- items 배열의 0번 인덱스는 반드시 null (RPG Maker MZ 필수 규칙)
- ID는 반드시 제공된 id_table의 값 사용
- 게임 테마와 일관된 이름/설명 사용 (한국어 필수)
- 그래픽 파일명은 반드시 제공된 리스트에 있는 '실존하는 파일명'만 사용하세요.
"""

# --- 메타데이터 조각 (토큰 절약을 위해 핵심만 요약) ---
ACTOR_METADATA_SUMMARY = """
## 캐릭터 그래픽 선택 가이드 (characterName & characterIndex)
- **Actor1**: 0(갈색단발남), 1(적갈색단발여), 4(기사남), 5(금발마법여), 7(신관여)
- **Actor2**: 0(온화기사남), 1(기사여), 3(귀족마법여), 5(전투여), 6(궁수남)
- **Actor3**: 0(전사남), 1(도적여), 2(냉철남), 3(신비마법여), 5(활발도적여)
- **Evil**: 0(불량배), 2(냉혹마법여), 3(황금갑옷악당), 6(마왕형), 7(흑막로브)
- **Monster**: 2(늑대인간), 4(여우정령), 6(좀비보스), 7(악마보스)
- **Nature**: 0(개), 1(고양이), 4(수인여), 5(요정), 6(천사여)
- **People1**: 0(소년), 1(소녀), 2(청년), 3(젊은여), 4(콧수염중년), 6(노인)
- **People2**: 0(현자노인), 1(신비여), 5(수녀), 6(탐험가), 7(발명가여)
- **People3**: 0(왕), 1(왕비), 2(왕자), 3(공주), 4(장군), 6(근위대장)
- **People4**: 0(학자), 1(메이드), 4(상인), 5(댄서/해적여), 7(무녀)
- **SF 계열**: SF_Actor1~3, SF_People1 (현대/미래 테마일 때 사용)

※ faceName은 characterName과 동일하게, faceIndex는 characterIndex와 동일하게 설정하세요.
   단, People/Evil/Monster/Nature 등 얼굴 파일이 없는 경우 faceName을 "Actor1"로 대체하고 인덱스는 0~7 중 외형이 어울리는 것을 고르세요.
"""

ENEMY_METADATA_SUMMARY = """
## 적 그래픽 선택 가이드 (battlerName)
- **잡몹 (Weak)**: Goblin, Zombie, Petitdevil, Crow, Crab, SF_Drone, SF_Zombiedog
- **중간 (Normal/Elite)**: Wolfman, Harpy, Treant, Darkelf, Sorcerer, Mimic, SF_Mafia, SF_Securityrobot
- **강적 (Elite/Boss)**: Blackknight, Medusa, Siren, Wraith, Unicorn, SF_Cyborg, SF_Phoenix
- **보스 (Boss)**: Highking, Dragon, Demon, Lich, Evilgod, Goddess, SF_Boss
- **최종 보스 (Final)**: Demon_metamorphosis, God_of_light, SF_Demon_of_universe
"""


def build_skills_prompt(spec: dict, id_table: dict) -> list[BaseMessage]:
    system = (
        _RPG_BASE
        + """
## Skills.json 생성 규칙
- stypeId: 1 (마법), 2 (특기)
- scope: 1 (적 단일), 7 (적 전체), 9 (아군 단일), 8 (아군 전체)
- damage.formula 예시: "a.atk * 2 - b.def", "a.mat * 2.5 - b.mdf"
"""
    )
    human = f"게임 테마: {spec['theme']}\n스킬 목록: {json.dumps(id_table.get('skills', {}), ensure_ascii=False)}\n위 목록에 맞춰 SkillsList를 생성하세요."
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_items_prompt(spec: dict, id_table: dict) -> list[BaseMessage]:
    system = _RPG_BASE + "ItemsList를 생성하세요. itypeId 1은 일반, 2는 중요 아이템입니다."
    human = f"아이템 목록: {json.dumps(id_table.get('items', {}), ensure_ascii=False)}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_weapons_prompt(spec: dict, id_table: dict) -> list[BaseMessage]:
    system = _RPG_BASE + "WeaponsList를 생성하세요. wtypeId는 1(검), 3(지팡이) 등입니다."
    human = f"무기 목록: {json.dumps(id_table.get('weapons', {}), ensure_ascii=False)}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_armors_prompt(spec: dict, id_table: dict) -> list[BaseMessage]:
    system = _RPG_BASE + "ArmorsList를 생성하세요. atypeId는 1(방패), 3(갑옷) 등입니다."
    human = f"방어구 목록: {json.dumps(id_table.get('armors', {}), ensure_ascii=False)}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_enemies_prompt(spec: dict, id_table: dict) -> list[BaseMessage]:
    system = (
        _RPG_BASE
        + ENEMY_METADATA_SUMMARY
        + """
## Enemies.json 규칙
- battlerName: 위 가이드에서 적의 티어에 맞는 이름을 반드시 선택하세요.
- params: [HP, MP, ATK, DEF, MAT, MDF, AGI, LUK]
"""
    )
    human = f"적 목록: {json.dumps(spec.get('enemies', []), ensure_ascii=False)}\nID 테이블: {json.dumps(id_table.get('enemies', {}), ensure_ascii=False)}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_classes_prompt(spec: dict, id_table: dict) -> list[BaseMessage]:
    system = _RPG_BASE + "ClassesList를 생성하세요. learnings에 레벨별 습득 스킬을 포함하세요."
    human = f"직업 ID: {json.dumps(id_table.get('classes', {}), ensure_ascii=False)}\n스킬 ID: {json.dumps(id_table.get('skills', {}), ensure_ascii=False)}"
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_actors_prompt(spec: dict, id_table: dict, classes_json: list) -> list[BaseMessage]:
    system = (
        _RPG_BASE
        + ACTOR_METADATA_SUMMARY
        + """
## Actors.json 규칙
- characterName & characterIndex: 캐릭터의 성격과 역할에 가장 잘 어울리는 것을 위 가이드에서 골라 할당하세요.
- faceName & faceIndex: 위 가이드의 '얼굴 파일 예외 규칙'을 반드시 준수하세요.
"""
    )
    human = f"캐릭터 설정: {json.dumps(spec.get('characters', []), ensure_ascii=False)}\nID 테이블: {json.dumps(id_table, ensure_ascii=False)}"
    return [SystemMessage(content=system), HumanMessage(content=human)]
