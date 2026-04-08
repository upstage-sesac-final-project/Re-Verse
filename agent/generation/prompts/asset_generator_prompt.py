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
3. scope: 1=적1체, 2=적전체, 7=아군1체, 8=아군전체, 11=자신
4. damage.type: 0=없음, 1=HP대미지, 3=HP회복, 5=HP흡수, 6=MP흡수
5. damage.formula 예시:
   - 물리 공격: "a.atk * 2 - b.def"
   - 마법 공격: "a.mat * 2.5 - b.mdf"
   - 회복: "a.mat * 1.5 + 50"
   - damage.type=0이면 formula="0" (효과는 effects로 구현)
6. stypeId: 1=마법, 2=특수기
7. damage.type=0 스킬은 반드시 effects를 포함해야 합니다 (빈 배열 금지):
   - 적 상태이상: [{"code": 21, "dataId": 상태ID, "value1": 확률(0~1), "value2": 0}]
     상태 dataId: 4=독, 5=실명, 6=침묵, 8=혼란, 10=수면, 12=마비, 13=스턴
   - 아군 버프: [{"code": 31, "dataId": 스탯ID, "value1": 턴수, "value2": 0}]
   - 아군 디버프: [{"code": 32, "dataId": 스탯ID, "value1": 턴수, "value2": 0}]
     스탯 dataId: 2=ATK, 3=DEF, 4=MAT, 5=MDF, 6=AGI, 7=LUK
   - HP/MP 회복 효과: [{"code": 11, "dataId": 0, "value1": 비율, "value2": 고정값}]
8. iconIndex (반드시 1 이상, 0 금지):
   - 물리 공격: 76(단일), 77(강공격), 78(범위/사격)
   - 마법: 64(불), 65(얼음), 66(번개), 67(물), 68(땅), 69(바람), 70(성), 71(암)
   - 회복: 72
   - 버프: 34~38, 디버프: 50~54
   - 상태이상: 2(독), 3(실명), 9(마비)
   - 방어/반사: 81, 도망: 82
9. messageType: message1이 있으면 반드시 1 (0=메시지 미표시)
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
2. battlerName: 반드시 아래 목록의 정확한 이름(대소문자 포함)만 사용 (img/enemies/ 실제 파일명 기준)
   ⚠️ 절대 금지: 목록에 없는 이름을 창작하거나 테마 기반으로 만드는 것
      예) PirateQueen, GhostShip, SeaKing, IceDragon → 이런 이름은 파일이 존재하지 않아 전투 그래픽이 깨짐
      테마와 맞지 않더라도 외형이 비슷한 목록 내 이름을 선택하세요
   외형 선택 팁 (테마별 추천, 정확한 이름만 사용):
     해적·선원   → Captain, Sailor, Mercenary
     마법사·주술사 → Sorcerer, Witch, Lich, Evilbook
     기계·로봇   → Mechascorpion, Machinerybee, SF_Workrobot, SF_Securityrobot, SF_Mechasphere
     해양생물    → Ketos(바다괴물), Kraken(대형문어), Crab(게), Siren(인어), Sandworm
     해골·언데드  → Zombie, Wraith, Lich, SF_Jiangshi(강시)
     새·조류     → Crow, Birdman, Harpy
     식물·균류   → Treant, Matango, Gnome
     곤충·벌레   → Mechascorpion, Machinerybee
     정령·원소   → Undine(물), Salamander(불), Sylph(바람), Gnome(땅), Plasma
     인어·바다요정 → Siren, Ketos, Kraken
     늑대·개과   → Wolfman, SF_Wolf, SF_Whitewolf
     도깨비·오우거 → SF_Blueogre, SF_Redogre, Petitdevil, Demoncount
     ⚠️ "상어", "물고기", "오징어", "해파리" 같은 이름은 파일 없음 → Ketos/Crab/Kraken 사용

   판타지 잡몹: Goblin(초록도깨비), Zombie(좀비), Petitdevil(소악마), Matango(버섯생물),
     Oddegg(알생물), Caitsith(고양이귀소녀), Gnome(버섯모자요정), Crow(까마귀), Crab(게)
   판타지 중간: Wolfman(늑대인간), Tigerbunny(호랑이토끼), Birdman(독수리머리전사),
     Harpy(날개여성), Frilledlizard(도마뱀), Demonpot(항아리악마), Sandworm(모래벌레),
     Sylph(꽃요정), Undine(물정령), Treant(나무괴물), Foxman(여우인간), Darkelf(다크엘프),
     Captain(선장), Mercenary(용병), Sailor(선원), Sorcerer(마법사), Salamander(화염정령),
     Stoneknight(돌기사), Hakutaku(신수), Mimic(보물상자함정), Evilbook(마법책생물),
     Mechascorpion(기계전갈), Machinerybee(기계벌), Plasma(에너지구체)
   판타지 강적: Berserker(흰머리여전사), Blackknight(검은기사), Witch(흰머리마녀),
     Medusa(뱀촉수여신), Siren(인어여성), Wraith(보라로브유령), Demoncount(악마백작),
     Kraken(대형문어), Hydra(다머리용), Ketos(바다괴물), Unicorn(흰유니콘),
     Hi_monster(대형강적), Gatekeeper(문지기)
   판타지 보스: Highking(황금갑옷전사), Dragon(붉은드래곤), Demon(용형악마), Lich(번개언데드),
     Evilgod(촉수여신), Goddess(비행여신), God_of_light(빛의신), Goddess_of_death(낫사신)
   판타지 최종: Demon_metamorphosis(거대변이악마)

   인간형 적: Actor1_3, Actor1_4, Actor1_5, Actor1_6,
     Actor2_1, Actor2_2, Actor2_3, Actor2_4, Actor2_5, Actor2_6, Actor2_7,
     Actor3_1, Actor3_2, Actor3_3, Actor3_4

   SF 잡몹: SF_Agent(요원), SF_Drone(드론), SF_Workrobot(작업로봇),
     SF_Zombiedog(좀비개), SF_Timebomb(시한폭탄로봇)
   SF 중간: SF_Anaconda(아나콘다), SF_Armygorilla(군용고릴라), SF_Armymonkey(군용원숭이),
     SF_Brownbear(갈색곰), SF_Wolf(늑대), SF_Whitewolf(흰늑대), SF_Kamaitachi(낫족제비),
     SF_Kappa(갓파), SF_Will_o_the_wisp(도깨비불), SF_Jiangshi(강시),
     SF_Hannyamask(한냐마스크), SF_Madclown(광대), SF_Mafia(마피아),
     SF_Specialforces(특수부대), SF_Securityrobot(경비로봇), SF_Mechasphere(구체로봇),
     SF_Talkingmuppet(마리오네트), SF_Evilteddybear(악마인형), SF_Shadow(그림자)
   SF 강적: SF_Skullmask(해골마스크), SF_Slaughterrobot(학살로봇), SF_Cyborg(사이보그),
     SF_Blueogre(파란도깨비), SF_Redogre(붉은도깨비), SF_Phoenix(불사조),
     SF_Hermit(은둔마법사), SF_Madscientist(미친과학자)
   SF 보스: SF_Enmadaio(염마대왕), SF_Boss(흰정장마피아두목)
   SF 최종: SF_Demon_of_universe(우주악마)
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

characterName / faceName (동일한 이름 사용 권장):
  판타지: Actor1, Actor2, Actor3, People1, People2, People3, People4, Evil, Monster, Nature
  SF:     SF_Actor1, SF_Actor2, SF_Actor3, SF_People1, SF_Monster

battlerName (img/sv_actors/ 파일명, 확장자 제외):
  Actor1_1~Actor1_8, Actor2_1~Actor2_8, Actor3_5~Actor3_8
  SF_Actor1_1~SF_Actor1_8, SF_Actor2_1~SF_Actor2_8, SF_Actor3_5~SF_Actor3_8
  "" (빈 문자열: SV 전투 미사용)

## characterIndex / faceIndex 상세 가이드 (0~7)

**Actor1** (판타지 주인공급):
  0=갈색단발남(파란눈·결의)   1=적갈색단발여(붉은스카프)
  2=주황스파이크남(묵묵함)    3=적단발여(빨간머리띠·전투)
  4=갈색중단발남(파란기사)    5=금발여(파란모자·마법사)
  6=은발남(차분·학자)         7=초록머리여(안경·신관)

**Actor2** (판타지 기사·전투형):
  0=연파랑단발남(온화한기사)  1=분홍롱헤어여(기사)
  2=연보라단발남(기사장식)    3=보라롱헤어여(귀족·마법사)
  4=초록스파이크남(개성파)    5=갈색금발장발여(근거리전투)
  6=연녹황색남(지식인·궁수)   7=은발여(성숙·궁수)

**Actor3** (판타지 특수·신비형):
  0=검은단발남(전사갑옷)      1=갈색땋은여(궁수·도적)
  2=백은단발남(냉철)          3=흰모자흰머리여(신비마법사)
  4=검은단발남(진지한도적)    5=금발여(활발한도적)
  6=파란갑옷기사남             7=검은롱헤어여(신관)

**SF_Actor1** (SF 학원·청소년):
  0=갈색단발남(흰교복)        1=갈색단발여(흰교복)
  2=빨간스파이크남(파란후드)   3=갈색스파이크여(노란자켓)
  4=검은단발남(짙은정장)      5=보라단발여(핑크베레모·헤드폰)
  6=갈색단발남(교복조끼)      7=파란안경여(베이지교복)

**SF_Actor2** (SF 캐주얼·스포츠):
  0=금발남(초록스웨터)        1=금발여(핑크스웨터)
  2=갈색단발남(파란셔츠)      3=금발여(파란버킷햇)
  4=초록스파이크남(검은티)    5=갈색운동여(파란수트)
  6=금발남(짙은자켓)          7=갈색단발여(흰실험복·의사)

**SF_Actor3** (SF 성인·요원):
  0=검은단발남(흰폴로·근육)   1=황금롱헤어여(노란카디건)
  2=보라롱헤어남(짙은정장)    3=빨간롱헤어여(파란장미·마스크)
  4=회색검은마스크남(닌자)    5=갈색단발소녀(빨간캡)
  6=검은단발남(이어피스·요원)  7=검은롱헤어여(교복·리본)

## 역할별 추천 조합
- 남자 주인공(전사): Actor1/0, Actor2/0, Actor2/2
- 여자 주인공:       Actor1/1, Actor2/1, Actor3/7
- 마법사(남):        Actor1/6, Actor2/6
- 마법사(여):        Actor1/5, Actor2/3
- 도적·닌자:         Actor1/4, Actor3/4, Actor3/5
- 기사:              Actor1/4, Actor2/2, Actor3/6
- 성직자:            Actor1/7, Actor3/7
- SF 주인공:         SF_Actor1/0(남), SF_Actor1/1(여)
- SF 과학자:         SF_Actor2/7
- SF 요원:           SF_Actor3/4, SF_Actor3/6
- 같은 characterName 파일은 characterIndex로 구분 — 한 게임 내 캐릭터마다 다른 index 부여

## 이미지 일관성 규칙 (필수)
세 필드는 반드시 같은 인물을 가리켜야 합니다:
- characterName == faceName (동일 시트)
- characterIndex == faceIndex (동일 index, 동일 인물)
- battlerName == "{faceName}_{faceIndex + 1}" (sv_actors/ 1-based 넘버링)

예시:
  faceName="Actor1", faceIndex=1 → characterName="Actor1", characterIndex=1, battlerName="Actor1_2"
  faceName="SF_Actor2", faceIndex=3 → characterName="SF_Actor2", characterIndex=3, battlerName="SF_Actor2_4"

⚠️ Actor3/SF_Actor3 주의: sv_actors에 5~8번(faceIndex 4~7)만 존재, 1~4번(faceIndex 0~3) 없음.
  faceIndex 0~3인 Actor3/SF_Actor3 캐릭터는 battlerName="" (SV 전투 미사용)으로 설정.
  SV 전투 스프라이트가 필요한 주인공/동료 캐릭터는 Actor3/SF_Actor3 인덱스 0~3을 피하고
  Actor1, Actor2, SF_Actor1, SF_Actor2를 우선 사용하세요.
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
