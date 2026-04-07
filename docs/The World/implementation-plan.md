# The World - RPG 게임 초기 생성 구현 계획서

> 사용자 요청에 따라 RPG Maker MZ 기반 게임을 처음부터 생성하는 기능.
> 기존 수정 파이프라인(`agent/graph/`)에 영향을 주지 않도록 `agent/generation/` 독립 모듈로 개발.
> `game_service`에서 게임 생성 시 LLM을 연결하여 한 번의 요청으로 게임을 생성한다.

---

## 1. 전체 아키텍처

### 1.1 현재 흐름

```
POST /games { name, description }
  → base_game 복사 → 빈 프로젝트 생성

POST /llm/process { project_id, message }
  → router → definition → planner → executor → validator → synthesizer
  → 기존 데이터 수정만 가능
```

### 1.2 신규 흐름

```
POST /games { name, description, prompt }    ← prompt 필드 추가
  → base_game 복사 → 프로젝트 생성
  → prompt가 있으면 The World 파이프라인 실행:

      [1차 LLM: GameDesigner]
        사용자 prompt 한 문장 → WorldSpec 전체 생성
        (부족한 정보는 LLM이 세계관에 맞게 자동 보충)
              ↓
      [AssetPlanner] (LLM 없음)
        WorldSpec → IdTable 확정 (모든 에셋 ID 사전 확정)
              ↓
      [2차 LLM: Architect]
        WorldSpec + IdTable → GameBlueprint (구체적 수치/DSL)
              ↓
      [Builder] (LLM 없음)
        GameBlueprint → RPG Maker MZ JSON 파일 생성
              ↓
      [Validator] (LLM 없음)
        생성된 JSON 검증
              ↓
      응답: WorldSpec 요약 + 생성 결과

  이후 수정은 기존 POST /llm/process 그대로 사용
```

### 1.3 사용자 경험 흐름

```
사용자: "주인공이 genie인 신데렐라 이야기의 게임을 만들어줘"
        ↓
시스템: (GameDesigner + AssetPlanner + Architect + Builder + Validator 실행)
        ↓
응답: "게임을 생성했습니다!
      - 제목: 유리구두의 마법사
      - 세계관: 동화 판타지
      - 스토리: 마법사 Genie가 사악한 계모의 저주를 풀고...
      - 파티: Genie(마법사), 왕자(전사), 요정대모(힐러)
      - 보스: 사악한 계모
      - 맵: 신데렐라의 집, 마법의 숲, 왕궁
      - 난이도: 보통"
```

### 1.4 API 시퀀스

```
[프론트엔드]                     [백엔드]                      [Agent]
    │                               │                            │
    ├─ POST /games ────────────────>│                            │
    │  { name: "신데렐라 RPG",      │ ① 프로젝트 생성             │
    │    prompt: "주인공이 genie인   │ ② base_game 복사            │
    │    신데렐라 이야기 게임" }     │ ③ The World 실행 ──────────>│
    │                               │                            ├─ game_designer
    │                               │                            ├─ asset_planner
    │                               │                            ├─ architect
    │                               │                            ├─ builder
    │                               │                            ├─ validator
    │<── { project_id, game_id,     │<───────────────────────────│
    │      world_summary: "..." }   │                            │
    │                               │                            │
    │  (수정이 필요하면)              │                            │
    │── POST /llm/process ─────────>│  기존 수정 파이프라인        │
    │   { project_id, message }     │                            │
```

---

## 2. 파일 구조

### 2.1 신규 파일

```
agent/generation/                          # 생성 전용 모듈 (기존 agent/graph/ 영향 없음)
├── __init__.py
├── state.py                               # GenerationState
├── workflow.py                            # 생성 전용 StateGraph
├── routing.py                             # 분기 로직
├── registry/
│   ├── __init__.py
│   └── id_table.py                        # IdTable (이름→ID 사전 확정)
├── nodes/
│   ├── __init__.py
│   ├── game_designer.py                   # 1차 LLM: prompt → WorldSpec
│   ├── asset_planner.py                   # ID 확정 (LLM 없음)
│   ├── architect.py                       # 2차 LLM: WorldSpec+IdTable → GameBlueprint
│   ├── builder.py                         # Python: JSON 파일 생성
│   └── generation_validator.py            # 생성 전용 검증
├── prompts/
│   ├── game_designer_prompt.py
│   └── architect_prompt.py
├── schemas/
│   ├── world_spec.py                      # WorldSpec, GameSpec
│   └── game_blueprint.py                  # GameBlueprint (DSL)
└── balance/
    ├── stat_templates.py                  # 직업별 스탯 곡선 템플릿
    ├── enemy_balance.py                   # 적 티어별 스탯 범위
    └── economy.py                         # 아이템 가격, 골드 경제
```

### 2.2 기존 파일 수정

| 파일 | 변경 내용 |
|------|----------|
| `app/backend/schemas/game.py` | `ProjectCreate`에 `prompt: str \| None` 필드 추가 |
| `app/backend/services/game_service.py` | `create_project()`에서 prompt가 있으면 The World 파이프라인 호출 |
| `app/backend/schemas/game.py` | `ProjectResponse`에 `world_summary: str \| None` 필드 추가 |

### 2.3 재사용하는 기존 코드

```
agent/schemas/              ← 전부 재사용 (Actors, Skills, Enemies 등 Pydantic 검증)
agent/core/llm_client.py    ← invoke_llm() 그대로 사용
agent/core/config.py        ← LLM 설정
app/backend/core/security.py ← 인증 미들웨어
app/backend/db/             ← DB 세션
```

---

## 3. State 설계

### 3.1 GenerationState

```python
# agent/generation/state.py

class GenerationState(TypedDict, total=False):
    # ── 입력 ──
    user_prompt: str                    # 사용자 원본 요청 ("주인공이 genie인 신데렐라...")
    game_id: str                        # 대상 게임 ID

    # ── GameDesigner 출력 ──
    world_spec: dict                    # WorldSpec (세계관, 파티, 적, 맵 등)

    # ── AssetPlanner 출력 ──
    id_table: dict                      # IdTable (이름→ID 매핑)

    # ── Architect 출력 ──
    game_blueprint: dict                # GameBlueprint (구체적 수치/DSL)

    # ── Builder 출력 ──
    generated_files: list[str]          # 생성된 JSON 파일 목록
    build_errors: list[str]             # 빌드 중 발생한 오류

    # ── Validator 출력 ──
    validation_results: list
    validation_summary: str
    success: bool
    retry_count: int

    # ── 최종 출력 ──
    world_summary: str                  # 사용자에게 보여줄 생성 결과 요약
```

---

## 4. Schema 설계

### 4.1 WorldSpec (1차 LLM 출력)

```python
# agent/generation/schemas/world_spec.py

class PartyMemberSpec(BaseModel):
    """파티원 한 명."""
    name: str
    role: str                               # "전사", "마법사", "힐러", "궁수", "도적" 등
    class_name: str                         # 직업명
    personality: str = ""                   # 성격 (1문장)
    gender: str = "male"                    # "male" | "female" (이미지 매핑용)


class EnemySpec(BaseModel):
    """적 한 마리."""
    name: str
    tier: Literal["weak", "normal", "elite", "boss"] = "normal"
    location: str = ""                      # 등장 맵 이름


class GameMapInfo(BaseModel):
    """맵 고수준 설명."""
    name: str
    map_type: Literal["town", "dungeon", "boss", "field"] = "field"
    description: str = ""
    connects_to: list[str] = []             # 연결된 맵 이름 목록


class WorldSpec(BaseModel):
    """1차 LLM(GameDesigner)이 사용자 prompt 한 문장으로 생성하는 전체 게임 설계.
    부족한 정보는 LLM이 세계관에 맞게 자동 보충한다."""

    # 세계관
    game_title: str
    theme: str                              # "동화 판타지", "중세 판타지", "SF" 등
    story_synopsis: str                     # 전체 줄거리 (2~3문장)
    tone: str = "standard"                  # "dark", "lighthearted", "standard"

    # 파티
    party: list[PartyMemberSpec]            # 2~4명

    # 적
    enemies: list[EnemySpec]                # weak 3~5 + normal 2~3 + boss 1

    # 맵
    maps: list[GameMapInfo]                 # 3~4개

    # 시스템
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    currency_name: str = "G"
    playtime_minutes: int = 7               # 목표 플레이타임
```

### 4.2 IdTable (에셋 ID 사전 확정)

```python
# agent/generation/registry/id_table.py

class IdTable(BaseModel):
    """모든 에셋의 이름→ID 매핑. LLM 호출 전에 확정된다.
    RPG Maker MZ는 인덱스 0이 null이므로 실제 ID는 1부터 시작."""

    actors:  dict[str, int] = {}
    classes: dict[str, int] = {}
    skills:  dict[str, int] = {}
    items:   dict[str, int] = {}
    weapons: dict[str, int] = {}
    armors:  dict[str, int] = {}
    enemies: dict[str, int] = {}
    troops:  dict[str, int] = {}
    maps:    dict[str, int] = {}

    def get_id(self, category: str, name: str) -> int:
        """이름으로 ID 조회. KeyError면 즉시 예외."""
        return getattr(self, category)[name]
```

### 4.3 GameBlueprint (2차 LLM 출력 — 창작 콘텐츠 전용)

> **핵심 원칙:** Architect(LLM)는 **창작 콘텐츠**(이름, 설명, 스토리, 이미지 선택, 게임 디자인 의도)만 출력한다.
> RPG Maker MZ의 구조적/정적 필드(`damage` 객체, `effects[]`, `hitType`, `battlerHue`, `pages` 등)는 **Builder가 조립**한다.
> 이렇게 하면 LLM이 MZ의 복잡한 중첩 구조를 정확히 생성할 필요가 없어 오류가 크게 줄어든다.

```python
# agent/generation/schemas/game_blueprint.py

class GameBlueprint(BaseModel):
    """2차 LLM(Architect)이 생성하는 창작 콘텐츠.
    Builder가 이것을 읽어 RPG Maker MZ JSON을 확정적으로 조립한다.
    모든 ID는 IdTable에서 받은 값만 사용해야 한다.

    ※ MZ 구조적 필드(damage 객체, effects[], hitType 등)는 여기에 없음 → Builder 담당."""

    system: SystemBlueprint
    classes: list[ClassBlueprint]
    actors: list[ActorBlueprint]
    skills: list[SkillBlueprint]
    items: list[ItemBlueprint]
    weapons: list[WeaponBlueprint]
    armors: list[ArmorBlueprint]
    enemies: list[EnemyBlueprint]
    troops: list[TroopBlueprint]


# ── System ──
# Builder가 추가하는 MZ 정적 필드: sounds, terms, attackMotions, testBattlers, versionId 등

class SystemBlueprint(BaseModel):
    game_title: str
    locale: str = "ko_KR"
    currency_unit: str = "G"
    party_members: list[int]            # actor id 목록
    start_map_id: int = 1
    start_x: int = 8
    start_y: int = 6
    skill_types: list[str]              # ["", "마법", "필살기"]
    weapon_types: list[str]             # ["", "검", "지팡이", ...]
    armor_types: list[str]              # ["", "방어구", ...]
    elements: list[str]                 # ["", "물리적", "불", "얼음", ...]


# ── Class ──
# params(8×100)는 LLM이 생성하지 않는다. Builder가 role 기반 알고리즘으로 생성.
# Builder가 추가하는 MZ 필드: params(8×100), traits

class LearningEntry(BaseModel):
    level: int
    skill_id: int

class ClassBlueprint(BaseModel):
    id: int
    name: str
    role: str                           # "warrior", "mage", "healer", "thief" 등 (params 생성 키)
    exp_params: list[int] = [30, 20, 30, 30]
    learnings: list[LearningEntry] = []
    note: str = ""


# ── Actor ──
# Builder가 추가하는 MZ 필드: traits, profile, nickname, meta

class ActorBlueprint(BaseModel):
    id: int
    name: str
    class_id: int
    initial_level: int = 1
    max_level: int = 99
    equip_weapon_id: int = 0
    equip_armor_ids: list[int] = [0, 0, 0, 0]  # [shield, head, body, accessory]
    face_name: str = "Actor1"
    face_index: int = 0                 # 0~7
    character_name: str = "Actor1"
    character_index: int = 0            # 0~7
    battler_name: str = "Actor1_1"


# ── Skill ──
# Architect는 게임 디자인 의도만 출력. Builder가 MZ의 damage 객체/effects[]/hitType 등을 조립.
# Builder가 조립하는 MZ 필드:
#   damage: { critical: false, elementId, formula, type, variance: 20 }
#   hitType (0=확정, 1=물리, 2=마법)
#   successRate (기본 100)
#   speed, repeats (기본 1), tpGain (기본 0)
#   effects[] (빈 배열 또는 스킬 효과)
#   message1, message2, messageType
#   requiredWtypeId1, requiredWtypeId2

class SkillBlueprint(BaseModel):
    id: int
    name: str
    description: str = ""
    skill_type_id: int = 1              # 1=마법, 2=필살기
    mp_cost: int = 0
    tp_cost: int = 0
    scope: int = 1
    """scope: 0=없음, 1=적1명, 2=적전체, 7=아군1명, 8=아군전체, 9=아군(전사자), 11=사용자"""
    occasion: int = 1
    """occasion: 0=항상, 1=전투중만, 2=메뉴에서만, 3=사용불가"""
    damage_type: int = 1
    """damage_type: 0=없음, 1=HP데미지, 2=MP데미지, 3=HP회복, 4=MP회복"""
    element: str = "물리적"              # 원소 이름 (Builder가 elements 목록에서 elementId로 변환)
    formula: str = "a.atk * 2 - b.def"


# ── Item ──
# Architect는 회복 의도만 출력. Builder가 MZ의 effects[] 배열로 변환.
# Builder가 조립하는 MZ 필드:
#   effects: [{ code: 11, dataId: 0, value1: rate/100, value2: flat }]  (HP회복)
#            [{ code: 12, dataId: 0, value1: rate/100, value2: flat }]  (MP회복)
#   damage: { critical: false, elementId: 0, formula: "0", type: 0, variance: 20 }
#   itypeId: 1 (일반아이템), consumable: true, hitType: 0, successRate: 100

class ItemBlueprint(BaseModel):
    id: int
    name: str
    description: str = ""
    price: int = 0
    scope: int = 7                      # 7=아군1명
    occasion: int = 0                   # 0=항상
    recover_hp_rate: int = 0            # HP 회복 % (0~100) → Builder가 effects[code:11]로 변환
    recover_hp_flat: int = 0
    recover_mp_rate: int = 0            # MP 회복 % → Builder가 effects[code:12]로 변환
    recover_mp_flat: int = 0


# ── Weapon ──
# Architect는 무기 이름/타입/스탯만 출력. Builder가 MZ 필드명으로 변환.
# Builder가 조립하는 MZ 필드:
#   wtypeId (weapon_type 이름 → weapon_types 목록에서 인덱스로 변환)
#   etypeId: 1 (항상 무기)
#   traits: [{ code: 31, dataId: animationId, value: 0 }, { code: 22, dataId: 0, value: 0 }]
#   animationId, meta

class WeaponBlueprint(BaseModel):
    id: int
    name: str
    description: str = ""
    weapon_type: str = "검"             # 무기 유형 이름 (Builder가 wtypeId로 변환)
    price: int = 0
    params: list[int] = [0, 0, 0, 0, 0, 0, 0, 0]  # [mhp, mmp, atk, def, mat, mdf, agi, luk]


# ── Armor ──
# Builder가 조립하는 MZ 필드:
#   atypeId (armor_type 이름 → armor_types 목록에서 인덱스로 변환)
#   etypeId (equip_slot 이름 → 숫자 변환: shield=2, head=3, body=4, accessory=5)
#   traits: [], meta

class ArmorBlueprint(BaseModel):
    id: int
    name: str
    description: str = ""
    armor_type: str = "방어구"          # 방어구 유형 이름 (Builder가 atypeId로 변환)
    equip_slot: str = "body"            # "shield"|"head"|"body"|"accessory" (Builder가 etypeId로 변환)
    price: int = 0
    params: list[int] = [0, 0, 0, 0, 0, 0, 0, 0]


# ── Enemy ──
# Architect는 적의 창작 콘텐츠 + 티어만 출력. Builder가 티어 기반 스탯을 생성.
# Builder가 조립하는 MZ 필드:
#   params: [HP, MP, ATK, DEF, MAT, MDF, AGI, LUK] — ENEMY_STAT_GUIDE[tier]에서 생성
#   battlerHue: 0 (기본값)
#   dropItems: 항상 정확히 3개 (미사용 슬롯은 {kind:0, dataId:0, denominator:1})
#   actions: [{skillId, conditionType:0, conditionParam1:0, conditionParam2:0, rating:5}]
#   traits: [], exp, gold

class EnemyDropSpec(BaseModel):
    """적 드롭 아이템 의도 (Builder가 MZ dropItems[3] 형식으로 변환)."""
    kind: str                           # "item"|"weapon"|"armor" (Builder가 1/2/3으로 변환)
    name: str                           # 드롭할 에셋 이름 (Builder가 IdTable에서 dataId 조회)
    denominator: int = 3                # 확률 분모 (1/N)

class EnemyBlueprint(BaseModel):
    id: int
    name: str
    battler_name: str                   # enemies/ 폴더 파일명 (유효 파일명만)
    tier: str = "normal"                # "weak"|"normal"|"elite"|"boss" → Builder가 스탯 생성
    exp: int = 10
    gold: int = 5
    drop_items: list[EnemyDropSpec] = []  # 최대 3개 (Builder가 항상 3개로 패딩)
    skill_ids: list[int] = [1]          # 사용할 스킬 ID 목록 (Builder가 actions[]로 변환)


# ── Troop ──
# Builder가 조립하는 MZ 필드:
#   members[].hidden: false
#   pages: [{ conditions: {...}, list: [{code:0, ...}], span: 0 }] (빈 이벤트 페이지)

class TroopMember(BaseModel):
    enemy_id: int
    x: int = 400
    y: int = 400

class TroopBlueprint(BaseModel):
    id: int
    name: str
    members: list[TroopMember]
```

### 4.4 창작 콘텐츠 vs 구조적 필드 책임 분리표

> Architect(LLM)가 출력하는 필드와 Builder(Python)가 조립하는 필드를 명확히 구분한다.

| 카테고리 | Architect 출력 (창작/디자인) | Builder 조립 (구조/정적) |
|----------|----------------------------|------------------------|
| **System** | game_title, locale, currency_unit, party_members, start 좌표, skill/weapon/armor_types, elements | sounds, terms, attackMotions, testBattlers, versionId, advanced 등 (base_game 복사) |
| **Class** | name, role, exp_params, learnings, note | **params(8×100)** — `build_params_2d(role)` 알고리즘, traits |
| **Actor** | name, class_id, level 범위, 장비 ID, face/character/battler 이미지 | equips[5] 배열 조립, traits, profile, nickname, meta |
| **Skill** | name, description, mp/tp_cost, scope, occasion, damage_type, element(이름), formula | **damage 객체** `{critical, elementId, formula, type, variance}`, hitType, successRate, speed, repeats, tpGain, effects[], message1/2, requiredWtypeId |
| **Item** | name, description, price, scope, occasion, recover_hp/mp (rate/flat) | **effects[]** `[{code:11, dataId, value1, value2}]`, damage 객체, itypeId:1, consumable:true, hitType:0 |
| **Weapon** | name, description, weapon_type(이름), price, params[8] | **wtypeId** (이름→인덱스), etypeId:1, traits[], animationId, meta |
| **Armor** | name, description, armor_type(이름), equip_slot(이름), price, params[8] | **atypeId** (이름→인덱스), **etypeId** (slot→2~5), traits[], meta |
| **Enemy** | name, battler_name, tier, exp, gold, drop_items(이름), skill_ids | **params[8]** (tier→ENEMY_STAT_GUIDE), battlerHue:0, **dropItems[3]** (항상 3개 패딩), **actions[]** (conditionType/Param 포함) |
| **Troop** | name, members(enemy_id, x, y) | members[].hidden:false, **pages[]** (conditions/list/span) |

---

## 5. 각 노드 상세

### 5.1 GameDesigner (1차 LLM)

**역할:** 사용자 prompt 한 문장 → WorldSpec 전체 생성. 부족한 정보는 세계관에 맞게 자동 보충.

**입력:** `user_prompt` (예: "주인공이 genie인 신데렐라 이야기의 게임을 만들어줘")

**LLM 프롬프트 핵심:**

```python
_SYSTEM = """\
당신은 RPG Maker MZ 게임 기획자입니다.
사용자 요청을 받아 5~10분 플레이타임의 RPG 게임 기획서를 JSON으로 작성하세요.

## 규칙

1. 사용자가 언급하지 않은 부분은 세계관에 맞게 창의적으로 보충하세요.
2. 파티원은 2~4명으로 구성하세요. 최소 1명의 전투형 + 1명의 보조형.
3. 적은 weak 3~5마리, normal 2~3마리, boss 1마리로 구성하세요.
4. 맵은 3~4개 (마을 1 + 필드/던전 1~2 + 보스방 1)로 구성하세요.
5. 각 맵의 connects_to는 반드시 양방향이어야 합니다.
6. game_title은 세계관에 맞는 매력적인 이름으로 지어주세요.

## 직업 역할 매핑 (role → class_name)

사용자가 직업을 명시하지 않으면 캐릭터 설정에 맞게 배정하세요:
- 물리 공격형: warrior, thief, archer
- 마법 공격형: mage
- 회복형: healer
- 범용: default

## 출력 형식

반드시 아래 JSON 스키마를 정확히 따르세요.
{WorldSpec JSON Schema}
"""
```

**동작:**

```python
async def game_designer(state: GenerationState) -> dict:
    prompt = state["user_prompt"]
    messages = build_game_designer_prompt(prompt)
    world_spec = await invoke_llm(messages, structured_output=WorldSpec)

    # 사용자에게 보여줄 요약 생성
    summary = _build_summary(world_spec)

    return {
        "world_spec": world_spec.model_dump(),
        "world_summary": summary,
    }

def _build_summary(spec: WorldSpec) -> str:
    party_str = ", ".join(f"{m.name}({m.class_name})" for m in spec.party)
    enemies_str = ", ".join(e.name for e in spec.enemies if e.tier == "boss")
    maps_str = ", ".join(m.name for m in spec.maps)
    return (
        f"게임을 생성했습니다!\n"
        f"- 제목: {spec.game_title}\n"
        f"- 세계관: {spec.theme}\n"
        f"- 스토리: {spec.story_synopsis}\n"
        f"- 파티: {party_str}\n"
        f"- 보스: {enemies_str}\n"
        f"- 맵: {maps_str}\n"
        f"- 난이도: {spec.difficulty}"
    )
```

### 5.2 AssetPlanner (ID 사전 확정, LLM 없음)

**역할:** WorldSpec → IdTable. **모든** 에셋의 ID를 1부터 순차 확정. 이후 단계에서 이 ID를 강제 사용.

> skills, items, weapons, armors도 WorldSpec의 직업/적 구성에서 **개수를 산정**하여 ID를 미리 부여한다.
> 예: 전사 스킬 3개 + 마법사 스킬 4개 → 기본 스킬(공격=1, 방어=2) + 전사 스킬(3,4,5) + 마법사 스킬(6,7,8,9)

```python
async def asset_planner(state: GenerationState) -> dict:
    spec = WorldSpec(**state["world_spec"])
    id_table, asset_counts = _build_id_table(spec)
    return {
        "id_table": id_table.model_dump(),
        "asset_counts": asset_counts,        # Architect에게 "이만큼 만들어야 함" 전달
    }


# ── 직업별 기본 스킬 개수 (role → 스킬 수) ──
ROLE_SKILL_COUNT = {
    "warrior": 3,   # 예: 강타, 방패치기, 전투함성
    "mage": 4,      # 예: 파이어볼, 아이스볼, 썬더, 마력폭발
    "healer": 3,    # 예: 힐, 그룹힐, 부활
    "thief": 3,     # 예: 독찌르기, 숨기, 급소공격
    "default": 2,   # 예: 특수1, 특수2
}

# ── 기본 아이템/장비 개수 ──
BASE_ITEM_COUNT = 4          # HP포션(소), HP포션, MP포션(소), MP포션
BASE_WEAPON_PER_CLASS = 1    # 직업당 1무기
BASE_ARMOR_SLOTS = 3         # 방패/갑옷/장신구 (클래스 공통)


def _build_id_table(spec: WorldSpec) -> tuple[IdTable, dict]:
    table = IdTable()
    counts = {}

    # ── actors ──
    for i, member in enumerate(spec.party, start=1):
        table.actors[member.name] = i

    # ── classes (중복 제거, 순서 유지) ──
    seen_classes = list(dict.fromkeys(m.class_name for m in spec.party))
    for i, cls in enumerate(seen_classes, start=1):
        table.classes[cls] = i

    # ── skills (개수 기반 ID 사전 부여) ──
    table.skills["공격"] = 1
    table.skills["방어"] = 2
    skill_id = 3
    role_to_class = {m.class_name: m.role for m in spec.party}
    for cls_name in seen_classes:
        role = role_to_class.get(cls_name, "default")
        n_skills = ROLE_SKILL_COUNT.get(role, ROLE_SKILL_COUNT["default"])
        for j in range(n_skills):
            table.skills[f"{cls_name}_skill_{j+1}"] = skill_id
            skill_id += 1
    counts["skills_per_class"] = {
        cls: ROLE_SKILL_COUNT.get(role_to_class.get(cls, "default"), 2)
        for cls in seen_classes
    }

    # ── items (개수 기반 ID 사전 부여) ──
    item_names = ["HP포션(소)", "HP포션", "MP포션(소)", "MP포션"]
    for i, name in enumerate(item_names, start=1):
        table.items[name] = i
    counts["item_count"] = len(item_names)

    # ── weapons (직업당 1개) ──
    for i, cls_name in enumerate(seen_classes, start=1):
        table.weapons[f"{cls_name}_무기"] = i
    counts["weapon_count"] = len(seen_classes)

    # ── armors (공통 방어구 세트) ──
    armor_slots = ["방패", "갑옷", "장신구"]
    for i, slot in enumerate(armor_slots, start=1):
        table.armors[slot] = i
    counts["armor_count"] = len(armor_slots)

    # ── enemies ──
    for i, enemy in enumerate(spec.enemies, start=1):
        table.enemies[enemy.name] = i

    # ── troops: 적 1종당 1그룹 ──
    for i, enemy in enumerate(spec.enemies, start=1):
        table.troops[f"{enemy.name}_group"] = i

    # ── maps ──
    for i, m in enumerate(spec.maps, start=1):
        table.maps[m.name] = i

    return table, counts
```

**핵심 원칙 (R1 대응):**
- **모든 카테고리**의 ID가 이 단계에서 **확정** → 이후 단계에서 새 ID를 만들지 않음
- skills/items/weapons/armors도 WorldSpec의 직업/적 구성에서 개수를 산정하여 ID 부여
- placeholder 이름(예: `마법사_skill_1`)은 Architect가 실제 이름으로 대체, ID는 유지
- Architect 프롬프트에 `"반드시 다음 ID를 사용하세요 (임의 변경 금지)"` 명시

### 5.3 Architect (2차 LLM)

**역할:** WorldSpec + IdTable → GameBlueprint. **창작 콘텐츠만 생성** (이름, 설명, 이미지 매핑, 게임 디자인 의도).
MZ의 구조적 필드(damage 객체, effects[], hitType 등)는 생성하지 않는다 → Builder가 조립.

**LLM에 주입하는 컨텍스트:**

| 항목 | 내용 |
|------|------|
| WorldSpec | 세계관, 파티, 적, 맵, 난이도 |
| IdTable | 확정된 ID (`"아서의 actor_id=1, classId=1"`) |
| 유효 리소스 파일명 | faces/, characters/, sv_actors/, enemies/ 목록 |
| 밸런스 가이드라인 | 적 티어별 스탯 범위, 데미지 공식, MP 소비 기준 |
| RPG Maker MZ 제약 | scope/occasion/damage_type enum 값 |

**유효 리소스 파일명 (프롬프트 직접 주입):**

```python
VALID_FACE_FILES = {
    "Actor1": "남성 주인공 스타일 (index 0~7)",
    "Actor2": "여성 주인공 스타일 (index 0~7)",
    "Actor3": "전사/기사 스타일 (index 0~7)",
    "People1": "마을 주민 (index 0~7)",
    "Evil": "악당 얼굴 (index 0~7)",
}

VALID_ENEMY_BATTLERS = [
    "Bat", "Bee", "Berserker", "Captain", "Cockatrice",
    "Darklord", "Dragon", "Gargoyle", "Ghost", "Goblin",
    "Hornet", "Lamia", "Minotaur", "Orc", "Rat",
    "Sahagin", "Skeleton", "Slime", "Snake", "Spider",
    "Vampire", "Werewolf", "Willowisp", "Zombie",
]

VALID_SV_ACTORS = {
    "Actor1_1": "남성 검사", "Actor1_2": "남성 마법사", "Actor1_3": "남성 성직자",
    "Actor2_1": "여성 검사", "Actor2_2": "여성 마법사", "Actor2_3": "여성 성직자",
}
```

**밸런스 가이드라인:**

```python
# 적 티어별 스탯 범위 (The_world/balance_and_economy.md 기반)
ENEMY_STAT_GUIDE = {
    "weak":   {"hp": (60, 100),   "atk": (8, 13),   "def": (2, 5),   "exp": (25, 55),   "gold": (10, 30)},
    "normal": {"hp": (120, 200),  "atk": (13, 20),  "def": (4, 9),   "exp": (55, 100),  "gold": (25, 60)},
    "elite":  {"hp": (300, 500),  "atk": (20, 30),  "def": (10, 15), "exp": (200, 400), "gold": (80, 200)},
    "boss":   {"hp": (1800, 4000),"atk": (30, 45),  "def": (15, 25), "exp": (1000, 3000),"gold": (500, 1500)},
}

# 데미지 공식 계수 기준
DAMAGE_FORMULA_GUIDE = {
    "single_atk":   "a.atk * 2 - b.def",
    "aoe_atk":      "a.atk * 0.8 - b.def",
    "strong_single":"a.atk * 3 - b.def * 0.5",
    "magic_single": "a.mat * 2.5 - b.mdf",
    "magic_aoe":    "a.mat * 1.2 - b.mdf",
    "heal_single":  "a.mat * 1.5 + 50",
    "heal_aoe":     "a.mat * 0.8 + 30",
}

# MP 소비 기준 (MMP 대비 %)
MP_COST_GUIDE = {
    "single_atk": 8, "aoe_atk": 15, "strong_single": 20,
    "heal_single": 10, "heal_aoe": 20, "buff": 5,
}
```

**아이템 가격 가이드:**

```python
ITEM_PRICE_GUIDE = {
    "회복 포션 (소)": {"price": 80,  "hp_rate": 30, "hp_flat": 20},
    "회복 포션":      {"price": 150, "hp_rate": 50, "hp_flat": 30},
    "회복 포션 (대)": {"price": 300, "hp_rate": 80, "hp_flat": 0},
    "에테르 (소)":    {"price": 60,  "mp_rate": 30},
    "에테르":         {"price": 120, "mp_rate": 50},
}
```

### 5.4 Builder (Python, LLM 없음)

**역할:** GameBlueprint → RPG Maker MZ JSON 파일 **전부 새로 조립**.
base_game의 data 폴더 구조만 참고하고, **내용은 전부 새로 생성**한다.
Architect가 출력한 창작 콘텐츠에 MZ 구조적/정적 필드를 합쳐 완성된 JSON을 만든다.

**생성 대상 파일:**

| 파일 | 소스 | Builder의 역할 |
|------|------|---------------|
| `System.json` | SystemBlueprint + base_game 정적값 | sounds, terms, attackMotions 등은 base_game에서 복사 |
| `Actors.json` | ActorBlueprint[] | equips[5] 조립, traits/profile/nickname/meta 추가 |
| `Classes.json` | ClassBlueprint[] + **알고리즘 params** | **8×100 params** 생성, traits 추가 |
| `Skills.json` | SkillBlueprint[] | **damage 객체** 조립, hitType/successRate/effects[] 등 추가 |
| `Items.json` | ItemBlueprint[] | **effects[] 배열** 조립, damage 객체/itypeId/consumable 추가 |
| `Weapons.json` | WeaponBlueprint[] | weapon_type→**wtypeId** 변환, etypeId:1, traits[] 추가 |
| `Armors.json` | ArmorBlueprint[] | armor_type→**atypeId**, equip_slot→**etypeId** 변환, traits[] 추가 |
| `Enemies.json` | EnemyBlueprint[] | tier→**params[8]** 생성, **dropItems[3]** 패딩, actions[] 조립, battlerHue:0 |
| `Troops.json` | TroopBlueprint[] | members[].hidden 추가, **pages[] 배열** 생성 |
| `States.json` | base_game 그대로 | |
| `Animations.json` | base_game 그대로 | |
| `CommonEvents.json` | base_game 그대로 | |
| `MapInfos.json` | 맵 개수에 따라 생성 | |
| `Map00X.json` | base_game 맵 복사 + 이름 변경 | Phase 1에서는 단순 복사 |

**Builder MZ 필드 조립 상세:**

```python
# ── Skills.json: damage 객체 조립 ──
def build_skill_entry(bp: SkillBlueprint, elements: list[str]) -> dict:
    element_id = elements.index(bp.element) if bp.element in elements else 0
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "stypeId": bp.skill_type_id,
        "mpCost": bp.mp_cost,
        "tpCost": bp.tp_cost,
        "scope": bp.scope,
        "occasion": bp.occasion,
        "animationId": -1,
        "iconIndex": 0,
        # ★ damage는 중첩 객체 — LLM이 아닌 Builder가 조립
        "damage": {
            "critical": False,
            "elementId": element_id,
            "formula": bp.formula,
            "type": bp.damage_type,
            "variance": 20,
        },
        "hitType": 2 if bp.damage_type in (1, 2) else 0,  # 공격=마법적, 회복=확정
        "successRate": 100,
        "speed": 0,
        "repeats": 1,
        "tpGain": 0,
        "effects": [],
        "message1": "",
        "message2": "",
        "messageType": 0,
        "requiredWtypeId1": 0,
        "requiredWtypeId2": 0,
        "note": "",
        "meta": {},
    }


# ── Items.json: effects[] 배열 조립 ──
def build_item_entry(bp: ItemBlueprint) -> dict:
    effects = []
    if bp.recover_hp_rate or bp.recover_hp_flat:
        effects.append({"code": 11, "dataId": 0,
                        "value1": bp.recover_hp_rate / 100, "value2": bp.recover_hp_flat})
    if bp.recover_mp_rate or bp.recover_mp_flat:
        effects.append({"code": 12, "dataId": 0,
                        "value1": bp.recover_mp_rate / 100, "value2": bp.recover_mp_flat})
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "iconIndex": 0,
        "price": bp.price,
        "scope": bp.scope,
        "occasion": bp.occasion,
        "itypeId": 1,            # 1=일반 아이템
        "consumable": True,
        "hitType": 0,
        "successRate": 100,
        "animationId": -1,
        "damage": {"critical": False, "elementId": 0, "formula": "0", "type": 0, "variance": 20},
        "effects": effects,      # ★ recover_hp/mp → effects[] 변환
        "speed": 0, "repeats": 1, "tpGain": 0,
        "note": "", "meta": {},
    }


# ── Weapons.json: wtypeId 변환 ──
def build_weapon_entry(bp: WeaponBlueprint, weapon_types: list[str]) -> dict:
    wtype_id = weapon_types.index(bp.weapon_type) if bp.weapon_type in weapon_types else 1
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "iconIndex": 0,
        "price": bp.price,
        "wtypeId": wtype_id,     # ★ weapon_type 이름 → 인덱스 변환
        "etypeId": 1,            # 항상 1 (무기)
        "params": bp.params,
        "traits": [
            {"code": 31, "dataId": 1, "value": 0},   # 공격 애니메이션
            {"code": 22, "dataId": 0, "value": 0},    # 공격 속성
        ],
        "animationId": 1,
        "note": "", "meta": {},
    }


# ── Armors.json: atypeId, etypeId 변환 ──
EQUIP_SLOT_MAP = {"shield": 2, "head": 3, "body": 4, "accessory": 5}

def build_armor_entry(bp: ArmorBlueprint, armor_types: list[str]) -> dict:
    atype_id = armor_types.index(bp.armor_type) if bp.armor_type in armor_types else 1
    etype_id = EQUIP_SLOT_MAP.get(bp.equip_slot, 4)
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "iconIndex": 0,
        "price": bp.price,
        "atypeId": atype_id,     # ★ armor_type 이름 → 인덱스 변환
        "etypeId": etype_id,     # ★ equip_slot 이름 → 2~5 변환
        "params": bp.params,
        "traits": [],
        "note": "", "meta": {},
    }


# ── Enemies.json: tier→스탯, dropItems 항상 3개 ──
def build_enemy_entry(bp: EnemyBlueprint, id_table: IdTable, difficulty: str) -> dict:
    # tier 기반 스탯 생성
    stat_range = ENEMY_STAT_GUIDE[bp.tier]
    mult = DIFFICULTY_MULTIPLIER[difficulty]
    params = _generate_enemy_params(stat_range, mult)

    # dropItems: 항상 정확히 3개 (미사용 슬롯은 기본값)
    drop_items = []
    KIND_MAP = {"item": 1, "weapon": 2, "armor": 3}
    for i in range(3):
        if i < len(bp.drop_items):
            d = bp.drop_items[i]
            kind = KIND_MAP.get(d.kind, 1)
            data_id = _resolve_drop_id(d, id_table)
            drop_items.append({"kind": kind, "dataId": data_id, "denominator": d.denominator})
        else:
            drop_items.append({"kind": 0, "dataId": 0, "denominator": 1})  # ★ 빈 슬롯

    # actions: skill_ids → MZ actions 형식
    actions = []
    for sid in bp.skill_ids:
        actions.append({
            "skillId": sid,
            "conditionType": 0,
            "conditionParam1": 0,
            "conditionParam2": 0,
            "rating": 5,
        })

    return {
        "id": bp.id,
        "name": bp.name,
        "battlerName": bp.battler_name,
        "battlerHue": 0,         # ★ 항상 0 (기본 색조)
        "params": params,        # ★ tier 기반 알고리즘 생성
        "exp": int(bp.exp * mult.get("exp", 1.0)),
        "gold": int(bp.gold * mult.get("gold", 1.0)),
        "dropItems": drop_items, # ★ 항상 정확히 3개
        "actions": actions,      # ★ conditionType/Param 포함
        "traits": [],
        "note": "", "meta": {},
    }


# ── Troops.json: pages[] 배열 필수 ──
def build_troop_entry(bp: TroopBlueprint) -> dict:
    members = []
    for m in bp.members:
        members.append({
            "enemyId": m.enemy_id,
            "x": m.x,
            "y": m.y,
            "hidden": False,     # ★ hidden 필드 필수
        })
    return {
        "id": bp.id,
        "name": bp.name,
        "members": members,
        "pages": [{              # ★ pages 배열 필수 (최소 1개 빈 이벤트 페이지)
            "conditions": {
                "actorHp": 0, "actorId": 1, "actorValid": False,
                "enemyHp": 0, "enemyIndex": 0, "enemyValid": False,
                "switchId": 1, "switchValid": False, "turnA": 0, "turnB": 0, "turnEnding": False, "turnValid": False,
            },
            "list": [{"code": 0, "indent": 0, "parameters": []}],
            "span": 0,
        }],
    }
```

**Classes.json params 생성 (핵심 알고리즘):**

LLM은 800개 숫자를 정확히 생성할 수 없으므로, `role` 기반 알고리즘이 생성한다.
RPG Maker MZ의 params는 **8×100 배열** (인덱스 0 = 레벨 1, 인덱스 99 = 레벨 99+).

```python
# agent/generation/balance/stat_templates.py
# 출처: The_world/classes_params_generation.md

CLASS_STAT_TEMPLATE: dict[str, dict[str, tuple[int, int]]] = {
    # role → { stat: (lv1값, lv99값) }
    "warrior": {
        "mhp": (180, 2500), "mmp": (60, 800),
        "atk": (18, 280),   "def": (10, 150),
        "mat": (8, 135),    "mdf": (8, 110),
        "agi": (9, 110),    "luk": (8, 80),
    },
    "mage": {
        "mhp": (130, 1600), "mmp": (100, 1400),
        "atk": (10, 140),   "def": (6, 90),
        "mat": (18, 280),   "mdf": (12, 160),
        "agi": (10, 120),   "luk": (9, 90),
    },
    "healer": {
        "mhp": (150, 2000), "mmp": (90, 1200),
        "atk": (10, 150),   "def": (8, 120),
        "mat": (14, 200),   "mdf": (14, 200),
        "agi": (9, 110),    "luk": (10, 100),
    },
    "thief": {
        "mhp": (140, 1800), "mmp": (50, 700),
        "atk": (15, 220),   "def": (7, 110),
        "mat": (8, 100),    "mdf": (8, 100),
        "agi": (18, 280),   "luk": (15, 200),
    },
    "default": {
        "mhp": (150, 2000), "mmp": (70, 1000),
        "atk": (14, 200),   "def": (8, 120),
        "mat": (12, 160),   "mdf": (8, 120),
        "agi": (10, 140),   "luk": (9, 90),
    },
}

STAT_ORDER = ["mhp", "mmp", "atk", "def", "mat", "mdf", "agi", "luk"]


def generate_class_params(stat_lv1: int, stat_lv99: int, growth: str = "linear") -> list[int]:
    """레벨 0~99 스탯 배열 생성 (100개 정수). 인덱스 0은 레벨 1에 해당."""
    import math
    result = []
    for lv in range(100):           # ★ 0~99 = 100개
        t = lv / 99 if lv > 0 else 0
        if growth == "accelerate":
            t = t ** 2
        elif growth == "decelerate":
            t = math.sqrt(t)
        value = int(stat_lv1 + (stat_lv99 - stat_lv1) * t)
        result.append(value)
    return result


def build_params_2d(role: str) -> list[list[int]]:
    """8×100 params 2D 배열 생성."""
    template = CLASS_STAT_TEMPLATE.get(role, CLASS_STAT_TEMPLATE["default"])
    params_2d = []
    for stat in STAT_ORDER:
        lv1, lv99 = template[stat]
        growth = "accelerate" if stat in ("mhp", "mmp") else "linear"
        params_2d.append(generate_class_params(lv1, lv99, growth=growth))
    return params_2d  # [8][100]
```

**EXP 곡선 가이드:**

```python
EXP_PARAMS_GUIDE = {
    "normal": [30, 20, 30, 30],
    "slow":   [30, 20, 15, 30],
    "fast":   [30, 20, 40, 30],
}
```

**난이도 보정:**

```python
DIFFICULTY_MULTIPLIER = {
    "easy":   {"enemy_hp": 0.7, "enemy_atk": 0.7, "exp": 1.5, "gold": 1.5},
    "normal": {"enemy_hp": 1.0, "enemy_atk": 1.0, "exp": 1.0, "gold": 1.0},
    "hard":   {"enemy_hp": 1.5, "enemy_atk": 1.3, "exp": 0.7, "gold": 0.7},
}
```

**JSON 생성 공통 규칙:**

```python
def build_json_array(items: list[dict]) -> list:
    """RPG Maker MZ JSON 배열: 인덱스 0은 null, id == 배열 인덱스."""
    result = [None]
    for item in sorted(items, key=lambda x: x["id"]):
        while len(result) < item["id"]:
            result.append(None)
        result.append(item)
    return result
```

### 5.5 GenerationValidator (검증)

기존 `agent/schemas/`의 Pydantic 모델을 재사용.

| 함수 | 검증 내용 | 리스크 |
|------|----------|--------|
| `check_null_at_index_0()` | JSON 배열 [0] == null | 기본 |
| `check_id_index_match()` | item.id == 배열 인덱스 | 기본 |
| `check_id_references()` | actor.classId → Classes 존재, skill 참조 유효 | R1 |
| `check_equips_valid()` | equips 5개 고정, 참조 ID 유효 | R1 |
| `check_resource_filenames()` | faceName, battlerName 유효 | R19 |
| `check_pydantic_schema()` | agent/schemas/ 모델로 전체 검증 | 기본 |

---

## 6. 워크플로우 그래프

### 6.1 StateGraph 구조

```python
# agent/generation/workflow.py

def build_generation_graph() -> StateGraph:
    builder = StateGraph(GenerationState)

    builder.add_node("game_designer", game_designer)
    builder.add_node("asset_planner", asset_planner)
    builder.add_node("architect", architect)
    builder.add_node("builder", builder_node)
    builder.add_node("validator", generation_validator)

    builder.add_edge(START, "game_designer")
    builder.add_edge("game_designer", "asset_planner")
    builder.add_edge("asset_planner", "architect")
    builder.add_edge("architect", "builder")
    builder.add_edge("builder", "validator")

    builder.add_conditional_edges(
        "validator",
        route_after_validator,
        {"__end__": END, "architect": "architect"},
    )

    return builder.compile()

generation_graph = build_generation_graph()
```

### 6.2 라우팅 로직

```python
# agent/generation/routing.py

def route_after_validator(state: GenerationState) -> str:
    if state.get("success", False):
        return "__end__"
    if state.get("retry_count", 0) < 2:
        return "architect"  # Architect부터 재시도
    return "__end__"        # 최대 재시도 도달
```

---

## 7. 기존 코드 수정

### 7.1 ProjectCreate 스키마 변경

```python
# app/backend/schemas/game.py

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    prompt: str | None = None           # ← 추가: 게임 생성 요청 프롬프트
```

### 7.2 ProjectResponse 스키마 변경

```python
class ProjectResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    game_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    world_summary: str | None = None    # ← 추가: 생성 결과 요약
```

### 7.3 game_service.create_project() 수정

```python
# app/backend/services/game_service.py

async def create_project(
    self,
    user_id: int,
    name: str,
    description: str | None,
    prompt: str | None,                 # ← 추가
    db: AsyncSession,
) -> Project:
    # ① 기존 로직 (프로젝트 수 제한, game_id 채번, base_game 복사)
    ...

    # ② prompt가 있으면 The World 파이프라인 실행
    if prompt:
        try:
            result = await self._run_generation(game_id, prompt)
            project.world_summary = result.get("world_summary", "")
            # status를 "generated"로 변경 (선택)
        except Exception:
            logger.warning("게임 생성 실패, base_game 상태로 유지 | game_id=%s", game_id)
            # 생성 실패해도 프로젝트 자체는 생성됨 (base_game 상태)

    return project


async def _run_generation(self, game_id: str, prompt: str) -> dict:
    """The World 파이프라인 실행."""
    from agent.generation.workflow import generation_graph

    result = await generation_graph.ainvoke({
        "user_prompt": prompt,
        "game_id": game_id,
    })
    return {
        "world_summary": result.get("world_summary", ""),
        "success": result.get("success", False),
        "generated_files": result.get("generated_files", []),
    }
```

### 7.4 games 엔드포인트 수정

```python
# app/backend/api/v1/endpoints/games.py

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await game_service.create_project(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        prompt=request.prompt,              # ← 추가
        db=db,
    )
    return ProjectResponse.model_validate(project)
```

---

## 8. 데이터 흐름 예시

### 8.1 요청 → 응답

```
POST /api/v1/games
{
    "name": "신데렐라 RPG",
    "prompt": "주인공이 genie인 신데렐라 이야기의 게임을 만들어줘"
}

→ 응답 (201 Created):
{
    "id": 5,
    "game_id": "game_a1b2c3d4",
    "name": "신데렐라 RPG",
    "status": "generated",
    "world_summary": "게임을 생성했습니다!\n- 제목: 유리구두의 마법사\n- 세계관: 동화 판타지\n- 스토리: 마법사 Genie가 사악한 계모의 저주를 풀고...\n- 파티: Genie(마법사), 왕자(전사), 요정대모(힐러)\n- 보스: 사악한 계모\n- 맵: 신데렐라의 집, 마법의 숲, 왕궁\n- 난이도: 보통",
    ...
}
```

### 8.2 내부 파이프라인 흐름

```
user_prompt: "주인공이 genie인 신데렐라 이야기의 게임을 만들어줘"

[GameDesigner] LLM 1회 호출 →
  WorldSpec:
    game_title: "유리구두의 마법사"
    theme: "동화 판타지"
    story_synopsis: "마법사 Genie가 사악한 계모의 저주를 풀고 왕궁 무도회에서..."
    party: [{name:"Genie", role:"마법사", class_name:"마법사", gender:"male"},
            {name:"왕자", role:"전사", class_name:"전사", gender:"male"},
            {name:"요정대모", role:"힐러", class_name:"힐러", gender:"female"}]
    enemies: [{name:"쥐병사", tier:"weak"}, {name:"못된 언니", tier:"normal"},
              {name:"사악한 계모", tier:"boss"}]
    maps: [{name:"신데렐라의 집", map_type:"town"},
           {name:"마법의 숲", map_type:"field"},
           {name:"왕궁", map_type:"dungeon"}]

[AssetPlanner] →
  IdTable:
    actors: {"Genie":1, "왕자":2, "요정대모":3}
    classes: {"마법사":1, "전사":2, "힐러":3}
    skills: {"공격":1, "방어":2, "마법사_skill_1":3, "마법사_skill_2":4,
             "마법사_skill_3":5, "마법사_skill_4":6, "전사_skill_1":7,
             "전사_skill_2":8, "전사_skill_3":9, "힐러_skill_1":10,
             "힐러_skill_2":11, "힐러_skill_3":12}
    items: {"HP포션(소)":1, "HP포션":2, "MP포션(소)":3, "MP포션":4}
    weapons: {"마법사_무기":1, "전사_무기":2, "힐러_무기":3}
    armors: {"방패":1, "갑옷":2, "장신구":3}
    enemies: {"쥐병사":1, "못된 언니":2, "사악한 계모":3}
    maps: {"신데렐라의 집":1, "마법의 숲":2, "왕궁":3}

[Architect] LLM 1회 호출 → (창작 콘텐츠만 출력)
  GameBlueprint:
    classes: [{id:1, name:"마법사", role:"mage", learnings:[{level:1,skill_id:3}...]}, ...]
    actors: [{id:1, name:"Genie", class_id:1, face_name:"Actor1", ...}, ...]
    skills: [{id:3, name:"파이어볼", description:"불꽃을 발사한다", damage_type:1,
              element:"불", formula:"a.mat*2.5-b.mdf", mp_cost:8, scope:1}, ...]
    items: [{id:1, name:"치유의 허브", description:"상처를 치료한다", recover_hp_rate:30, ...}]
    enemies: [{id:1, name:"쥐병사", battler_name:"Rat", tier:"weak", exp:30, gold:15}, ...]
    ...

[Builder] → (MZ 구조 조립)
  Skills.json: damage 객체 조립 {critical,elementId,formula,type,variance}
  Items.json: effects[] 배열 조립 [{code:11,dataId:0,value1:0.3,value2:20}]
  Weapons.json: wtypeId/etypeId 변환
  Armors.json: atypeId/etypeId 변환
  Enemies.json: tier→params[8] 생성, dropItems 3개 패딩, actions[] 조립
  Troops.json: pages[] 배열 추가, members[].hidden 추가
  Classes.json: build_params_2d("mage") → 8×100 params 알고리즘 생성

[Validator] →
  check_null_at_index_0: OK
  check_id_references: OK
  check_resource_filenames: OK
  success: true
```

### 8.3 이후 수정 (기존 파이프라인)

```
POST /api/v1/llm/process
{ "project_id": 5, "message": "파티에 고양이 캐릭터 추가해줘" }

→ 기존 router → definition → planner → executor → validator → synthesizer
→ Actors.json에 고양이 캐릭터 추가
```

---

## 9. RPG Maker MZ 제약 사항

> 출처: `docs/The_world/rpgmaker_constraints.md`

### 9.1 공통 규칙

| 규칙 | 설명 |
|------|------|
| 배열[0] = null | 모든 데이터 JSON 배열의 첫 번째 원소는 `null` |
| id = 배열 인덱스 | `Actors.json[1].id == 1` |
| 참조 유효성 | `Actor.classId` → `Classes.json`에 존재 |

### 9.2 파일별 제약 (실제 MZ JSON 구조 기반)

| 파일 | 필드 | 제약 |
|------|------|------|
| **Actors.json** | `equips` | 5개 고정: `[weapon, shield, head, body, accessory]`, 없으면 0 |
| | `faceIndex` | 0~7 |
| | params | **Actor에 없음** — Class에서 관리 |
| **Classes.json** | `params` | `list[list[int]]` **8×100 = 800개** (인덱스 0 포함) |
| | `expParams` | 4개: `[base, extra, acc_a, acc_b]` |
| **Skills.json** | `damage` | **중첩 객체**: `{critical, elementId, formula, type, variance}` |
| | `hitType` | 0=확정, 1=물리, 2=마법 |
| | `successRate` | 기본 100 |
| | `effects[]` | 효과 배열 |
| | `message1/2` | 스킬 사용 메시지 |
| | `requiredWtypeId1/2` | 필요 무기 타입 |
| | `scope` | 0=없음, 1=적1, 2=적전체, 7=아군1, 8=아군전체, 11=사용자 |
| | `occasion` | 0=항상, 1=전투중만, 2=메뉴만, 3=불가 |
| | `formula` | JS식: `a.atk`, `b.def` 등 (`damage.formula`에 위치) |
| **Items.json** | `effects[]` | 회복: `[{code:11, dataId:0, value1:rate, value2:flat}]` (HP=code 11, MP=code 12) |
| | `itypeId` | 1=일반 아이템 |
| | `consumable` | true/false |
| | `damage` | 중첩 객체 (스킬과 동일 구조) |
| **Weapons.json** | `wtypeId` | 무기 유형 ID (**weapon_type_id 아님**) |
| | `etypeId` | 항상 1 (무기 장비 슬롯) |
| **Armors.json** | `atypeId` | 방어구 유형 ID (**armor_type_id 아님**) |
| | `etypeId` | 장비 슬롯: 2=방패, 3=머리, 4=몸, 5=장신구 |
| **Enemies.json** | `params` | 8개: `[HP, MP, ATK, DEF, MAT, MDF, AGI, LUK]` |
| | `battlerHue` | 색조 (기본 0) |
| | `dropItems` | **항상 정확히 3개** (빈 슬롯: `{kind:0, dataId:0, denominator:1}`) |
| | `actions[]` | `{skillId, conditionType, conditionParam1, conditionParam2, rating}` |
| **Troops.json** | `members[]` | `{enemyId, x, y, hidden}` — **hidden 필드 필수** |
| | `pages[]` | **필수 배열**: `[{conditions:{...}, list:[{code:0,...}], span:0}]` |
| **System.json** | `partyMembers` | actor id 배열 |

### 9.3 유효 리소스 파일명

> 출처: `docs/The_world/rpgmaker_default_assets.md`

| 카테고리 | 파일명 예시 | 비고 |
|----------|-----------|------|
| faces/ | `Actor1`~`Actor3`, `People1`~`People4`, `Evil` | index 0~7 |
| sv_actors/ | `Actor1_1`(남검사), `Actor2_1`(여검사) | 전투 스프라이트 |
| enemies/ | `Slime`, `Goblin`, `Dragon`, `Darklord` 등 | 적 이미지 |
| BGM | `Town1`~`Town3`, `Dungeon1`~`Dungeon3`, `Battle1`~`Battle3` | 맵/전투 |

---

## 10. 리스크 및 대응

### 10.1 기술적 리스크

| # | 리스크 | 심각도 | 대응 |
|---|--------|:------:|------|
| R1 | **ID 참조 정합성** | P0 | AssetPlanner에서 ID 사전 확정 + `check_id_references()` |
| R2 | **params 792개 생성 불가** | P0 | LLM은 role만, 알고리즘이 `build_params_2d()` 생성 |
| R3 | **필수 필드 누락** | P0 | base_game 기본값 + Pydantic 검증 |
| R4 | **리소스 파일명 오류** | P1 | 유효 목록 프롬프트 주입 + `check_resource_filenames()` |
| R7 | **Architect 스키마 불일치** | P1 | Pydantic validation + 재시도 |
| R8 | **밸런스 붕괴** | P2 | 티어별 스탯 범위 가이드 프롬프트 주입 |
| R9 | **scope/occasion enum 오류** | P1 | 정확한 값 프롬프트 명시 + Pydantic enum |
| R10 | **맵 데이터 복잡성** | P2 | Phase 1에서는 base_game 맵 복사 |
| R11 | **GameDesigner가 부족한 정보를 이상하게 보충** | P1 | 프롬프트에 수량 범위/구성 가이드 명시 |
| R12 | **생성 시간 초과 (LLM 2회 호출)** | P1 | 타임아웃 설정, 실패 시 base_game 유지 |
| R16 | **시작 좌표가 벽 타일** | P0 | base_game 좌표 재사용 |

### 10.2 구현 범위 리스크

| 리스크 | 대응 |
|--------|------|
| **시간 부족 (4/7 오전)** | Phase 1 MVP만. 맵/이벤트는 base_game 그대로 |
| **팀원 코드 충돌** | `agent/generation/` 독립 모듈 |
| **기존 수정 파이프라인 호환** | 생성 완료 후 base_game과 동일한 파일 구조 |
| **생성 실패 시** | 프로젝트 자체는 생성됨 (base_game 상태로 폴백) |

---

## 11. 구현 우선순위

### Phase 1 — MVP (4/7 오전)

- [ ] `agent/generation/state.py` — GenerationState
- [ ] `agent/generation/schemas/world_spec.py` — WorldSpec
- [ ] `agent/generation/schemas/game_blueprint.py` — GameBlueprint (핵심 필드)
- [ ] `agent/generation/registry/id_table.py` — IdTable
- [ ] `agent/generation/nodes/game_designer.py` — prompt → WorldSpec
- [ ] `agent/generation/nodes/asset_planner.py` — ID 확정
- [ ] `agent/generation/nodes/architect.py` — GameBlueprint 생성
- [ ] `agent/generation/nodes/builder.py` — JSON 파일 생성
- [ ] `agent/generation/balance/stat_templates.py` — params 곡선 알고리즘
- [ ] `agent/generation/workflow.py` — StateGraph
- [ ] `agent/generation/routing.py`
- [ ] `app/backend/schemas/game.py` — ProjectCreate에 prompt 추가
- [ ] `app/backend/services/game_service.py` — _run_generation() 추가
- [ ] 맵/이벤트는 base_game 그대로 복사

### Phase 2 — 확장 (4/12 최종 마감)

- [ ] Items, Weapons, Armors 생성 로직
- [ ] Troops 자동 구성
- [ ] 이미지 매핑 정교화 (role+gender → face/character/battler)
- [ ] 적 밸런스 검증 (`simulate_battle()`)
- [ ] MapInfos.json 커스터마이징 (맵 이름/연결)
- [ ] GenerationValidator 전체 검증 함수
- [ ] 에러 핸들링 + 재시도 강화

### Phase 3 — 고도화 (이후)

- [ ] 맵 타일 알고리즘 생성 — `The_world/map_generation.md` 참조
- [ ] 이벤트 DSL + 컴파일러 — `The_world/dsl_specification.md` 참조
- [ ] NPC, 상점, 보스 전투 이벤트 자동 생성
- [ ] 프론트엔드 생성 진행률 표시

---

## 부록: 참조 문서 (docs/The_world/)

| 문서 | Phase | 활용 |
|------|:-----:|------|
| `rpgmaker_constraints.md` | 1 | Builder 필드 제약 레퍼런스 |
| `classes_params_generation.md` | 1 | `build_params_2d()`, `CLASS_STAT_TEMPLATE` |
| `balance_and_economy.md` | 1~2 | 적 스탯, EXP, 아이템 가격, 데미지 공식 |
| `rpgmaker_default_assets.md` | 1~2 | 유효 리소스 파일명 |
| `risks_and_mitigations.md` | 1~2 | R1~R10 대응, 검증 함수 |
| `asset_generation.md` | 2 | 에셋 병렬 생성 패턴 |
| `dsl_specification.md` | 3 | 이벤트 DSL + 컴파일러 |
| `map_generation.md` | 3 | BSP/격자 맵 알고리즘 |
