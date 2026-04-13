# RPG Maker MZ JSON 제약 조건

> `agent/schemas/`의 실제 Pydantic 스키마에서 추출한 필드 제약
> Full Generation의 에셋 생성 노드(C)가 이 조건을 반드시 만족해야 함

---

## 공통 규칙 (모든 JSON 파일)

```
1. 배열의 첫 번째 원소(인덱스 0)는 반드시 null이어야 한다.
   → Actors.json[0] = null, Skills.json[0] = null, ...
   → 실제 데이터는 인덱스 1부터 시작

2. id 필드는 배열 인덱스와 일치해야 한다.
   → Actors.json[1].id = 1, Actors.json[2].id = 2, ...

3. 참조 필드(classId, skillId 등)는 해당 파일에 존재하는 id를 가리켜야 한다.
   → Actor.classId = 2 → Classes.json[2].id = 2 가 있어야 함
```

---

## Actors.json

**소스**: `agent/schemas/actors.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | 배열 인덱스와 일치 |
| `name` | str | 필수 | 캐릭터 이름 |
| `classId` | int | ≥ 1 | Classes.json의 id 참조 |
| `initialLevel` | int | 1~99 | 기본값 1 |
| `maxLevel` | int | 1~99 | 기본값 99 |
| `faceName` | str | 필수 | 얼굴 이미지 파일명 (확장자 없음) |
| `faceIndex` | int | 0~7 | 얼굴 이미지 슬롯 번호 |
| `characterName` | str | 필수 | 보행 스프라이트 파일명 |
| `characterIndex` | int | 0~7 | 보행 스프라이트 슬롯 번호 |
| `battlerName` | str | 필수 | 전투 스프라이트 파일명 |
| `equips` | list[int] | 5개 고정 | [무기, 방어구, 머리, 몸통, 장신구] ID 목록 |
| `traits` | list[Trait] | 기본 [] | 특성 목록 |

### params 구조 (Actor)

Actor에는 `params` 필드가 **없다** — 레벨당 스탯은 **Class**에서 관리한다.

```python
# 오해하기 쉬운 부분: Actor.params ≠ Enemy.params
# Actor의 스탯 성장 곡선은 Class(직업)에 정의됨
# Actor 자체에는 equips(장비), traits(특성)만 있음
```

### 기본 이미지 값 (RPG Maker MZ 기본 리소스 기준)

```python
ACTOR_IMAGE_DEFAULTS = {
    "faceName":       "Actor1",    # faces/Actor1.png
    "faceIndex":      0,           # 0~7 중 하나
    "characterName":  "Actor1",    # characters/Actor1.png
    "characterIndex": 0,
    "battlerName":    "Actor1_1",  # sv_actors/Actor1_1.png (사이드뷰)
}

# 캐릭터 수에 따라 인덱스 배분 (최대 8명이 한 파일에)
# Actor1: 인덱스 0~7
# Actor2: 인덱스 0~7
# ...
```

---

## Classes.json

**소스**: `agent/schemas/classes.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 필수 | 직업 이름 |
| `expParams` | list[int] | 4개 고정 | EXP 성장 파라미터 `[base, extra, acc_a, acc_b]` |
| `params` | list[list[int]] | 8×99 = 792개 | 레벨1~99의 스탯 (HP, MP, ATK, DEF, MAT, MDF, AGI, LUK) |
| `skills` | list[{level, skillId}] | 기본 [] | 레벨업 시 습득 스킬 |
| `traits` | list[Trait] | 기본 [] | |

### params 구조 (Class)

```python
# Class.params: 8개 스탯 × 99레벨 = 792개 정수
# params[stat_index][level - 1] 로 접근

# stat_index:
#   0 = MHP (최대 HP)
#   1 = MMP (최대 MP)
#   2 = ATK (공격력)
#   3 = DEF (방어력)
#   4 = MAT (마법공격력)
#   5 = MDF (마법방어력)
#   6 = AGI (민첩성)
#   7 = LUK (행운)

# 예시: 전사 클래스, 레벨 1의 HP
warrior_hp_lv1 = class_data["params"][0][0]   # params[MHP][lv1-1]

# JSON 실제 형식: params는 중첩 배열 [8][99]
{
  "params": [
    [150, 165, 181, ...],  # MHP 레벨1~99
    [60,  66,  72,  ...],  # MMP 레벨1~99
    [12,  13,  15,  ...],  # ATK 레벨1~99
    ...
  ]
}
```

### expParams 해설

```python
# RPG Maker MZ EXP 공식:
# EXP(level) = base * (level - 1)^acc_a / (acc_b ** acc_a) + (level - 1) * extra
#
# 일반적인 값:
expParams_standard = [30, 20, 30, 30]    # 보통 성장
expParams_fast     = [30, 20, 20, 20]    # 빠른 레벨업
expParams_slow     = [30, 20, 40, 40]    # 느린 레벨업
```

---

## Skills.json

**소스**: `agent/schemas/skills.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 필수 | |
| `stypeId` | int | ≥ 0 | 스킬 유형 (1=마법, 2=특수기) |
| `mpCost` | int | 0~9999 | MP 소비 |
| `tpCost` | int | 0~100 | TP 소비 |
| `scope` | int | 0~14 | 대상 범위 (아래 표 참조) |
| `occasion` | int | 0~3 | 사용 가능 상황 (아래 표 참조) |
| `speed` | int | ≤ 2000 | 속도 보정 (음수 가능) |
| `successRate` | int | 1~100 | 성공률 (%) |
| `repeats` | int | 1~9 | 연속 횟수 |
| `hitType` | int | 0~2 | 명중 유형 |
| `animationId` | int | ≥ -1 | 애니메이션 ID (-1=없음) |
| `damage` | Damage | 필수 | 피해 정의 |
| `effects` | list[Effect] | 기본 [] | 사용 효과 |

### scope 허용값

| 값 | 의미 |
|----|------|
| 0 | 없음 |
| 1 | 적 1체 (일반 공격) |
| 2 | 적 전체 |
| 3 | 적 1체 (랜덤) |
| 4 | 적 2체 (랜덤) |
| 5 | 적 3체 (랜덤) |
| 6 | 적 4체 (랜덤) |
| 7 | 아군 1체 (전투 가능) |
| 8 | 아군 전체 (전투 가능) |
| 9 | 아군 1체 (전투 불능) |
| 10 | 아군 1체 (모두) |
| 11 | 사용자 자신 |
| 12 | 아군 전체 (전투 불능 포함) |
| 13 | 전체 |
| 14 | 없음 (scope=14도 유효) |

### occasion 허용값

| 값 | 의미 |
|----|------|
| 0 | 항상 (전투 + 메뉴) |
| 1 | 전투 중만 |
| 2 | 메뉴에서만 |
| 3 | 사용 불가 |

### damage.type 허용값

| 값 | 의미 |
|----|------|
| 0 | 없음 |
| 1 | HP 대미지 |
| 2 | MP 대미지 |
| 3 | HP 회복 |
| 4 | MP 회복 |
| 5 | HP 흡수 |
| 6 | MP 흡수 |

### damage.formula 작성 규칙

```python
# 허용되는 변수:
#   a = 사용자 (attacker)
#   b = 대상 (target)
#   v = 변수 배열 (v[1] 형식)

# 허용되는 속성:
#   .atk, .def, .mhp, .mmp, .mat, .mdf, .agi, .luk
#   .hp, .mp, .level

# 예시:
"a.atk * 2 - b.def"         # 일반 물리 공격
"a.mat * 2.5 - b.mdf"       # 마법 공격
"a.mat * 1.5 + 50"          # 회복 (HP 회복 스킬)
"a.atk * 3 - b.def * 2"     # 강한 물리
"a.atk * 0.8 - b.def"       # 전체 공격 (낮은 계수)
```

### hitType 허용값

| 값 | 의미 |
|----|------|
| 0 | 확정 명중 |
| 1 | 물리 공격 (회피 판정) |
| 2 | 마법 공격 (마법회피 판정) |

---

## Items.json

**소스**: `agent/schemas/items.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 필수 | |
| `itypeId` | int | 필수 | 1=일반, 2=핵심(소모불가) |
| `price` | int | ≥ 0 | 구매 가격 (판매가 = price/2) |
| `consumable` | bool | 기본 true | true면 사용 후 소모 |
| `scope` | int | 0~14 | Skill.scope와 동일 |
| `occasion` | int | 0~3 | Skill.occasion과 동일 |
| `effects` | list[Effect] | 기본 [] | |

### Effect (사용 효과) 구조

```python
# Effect.code 주요 값:
#   11 = HP 회복      value1=회복률(0.0~1.0), value2=고정값
#   12 = MP 회복      value1=회복률, value2=고정값
#   13 = TP 획득      value1=0, value2=TP량
#   21 = 상태이상 부여  dataId=상태ID, value1=확률(0.0~1.0)
#   22 = 상태이상 해제  dataId=상태ID, value1=0
#   41 = 성장         dataId=스탯ID, value1=성장량
#   42 = 스킬 습득    dataId=스킬ID
#   43 = 공통 이벤트  dataId=이벤트ID

# HP 50% + 30 고정 회복:
{"code": 11, "dataId": 0, "value1": 0.5, "value2": 30}

# MP 30% 회복:
{"code": 12, "dataId": 0, "value1": 0.3, "value2": 0}

# 독 해제:
{"code": 22, "dataId": 4, "value1": 0}  # dataId=4 = 독 상태
```

---

## Weapons.json

**소스**: `agent/schemas/weapons.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 필수 | |
| `wtypeId` | int | ≥ 0 | 무기 유형 (아래 표) |
| `price` | int | ≥ 0 | |
| `params` | list[int] | **8개 고정** | 스탯 보정값 |
| `animationId` | int | ≥ 0 | 공격 애니메이션 |
| `traits` | list[Trait] | 기본 [] | |

### wtypeId 허용값 (기본 설정 기준)

| 값 | 무기 유형 |
|----|---------|
| 0 | 없음 |
| 1 | 단검 |
| 2 | 검 |
| 3 | 도끼 |
| 4 | 창 |
| 5 | 도리깨 |
| 6 | 지팡이 |
| 7 | 장궁 |
| 8 | 석궁 |
| 9 | 활 |
| 10 | 도구 |

### params 구조 (Weapon / Armor)

```python
# params[8]: 8개 스탯 보정값 (더하기 방식)
# [MHP보정, MMP보정, ATK보정, DEF보정, MAT보정, MDF보정, AGI보정, LUK보정]

# 검 (ATK+15):
[0, 0, 15, 0, 0, 0, 0, 0]

# 마법 지팡이 (MAT+20, MMP+30):
[0, 30, 0, 0, 20, 0, 0, 0]

# 경갑옷 (DEF+10, AGI+2):
[0, 0, 0, 10, 0, 0, 2, 0]
```

---

## Armors.json

**소스**: `agent/schemas/armors.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 필수 | |
| `atypeId` | int | ≥ 0 | 방어구 유형 (아래 표) |
| `etypeId` | int | ≥ 1 | 장비 슬롯 (아래 표) |
| `price` | int | ≥ 0 | |
| `params` | list[int] | **8개 고정** | |
| `traits` | list[Trait] | 기본 [] | |

### atypeId 허용값

| 값 | 방어구 유형 |
|----|-----------|
| 0 | 없음 |
| 1 | 일반 방어구 |
| 2 | 마법 방어구 |
| 3 | 경장갑 |
| 4 | 중장갑 |
| 5 | 소형 방패 |
| 6 | 대형 방패 |

### etypeId (장비 슬롯)

| 값 | 슬롯 |
|----|------|
| 1 | 무기 |
| 2 | 방패 |
| 3 | 머리 |
| 4 | 몸통 |
| 5 | 장신구 |

---

## Enemies.json

**소스**: `agent/schemas/enemies.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 필수 | |
| `battlerName` | str | 필수 | `img/enemies/` 이미지 파일명 |
| `battlerHue` | int | 0~360 | 색조 변환 |
| `params` | list[int] | **8개 고정** | 아래 표 참조 |
| `exp` | int | 0~9,999,999 | 기본 10 |
| `gold` | int | 0~9,999,999 | 기본 5 |
| `dropItems` | list[DropItem] | **3개 고정** | |
| `actions` | list[Action] | 기본 [] | 행동 패턴 |
| `traits` | list[Trait] | 기본 [] | |

### params 유효 범위 (Enemy, 8개 고정)

| 인덱스 | 스탯 | 최솟값 | 최댓값 |
|--------|------|--------|--------|
| 0 | MHP (최대 HP) | 1 | 999,999 |
| 1 | MMP (최대 MP) | 0 | 9,999 |
| 2 | ATK (공격) | 0 | 999 |
| 3 | DEF (방어) | 0 | 999 |
| 4 | MAT (마법공격) | 0 | 999 |
| 5 | MDF (마법방어) | 0 | 999 |
| 6 | AGI (민첩) | 0 | 999 |
| 7 | LUK (행운) | 0 | 999 |

### dropItems 구조 (3개 고정)

```python
# dropItems는 반드시 3개 원소 (빈 슬롯도 kind=0으로 채워야 함)
dropItems = [
    {"kind": 1, "dataId": 1, "denominator": 4},   # 아이템 ID=1, 1/4 확률
    {"kind": 0, "dataId": 1, "denominator": 1},   # 빈 슬롯
    {"kind": 0, "dataId": 1, "denominator": 1},   # 빈 슬롯
]

# kind:
#   0 = 없음
#   1 = 아이템 (Items.json 참조)
#   2 = 무기 (Weapons.json 참조)
#   3 = 방어구 (Armors.json 참조)

# denominator: 1/N 확률 (1~1000)
```

### actions 구조

```python
# conditionType:
#   0 = 항상
#   1 = N번째 턴
#   2 = HP% 이하
#   3 = MP% 이하
#   4 = 상태이상
#   5 = 파티 레벨 이상
#   6 = 스위치

# 기본 공격만 하는 action:
{"skillId": 1, "rating": 5, "conditionType": 5,
 "conditionParam1": 0, "conditionParam2": 0}
# conditionType=5(파티레벨), conditionParam1=0 → 항상 조건 만족

# HP 50% 이하에서 강화 공격:
{"skillId": 5, "rating": 8, "conditionType": 2,
 "conditionParam1": 50, "conditionParam2": 0}
```

---

## Troops.json

**소스**: `agent/schemas/troops.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | int | ≥ 1 | |
| `name` | str | 기본 "" | |
| `members` | list[TroopMember] | 기본 [] | |
| `pages` | list[TroopPage] | 기본 [] | 전투 이벤트 (보통 비움) |

### TroopMember

| 필드 | 제약 |
|------|------|
| `enemyId` | ≥ 0, Enemies.json id 참조 |
| `x` | 전투 화면 X (0~816 권장) |
| `y` | 전투 화면 Y (0~624 권장) |
| `hidden` | 기본 false |

---

## Map*.json

**소스**: `agent/schemas/maps.py`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `width` | int | ≥ 1 | 맵 가로 타일 수 |
| `height` | int | ≥ 1 | 맵 세로 타일 수 |
| `tilesetId` | int | ≥ 0 | Tilesets.json id 참조 |
| `data` | list[int] | width × height × 레이어 수 | 타일 배열 |
| `events` | list[MapEvent\|None] | 첫 원소는 null | 이벤트 목록 |
| `encounterStep` | int | ≥ 1 | 랜덤 인카운터 빈도 (기본 30) |

### data 배열 유효성

```python
# model_validator에서 검증:
len(data) % (width * height) == 0

# 6레이어 기준:
len(data) == width * height * 6

# 예시: 17×13 맵
assert len(data) == 17 * 13 * 6  # = 1326
```

### MapEvent 구조

```python
class MapEvent:
    id: int          # ≥ 1 (이벤트 ID, 배열 인덱스와 일치)
    name: str        # 이벤트 이름
    x: int           # ≥ 0
    y: int           # ≥ 0
    pages: list[MapEventPage]  # 최소 1개 이상 (min_length=1)
```

### MapEventPage.trigger 허용값

| 값 | 트리거 |
|----|--------|
| 0 | action_button (결정키) |
| 1 | player_touch (플레이어 접촉) |
| 2 | event_touch (이벤트 접촉) |
| 3 | auto_run (자동 실행) |
| 4 | parallel_process (병렬 처리) |

### MapEventPage.conditions (페이지 조건)

```python
# 스위치 1번이 ON인 경우에만 페이지 활성화:
conditions = {
    "switch1Id": 1,
    "switch1Valid": True,
    # 나머지 필드는 기본값 (Valid=False)
    ...
}
```

---

## System.json 핵심 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `gameTitle` | str | 게임 제목 |
| `startMapId` | int | 게임 시작 맵 ID |
| `startX` | int | 시작 X 좌표 |
| `startY` | int | 시작 Y 좌표 |
| `partyMembers` | list[int] | 초기 파티 Actor ID 목록 (최대 4명) |
| `switches` | list[str] | 스위치 이름 목록 (인덱스 0 = "", 1부터 이름) |
| `variables` | list[str] | 변수 이름 목록 (동일) |
| `locale` | str | "ko_KR" |
| `currency_unit` | str | 화폐 단위 이름 |
| `battleSystem` | int | 0=턴제, 1=액션전투 |

---

## 흔한 LLM 생성 오류 패턴

| 오류 | 원인 | 수정 방법 |
|------|------|---------|
| `Actors.json[0]`이 null 아님 | LLM이 0번째 원소로 실제 데이터 생성 | Pydantic 검증 → 재시도 |
| `Enemy.params` 길이 ≠ 8 | LLM이 레벨별 성장 배열로 오해 | 프롬프트에 "8개 고정" 명시 |
| `dropItems` 길이 ≠ 3 | LLM이 빈 슬롯 생략 | 생성 후 자동 패딩 |
| `Skill.scope` 범위 초과 | LLM이 14 이상 값 생성 | 허용값 테이블을 프롬프트에 포함 |
| `Weapon.params` 길이 ≠ 8 | LLM이 실제 스탯으로 채움 | "8개 고정 [MHP보정, ...]" 명시 |
| `Class.params` 중첩 배열 오류 | LLM이 flat 배열로 생성 | 프롬프트에 `[[hp1, hp2, ...], [mp1, mp2, ...]]` 형식 명시 |
| `Actor.classId` 범위 초과 | LLM이 id_table 무시 | id_table 값을 프롬프트에 명시, 검증기에서 확인 |

---

## 자동 패딩 유틸리티

```python
# agent/generation/utils/schema_fix.py

def pad_drop_items(drop_items: list) -> list:
    """dropItems를 반드시 3개로 맞춤."""
    empty_slot = {"kind": 0, "dataId": 1, "denominator": 1}
    result = list(drop_items)
    while len(result) < 3:
        result.append(empty_slot)
    return result[:3]   # 3개 초과 시 자르기


def ensure_null_at_index_0(array: list) -> list:
    """배열의 첫 원소가 null인지 보장."""
    if not array:
        return [None]
    if array[0] is not None:
        return [None] + array
    return array


def flatten_class_params(params_2d: list[list[int]]) -> list[list[int]]:
    """
    LLM이 flat 배열로 생성했을 때 2D 배열로 변환 시도.
    정상 입력이면 그대로 반환.
    """
    if not params_2d or isinstance(params_2d[0], list):
        return params_2d  # 이미 2D
    # flat 배열 [792개] → [8][99] 변환
    if len(params_2d) == 8 * 99:
        return [params_2d[i*99:(i+1)*99] for i in range(8)]
    raise ValueError(f"Class.params 형식 불명: 길이={len(params_2d)}")
```

---

## 검증 시 사용하는 스키마 클래스

```python
# agent/generation/nodes/generation_validator.py
from agent.schemas.actors   import ActorsFile
from agent.schemas.classes  import ClassesFile
from agent.schemas.skills   import SkillsFile
from agent.schemas.items    import ItemsFile
from agent.schemas.weapons  import WeaponsFile
from agent.schemas.armors   import ArmorsFile
from agent.schemas.enemies  import EnemiesFile
from agent.schemas.troops   import TroopsFile
from agent.schemas.maps     import MapFile

SCHEMA_MAP = {
    "Actors.json":  ActorsFile,
    "Classes.json": ClassesFile,
    "Skills.json":  SkillsFile,
    "Items.json":   ItemsFile,
    "Weapons.json": WeaponsFile,
    "Armors.json":  ArmorsFile,
    "Enemies.json": EnemiesFile,
    "Troops.json":  TroopsFile,
}

def check_schema_compliance(assets: dict, maps: dict) -> list[str]:
    errors = []
    for fname, schema_cls in SCHEMA_MAP.items():
        if fname not in assets:
            continue
        try:
            schema_cls.model_validate(assets[fname])
        except ValidationError as e:
            for err in e.errors():
                errors.append(f"[schema] {fname}: {err['loc']} — {err['msg']}")

    for map_fname, map_data in maps.items():
        try:
            MapFile.model_validate(map_data)
        except ValidationError as e:
            for err in e.errors():
                errors.append(f"[schema] {map_fname}: {err['loc']} — {err['msg']}")

    return errors
```

---

## 참고 링크

- 에셋 생성 상세: `docs/The_world/asset_generation.md`
- 리스크 R1 (ID 참조 오류): `docs/The_world/risks_and_mitigations.md#r1`
- 실제 스키마 코드: `agent/schemas/`
