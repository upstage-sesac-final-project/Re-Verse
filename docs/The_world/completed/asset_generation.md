# 에셋 생성 상세 설계

> 관련 노드: B. 설계사, C. 에셋 생성
> 위치: `agent/generation/nodes/asset_planner.py`, `agent/generation/nodes/asset_generator.py`

---

## 개요

에셋 생성은 Full Generation에서 가장 많은 LLM 호출이 발생하는 단계다.

```
B. 설계사 (LLM 없음)
  └─ game_spec 읽기 → ID 테이블 확정 → 생성 순서 결정

C. 에셋 생성 (LLM 5~6회 병렬)
  ├─ generate_classes()
  ├─ generate_actors()
  ├─ generate_skills()
  ├─ generate_items()   ─── 동시 실행
  ├─ generate_weapons()
  ├─ generate_armors()
  └─ generate_enemies() + generate_troops()
```

---

## B. 설계사 (asset_planner.py)

### 하는 일

LLM 호출 없이, `game_spec`만 보고 ID 테이블과 생성 순서를 결정한다.

```python
# agent/generation/nodes/asset_planner.py

def asset_planner(state: GenerationState) -> GenerationState:
    spec = state["game_spec"]

    id_table = _build_id_table(spec)
    switch_table = _build_switch_table(spec)
    generation_order = _decide_order(spec)

    return {
        **state,
        "id_table": id_table,
        "switch_table": switch_table,
        "generation_order": generation_order,
    }
```

### ID 테이블 빌드 로직

RPG Maker MZ는 인덱스 0이 항상 비어 있으므로 실제 ID는 1부터 시작한다.

```python
def _build_id_table(spec: GameSpec) -> IdTable:
    table = IdTable()

    # actors: 캐릭터 이름 순서대로 ID 부여
    for i, char in enumerate(spec.characters, start=1):
        table.actors[char.name] = i

    # classes: 직업 (중복 제거, 순서 유지)
    seen_classes = list(dict.fromkeys(c.class_name for c in spec.characters))
    for i, cls in enumerate(seen_classes, start=1):
        table.classes[cls] = i

    # skills: 각 캐릭터가 가질 스킬 + 공용 스킬 (game_spec에 명시된 경우)
    for i, skill in enumerate(spec.skills or [], start=1):
        table.skills[skill] = i

    # items / weapons / armors
    for i, item in enumerate(spec.key_items or [], start=1):
        table.items[item] = i

    # enemies
    for i, enemy in enumerate(spec.enemies, start=1):
        table.enemies[enemy.name] = i

    # troops: 적 조합 (1종 1 troop 기본)
    for i, enemy in enumerate(spec.enemies, start=1):
        table.troops[f"{enemy.name}_group"] = i

    # maps
    for i, map_spec in enumerate(spec.maps, start=1):
        table.maps[map_spec.name] = i

    return table


def _build_switch_table(spec: GameSpec) -> SwitchTable:
    table = SwitchTable()
    switches = [
        "boss_defeated",
        "game_ending_triggered",
    ]
    # 맵당 핵심 스위치 예약
    for map_spec in spec.maps:
        switches.append(f"{map_spec.name.replace(' ', '_')}_entered")

    for i, name in enumerate(switches, start=1):
        table.switches[name] = i
        table.next_switch_id = i + 1

    return table


def _decide_order(spec: GameSpec) -> list[str]:
    """
    의존성 기반 생성 순서.
    actors는 classes가 먼저 있어야 classId를 쓸 수 있음.
    """
    return [
        "states",                          # 기본 상태 (독립)
        "classes",                         # 직업 (독립)
        "actors", "skills",                # 캐릭터/스킬 (classes 필요)
        "items", "weapons", "armors",      # 아이템류 (독립)
        "enemies", "troops",               # 적 (독립)
        "system",                          # 시스템 (actors, maps 필요)
    ]
```

---

## C. 에셋 생성 (asset_generator.py)

### 병렬 실행 전략

```python
# agent/generation/nodes/asset_generator.py
import asyncio

async def asset_generator(state: GenerationState) -> GenerationState:
    spec      = state["game_spec"]
    id_table  = state["id_table"]
    assets: dict[str, Any] = {}

    # 1단계: 독립 에셋 병렬 생성
    results = await asyncio.gather(
        generate_classes(spec, id_table),
        generate_skills(spec, id_table),
        generate_items(spec, id_table),
        generate_weapons(spec, id_table),
        generate_armors(spec, id_table),
        generate_enemies(spec, id_table),
        return_exceptions=True,
    )

    file_names = ["Classes.json", "Skills.json", "Items.json",
                  "Weapons.json", "Armors.json", "Enemies.json"]
    for fname, result in zip(file_names, results):
        if isinstance(result, Exception):
            raise GenerationError(f"{fname} 생성 실패: {result}")
        assets[fname] = result

    # 2단계: actors는 classes 완료 후 생성
    assets["Actors.json"] = await generate_actors(spec, id_table, assets["Classes.json"])

    # 3단계: troops는 enemies 완료 후 생성
    assets["Troops.json"] = await generate_troops(spec, id_table, assets["Enemies.json"])

    return {**state, "generated_assets": assets}
```

---

## 에셋별 LLM 프롬프트 + Pydantic 스키마

### Actors.json

RPG Maker MZ 캐릭터(배우) 데이터.

**Pydantic 스키마:**

```python
class RpgActor(BaseModel):
    id: int
    name: str
    nickname: str = ""               # 별명 (선택)
    classId: int                     # 직업 ID (id_table에서 확정)
    initialLevel: int = 1
    maxLevel: int = 99
    characterName: str = "Actor1"    # 스프라이트 파일명
    characterIndex: int = 0
    faceName: str = "Actor1"         # 얼굴 이미지 파일명
    faceIndex: int = 0
    equips: list[int] = [0, 0, 0, 0, 0]   # 초기 장비 ID
    # ※ Actor에는 params 없음 — 스탯 성장은 Classes.json에서 관리
    #    (rpgmaker_constraints.md, classes_params_generation.md 참조)
    traits: list[dict] = []
    note: str = ""
    meta: dict = {}
    profile: str = ""

class ActorsJson(BaseModel):
    """Actors.json 전체 구조 (인덱스 0은 null)"""
    __root__: list[RpgActor | None]
```

**LLM 프롬프트:**

```python
def build_actors_prompt(
    spec: GameSpec, id_table: IdTable, classes_json: list
) -> list[BaseMessage]:
    system = """\
당신은 RPG Maker MZ 데이터 생성 전문가입니다.
게임 스펙에 맞는 Actors.json을 생성하세요.

## 필수 규칙
1. 배열 첫 번째 요소(index 0)는 반드시 null이어야 합니다.
2. id는 1부터 순서대로, 제공된 ID를 반드시 사용하세요.
3. classId는 반드시 제공된 ID 테이블 값을 사용하세요.
4. Actor에는 params 필드가 없습니다 (스탯 성장은 Classes.json에서 관리).
   → classes_params_generation.md의 알고리즘이 Class.params를 생성합니다.
5. characterName, faceName은 RPG Maker MZ 기본 리소스명을 사용하세요.
6. equips는 [무기ID, 방패ID, 머리ID, 몸통ID, 장신구ID] 순서입니다.
"""

    human = f"""\
## 캐릭터 목록

{chr(10).join(
    f"- {c.name} / 직업: {c.class_name} / 역할: {c.role} / 성격: {c.personality}"
    f"\n  actor_id: {id_table.actors[c.name]}, classId: {id_table.classes[c.class_name]}"
    for c in spec.characters
)}

## 현재 Classes.json 참조용
{json.dumps(classes_json[:5], ensure_ascii=False)}

Actors.json 배열을 JSON으로 출력하세요 (첫 요소는 null).
"""
    return [SystemMessage(content=system), HumanMessage(content=human)]
```

---

### Skills.json

**Pydantic 스키마:**

```python
class RpgSkillDamage(BaseModel):
    type: int = 1           # 0=없음, 1=HP대미지, 2=MP대미지, 3=HP회복, 4=MP회복
    elementId: int = 0      # 0=일반, 1=불, 2=얼음, 3=번개, ...
    formula: str = "a.atk * 2 - b.def"   # 데미지 공식
    variance: int = 20      # 대미지 분산 (%)
    critical: bool = False

class RpgSkill(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    stypeId: int = 1        # 스킬 타입 (1=마법, 2=특수기)
    scope: int = 1          # 1=적 1체, 2=적 전체, 7=아군 1체, 8=아군 전체
    occasion: int = 1       # 0=항상, 1=전투 중, 2=메뉴
    mpCost: int = 0
    tpCost: int = 0
    damage: RpgSkillDamage = RpgSkillDamage()
    effects: list[dict] = []
    note: str = ""
```

**LLM 프롬프트 핵심 규칙:**

```
스킬 생성 규칙:
1. id는 제공된 값 사용 (임의 변경 금지)
2. mpCost ≤ 캐릭터 최대 MP의 30% (지속 사용 가능해야 함)
3. scope:
   - 단일 공격: scope=1 (적 1체)
   - 전체 공격: scope=2 (적 전체) → damage.formula에서 계수 0.6 이하
   - 회복: scope=7 (아군 1체) 또는 scope=8 (아군 전체)
4. damage.formula 예시:
   - 물리: "a.atk * 2 - b.def"
   - 마법: "a.mat * 2.5 - b.mdf"
   - 회복: "a.mat * 1.5 + 50"
```

---

### Items.json

**Pydantic 스키마:**

```python
class RpgItem(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    itype_id: int = 1       # 아이템 타입 (1=일반, 2=핵심아이템)
    price: int = 100
    consumable: bool = True
    scope: int = 7          # 7=아군 1체
    occasion: int = 0       # 0=항상
    effects: list[dict] = []
    # 회복 아이템 예: effects=[{"code": 11, "dataId": 0, "value1": 0.5, "value2": 0}]
    # code 11 = HP 회복, value1 = 회복률 (0.5 = 최대HP의 50%)
    note: str = ""
```

**회복 아이템 effects 규칙:**

```
회복 포션 (HP 30~50% 회복):
  effects: [{"code": 11, "dataId": 0, "value1": 0.4, "value2": 50}]
  → HP = MaxHP × 0.4 + 50

에테르 (MP 30~50% 회복):
  effects: [{"code": 12, "dataId": 0, "value1": 0.3, "value2": 30}]

만병통치약 (HP+MP 회복):
  effects: [
    {"code": 11, "dataId": 0, "value1": 0.6, "value2": 0},
    {"code": 12, "dataId": 0, "value1": 0.3, "value2": 0}
  ]
```

---

### Weapons.json

**Pydantic 스키마:**

```python
class RpgWeapon(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    wtypeId: int = 1        # 무기 종류 (1=단검, 2=검, 3=도끼, 4=창, 5=도리깨, 6=지팡이)
    price: int = 500
    params: list[int] = [0] * 8   # [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK] 보정값
    traits: list[dict] = []
    animationId: int = 0
    note: str = ""
```

**무기 종류별 스탯 가이드:**

```
검 (wtypeId=2):      ATK+15~25, DEF+2
도끼 (wtypeId=3):    ATK+20~30, AGI-2
창 (wtypeId=4):      ATK+12~20, AGI+3
지팡이 (wtypeId=6):  MAT+15~25, ATK+2

가격 기준:
  초반 무기:  300~800
  중반 무기:  1,000~2,500
  후반 무기:  3,000~8,000
```

---

### Armors.json

```python
class RpgArmor(BaseModel):
    id: int
    name: str
    description: str = ""
    iconIndex: int = 0
    atypeId: int = 1        # 방어구 타입 (1=일반방어구, 2=방패, 3=머리, 4=몸통, 5=장신구)
    price: int = 300
    params: list[int] = [0] * 8   # DEF, MDF 위주
    traits: list[dict] = []
    note: str = ""
```

---

### Enemies.json

**Pydantic 스키마:**

```python
class RpgEnemyAction(BaseModel):
    conditionParam1: int = 0
    conditionParam2: int = 0
    conditionType: int = 0    # 0=항상, 1=턴수, 2=HP%, 4=파티HP%
    rating: int = 5           # 행동 우선도
    skillId: int = 1          # 사용 스킬 ID (1=공격)

class RpgEnemy(BaseModel):
    id: int
    name: str
    battlerName: str = "Slime"    # 배틀러 그래픽 파일명
    battlerHue: int = 0
    params: list[int]             # [MHP, MMP, ATK, DEF, MAT, MDF, AGI, LUK] (8개, 고정)
    exp: int = 50
    gold: int = 20
    dropItems: list[dict] = []
    actions: list[RpgEnemyAction] = [RpgEnemyAction()]
    traits: list[dict] = []
    note: str = ""
```

**티어별 스탯 공식 (LLM 프롬프트에 포함):**

```
플레이어 기준: HP=150, ATK=15, DEF=5

weak (잡몹):
  HP  = 60~90       (플레이어 HP × 0.4~0.6)
  ATK = 8~12        (플레이어 ATK × 0.5~0.8)
  EXP = 20~50
  GOLD = 10~30

normal (일반):
  HP  = 120~200
  ATK = 12~18
  EXP = 50~100

elite (강적):
  HP  = 300~500
  ATK = 20~28
  EXP = 200~400

boss (보스):
  HP  = 2000~4000
  ATK = 30~45
  EXP = 1000~3000

드롭 아이템:
  dropItems: [{"kind": 1, "dataId": 1, "denominator": 4}]
  → kind=1(아이템), dataId=아이템ID, denominator=드롭확률(1/N)
```

---

### Troops.json

적 조합(부대) 데이터. 전투 화면에서 나타나는 적 배치.

```python
class RpgTroopMember(BaseModel):
    enemyId: int
    x: int          # 전투 화면 X 좌표 (0~816)
    y: int          # 전투 화면 Y 좌표 (0~624)
    hidden: bool = False

class RpgTroop(BaseModel):
    id: int
    name: str
    members: list[RpgTroopMember]
    pages: list[dict] = [{"conditions": {}, "list": [], "span": 0}]
```

**적 배치 좌표 가이드:**

```
전투 화면 크기: 816×624

적 1마리:  x=400, y=280 (중앙)
적 2마리:  [x=250, y=280], [x=550, y=280]
적 3마리:  [x=150, y=280], [x=400, y=280], [x=650, y=280]
보스 1마리: x=400, y=200 (크고 위쪽에)
```

**Troops 생성 전략:**

```python
async def generate_troops(
    spec: GameSpec, id_table: IdTable, enemies_json: list
) -> list:
    """각 enemy마다 1개의 troop을 자동 생성 (LLM 없음)"""
    troops = [None]   # 인덱스 0 = null

    for enemy in spec.enemies:
        enemy_id = id_table.enemies[enemy.name]
        troop_id = id_table.troops[f"{enemy.name}_group"]

        # 약한 적은 2~3마리, 보스는 1마리
        if enemy.tier == "boss":
            members = [RpgTroopMember(enemyId=enemy_id, x=400, y=200)]
        elif enemy.tier == "weak":
            count = random.randint(2, 3)
            members = _spread_members(enemy_id, count)
        else:
            members = [RpgTroopMember(enemyId=enemy_id, x=400, y=280)]

        troops.append(RpgTroop(
            id=troop_id,
            name=f"{enemy.name}_group",
            members=members,
        ).model_dump())

    return troops


def _spread_members(enemy_id: int, count: int) -> list[RpgTroopMember]:
    positions = [
        (150, 280), (400, 280), (650, 280),
        (250, 180), (550, 180),
    ]
    return [
        RpgTroopMember(enemyId=enemy_id, x=positions[i][0], y=positions[i][1])
        for i in range(count)
    ]
```

---

### System.json

게임 시스템 설정. 에셋이 모두 생성된 후 통합기(H)에서 조립.

```python
def build_system_json(
    spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
) -> dict:
    return {
        "gameTitle": spec.title,
        "startMapId": id_table.maps[spec.maps[0].name],   # 첫 번째 맵이 시작 맵
        "startX": 8,
        "startY": 6,
        "partyMembers": [
            id_table.actors[c.name]
            for c in spec.characters
            if c.role == "주인공"
        ][:4],  # 최대 4명
        "switches": [""] + list(switch_table.switches.keys()),
        "variables": [""] + list(switch_table.variables.keys()),
        "locale": "ko_KR",
        "currency_unit": "골드",
        "battleSystem": 0,          # 0=턴제
        "optDisplayTp": True,
        "optExtraExp": False,
    }
```

---

## 오류 처리 전략

### LLM 파싱 실패 (에셋별 재시도)

```python
async def generate_with_retry(
    generator_fn: Callable,
    schema: type[BaseModel],
    *args,
    max_retries: int = 3,
) -> list:
    for attempt in range(max_retries):
        try:
            raw = await invoke_llm(generator_fn(*args))
            data = json.loads(raw)
            # Pydantic 검증
            validated = [schema.model_validate(item) if item else None for item in data]
            return [v.model_dump() if v else None for v in validated]
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(
                "%s 파싱 실패 attempt=%d/%d: %s",
                schema.__name__, attempt + 1, max_retries, e
            )
            if attempt == max_retries - 1:
                raise GenerationError(f"{schema.__name__} 생성 {max_retries}회 실패")
```

### `return_exceptions=True` 처리

```python
results = await asyncio.gather(
    generate_classes(spec, id_table),
    generate_skills(spec, id_table),
    # ...
    return_exceptions=True,
)

for fname, result in zip(file_names, results):
    if isinstance(result, Exception):
        # 개별 에셋 실패 → 해당 에셋만 재시도 (전체 재시작 아님)
        logger.error("%s 생성 실패, 재시도: %s", fname, result)
        result = await retry_single_asset(fname, spec, id_table)
    assets[fname] = result
```

---

## 생성 품질 체크리스트

에셋 생성 완료 후 검증기(I)가 확인하는 항목.

```
Actors.json
  □ 각 actor의 id가 id_table과 일치
  □ classId가 Classes.json에 존재
  □ characterName/faceName이 유효한 RPG Maker 리소스명
  □ equips 길이 = 5

Skills.json
  □ mpCost ≤ 최소 MaxMP × 0.3
  □ scope 값이 RPG Maker 허용 범위 (0~13)
  □ damage.formula에 'a.atk', 'a.mat', 'b.def', 'b.mdf' 중 하나 포함

Items.json
  □ effects 배열이 비어있지 않음 (회복 아이템)
  □ price > 0
  □ consumable=true (소모품)

Enemies.json
  □ params 배열 길이 = 8 (고정)
  □ weak 적 ATK ≤ 플레이어 HP × 0.15
  □ boss 적 HP ≥ 1,500

Troops.json
  □ members 배열이 비어있지 않음
  □ 모든 enemyId가 Enemies.json에 존재
  □ x, y 좌표가 전투 화면 범위 내 (0~816, 0~624)
```

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- 리스크 (ID 참조 오류): `docs/The_world/risks_and_mitigations.md#r1`
- 검증기 알고리즘: `docs/The_world/full_generation_plan.md` (검증기 섹션)
- RPG Maker MZ JSON 스키마: `agent/schemas/`
