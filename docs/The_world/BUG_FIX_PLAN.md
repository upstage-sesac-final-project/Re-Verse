# 에셋 생성 파이프라인 버그 수정 계획

> 작성일: 2026-04-08
> 대상 브랜치: feat/sejong/world

---

## 검증된 사실 (base_game 데이터 기반)

### base_game 아이콘 매핑

**Skills.json** (149개 유효 스킬, 모두 `messageType=1`):
- 물리 공격: 76(기본공격/찌르기), 77(강공격/킥), 78(폭발/사격)
- 마법 공격: 64(불), 65(얼음), 66(번개), 67(물), 68(땅), 69(바람), 70(성), 71(암)
- 회복: 72
- 버프: 34~38, 디버프: 50~54
- 상태이상: 2(독), 3(실명), 4(침묵), 5(흡혈), 6(혼란), 8(수면), 9(마비)
- 방어/특수: 80, 81(방어/반사), 82(도망/숨기)
- `damage.type=0` 패턴: effects 있음=49개 / effects 없음=10개(모두 빈 placeholder)

**Weapons.json** — wtypeId → iconIndex (1:1 고정):
| wtypeId | 이름 | iconIndex |
|---------|------|-----------|
| 1 | 단검 | 96 |
| 2 | 검 | 97 |
| 3 | 철퇴 | 98 |
| 4 | 도끼 | 99 |
| 6 | 지팡이 | 101 |
| 7 | 활 | 102 |
| 8 | 석궁 | 103 |
| 10 | 클로 | 105 |
| 11 | 격투장갑 | 106 |
| 12 | 창 | 107 |

**Armors.json** — etypeId → iconIndex (다수):
| etypeId | 슬롯 | iconIndex 후보 |
|---------|------|---------------|
| 2 | 방패 | 128(대형방패), 129(버클러), 144(팔찌) |
| 3 | 머리 | 130(모자/캡), 132(투구), 133(서클릿), 150(반다나) |
| 4 | 몸통 | 135(일반), 136(경량갑옷), 137(무거운갑옷), 139(로브) |
| 5 | 장신구 | 144(반지류), 145(링), 147(스톤), 151(안경), 205(종) |

### 생성된 게임 데이터 확인 (game_9e5bef58)

**Bug 1 확인**: 7개 스킬 → 3개 클래스가 각 20개 learnings에서 동일 7개 skillId를 순환 반복
```
해커:       [1,2,3,4,5,6,7, 1,2,3,4,5,6,7, 1,2,3,4,5,6]  (unique=7)
드론 조종사: [3,1,2,4,5,6,7, 3,1,2,4,5,6,7, 3,1,2,4,5,6]  (unique=7)
생체공학자:  [4,5,6,7,1,2,3, 4,5,6,7,1,2,3, 4,5,6,7,1,2]  (unique=7)
```
→ 3개 클래스가 완전히 동일한 스킬셋. 역할 구분 불가.

**Bug 2 확인**: 무기/방어구 하드코딩
```
Weapons: "제로의 무기"(icon=0), "미아의 무기"(icon=1), "닥터 K의 무기"(icon=2)
Armors:  "제로의 방어구"(icon=1), "미아의 방어구"(icon=2), "닥터 K의 방어구"(icon=3)
```
→ 캐릭터당 1개씩만 존재. 장비 진행 불가, 아이콘 의미 없음.

**Bug 3 확인**: `damage.type=0`인 스킬 중 일부에 effects 있으나, 빈 경우도 존재 가능
→ LLM이 프롬프트 안내 없이 type=0 생성 시 effects를 빠뜨리면 "아무것도 안 하는 스킬"

**Bug 4 확인**: 아이콘 인덱스가 0~6 (순차) → base_game 패턴과 무관

**Bug 5 확인**: 7개 스킬 모두 `messageType=0` (message1 텍스트 있음에도)
→ 전투 메시지 미표시

---

## Phase 1: 후처리 (리스크 없음, 격리된 변경)

> 대상: `agent/generation/nodes/asset_generator.py`
> 다른 파일 영향: 없음 (generate_*() 함수 내부에서만 처리)

### Bug 5 — messageType=0 → 1 (선택: A)

**위치**: `generate_skills()` (line 589-600)

**변경**: `result.items` 순회 후 `output.append(skill.model_dump())` 직전에 후처리 삽입

```python
# generate_skills() 내부, output.append 전:
d = skill.model_dump()
if d.get("message1") and d.get("messageType") == 0:
    d["messageType"] = 1
output.append(d)
```

**검증**: base_game 149개 스킬 모두 `messageType=1`. game_9e5bef58 7개 모두 `messageType=0`.
후처리는 message1이 있는 경우만 건드리므로 빈 placeholder 스킬에는 영향 없음.

### Bug 4 — iconIndex 매핑 테이블 (선택: B)

**위치**: `generate_skills()`, `generate_weapons()`, `generate_armors()`

**스킬 아이콘**: scope + damage.type 기반 매핑
```python
_SKILL_ICON_MAP = {
    # damage.type 기반
    (1, 1): 76,   # HP대미지 + 적1체 → 물리공격
    (1, 2): 78,   # HP대미지 + 적전체 → 범위공격
    (3, 7): 72,   # HP회복 + 아군1체 → 회복
    (3, 8): 72,   # HP회복 + 아군전체 → 회복
}
# iconIndex가 0이거나 유효 범위(1~312) 밖이면 매핑 적용
```

fallback 로직:
1. `(damage.type, scope)` 매핑 조회
2. 없으면 scope 기반: scope 1~6→76, scope 7~8→72, scope 0/11→81
3. 최종 fallback: 76

**무기 아이콘**: `wtypeId` 기반 (1:1 매핑, 검증 완료)
```python
_WEAPON_ICON_MAP = {1: 96, 2: 97, 3: 98, 4: 99, 6: 101, 7: 102, 8: 103, 10: 105, 11: 106, 12: 107}
# iconIndex==0이면 wtypeId로 매핑
```

**방어구 아이콘**: `etypeId` + `atypeId` 기반
```python
_ARMOR_ICON_MAP = {
    # (etypeId, atypeId) → iconIndex
    (4, 1): 135,  # 몸통/일반
    (4, 2): 139,  # 몸통/마법
    (4, 3): 136,  # 몸통/경량
    (4, 4): 137,  # 몸통/무거운
    (2, 5): 129,  # 방패/버클러
    (2, 6): 128,  # 방패/대형
    (2, 2): 144,  # 방패/팔찌
    (3, 1): 130,  # 머리/모자
    (3, 2): 133,  # 머리/서클릿
    (3, 3): 130,  # 머리/캡
    (3, 4): 132,  # 머리/투구
    (5, 1): 145,  # 장신구/링
}
# iconIndex==0이면 매핑 적용, fallback: etypeId별 기본값
```

**검증**: `iconIndex==0`인 경우에만 매핑 적용 → LLM이 올바른 아이콘을 출력했으면 그대로 유지.

### Bug 3-B — type=0 + effects=[] 후처리 (선택: B)

**위치**: `generate_skills()` 내부

**변경**: damage.type=0이면서 effects가 비어있으면 기본 버프 효과 주입
```python
if d["damage"]["type"] == 0 and not d.get("effects"):
    # scope 기반 기본 효과 결정
    if d.get("scope") in (1, 2, 3, 4, 5, 6):  # 적 대상
        d["effects"] = [{"code": 21, "dataId": 0, "value1": 1, "value2": 0}]  # 일반 공격 추가
    elif d.get("scope") in (7, 8, 9, 10, 11):  # 아군 대상
        d["effects"] = [{"code": 31, "dataId": 2, "value1": 5, "value2": 0}]  # ATK+5 버프
    else:
        d["effects"] = [{"code": 31, "dataId": 2, "value1": 5, "value2": 0}]  # fallback: ATK 버프
```

**검증**: base_game에서 damage.type=0 + effects=[]인 스킬은 10개 (모두 빈 placeholder, name="").
생성 스킬은 name이 있으므로 placeholder와 충돌 없음.

---

## Phase 2: 프롬프트 개선 (리스크 낮음)

> 대상: `agent/generation/prompts/asset_generator_prompt.py`

### Bug 3-A — _SKILLS_SYSTEM에 effects 가이드 추가 (선택: A)

**위치**: `_SKILLS_SYSTEM` (line 63-77)

**추가할 규칙**:
```
7. damage.type=0인 스킬은 반드시 effects를 포함해야 합니다:
   - 적 대상 상태이상: effects=[{"code": 21, "dataId": 상태ID, "value1": 확률, "value2": 0}]
     상태 dataId: 1=사망, 4=독, 5=실명, 6=침묵, 8=혼란, 9=매혹, 10=수면, 12=마비, 13=스턴
   - 아군 대상 버프: effects=[{"code": 31, "dataId": 스탯ID, "value1": 턴수, "value2": 0}]
     스탯 dataId: 2=ATK, 3=DEF, 4=MAT, 5=MDF, 6=AGI, 7=LUK
   - HP/MP 회복 효과: effects=[{"code": 11/12, "dataId": 0, "value1": 비율, "value2": 고정값}]
8. iconIndex 가이드:
   - 물리 공격: 76~78
   - 마법(불/얼음/번개/물/땅/바람/성/암): 64~71
   - 회복: 72
   - 버프: 34~38, 디버프: 50~54
   - 상태이상: 2(독), 3(실명), 9(마비)
   - 방어/반사: 81, 도망: 82
9. messageType: message1이 있으면 반드시 1로 설정 (0=메시지 미표시)
```

**영향 범위**: 프롬프트만 변경 → LLM 출력 품질 개선, 기존 로직 변경 없음

---

## Phase 3: GameSpec 확장 — weapons/armors (리스크 중간)

> 선택: Bug 2-C (game_designer가 무기/방어구 목록 생성)

### 변경 파일 및 영향 분석

| 파일 | 변경 내용 | 영향 범위 |
|------|----------|----------|
| `models.py:47` | `weapons: list[str] = []`, `armors: list[str] = []` 필드 추가 | GameSpec 구조 변경 |
| `game_designer_prompt.py:19` | 프롬프트에 weapons/armors 가이드 추가 | A 노드 출력 변경 |
| `asset_planner.py:74-81` | 하드코딩 → `spec.weapons`/`spec.armors` 사용 | B 노드 로직 변경 |

### 상세 변경

#### models.py
```python
# 기존
skills: list[str] = []

# 추가
weapons: list[str] = []
armors: list[str] = []
```

#### game_designer_prompt.py
```
- weapons: 캐릭터 수 × 2~3개 (무기 이름 목록, 초반~후반 무기 진행)
- armors: 캐릭터 수 × 1~2개 (방어구 이름 목록)
```
예시에 추가:
```json
"weapons": ["단검", "장검", "미스릴 검", "나무 지팡이", "매직 완드"],
"armors": ["가죽조끼", "미늘 갑옷", "면 로브", "버클러"]
```

#### asset_planner.py — _build_id_table()
```python
# 기존 (line 74-81): 하드코딩
weapons: dict[str, int] = {}
armors: dict[str, int] = {}
for i, char in enumerate(spec.characters):
    weapon_name = f"{char.name}의 무기"
    ...

# 변경: spec에서 가져옴
weapons = {w: i + 1 for i, w in enumerate(spec.weapons)}
armors = {a: i + 1 for i, a in enumerate(spec.armors)}

# fallback: spec.weapons가 비어있으면 기존 하드코딩 유지 (하위 호환)
if not weapons:
    for i, char in enumerate(spec.characters):
        weapons[f"{char.name}의 무기"] = i + 1
if not armors:
    for i, char in enumerate(spec.characters):
        armors[f"{char.name}의 방어구"] = i + 1
```

### downstream 영향 (변경 불필요)

모든 downstream 코드는 `id_table.weapons`/`id_table.armors` (dict[str, int]) 인터페이스를 통해 접근:
- `event_compiler.py:76-79` — 이름 → ID 조회 (인터페이스 동일)
- `event_planner.py:206` — 이름 집합 (인터페이스 동일)
- `event_planner_prompt.py:285-286` — 이름 목록 표시 (인터페이스 동일)
- `asset_generator_prompt.py:166,202,422-423` — ID 매핑 전달 (인터페이스 동일)
- `generation_responder.py:23` — 카운트 (인터페이스 동일)

→ **id_table 인터페이스가 동일하므로 downstream 변경 0개**

### 하위 호환 리스크

기존 저장된 GameSpec (DB/캐시)에 `weapons`/`armors` 필드가 없을 수 있음.
→ `list[str] = []` 기본값으로 처리 + fallback 로직으로 하드코딩 유지

---

## Phase 4: GameSpec 구조 변경 — SkillSpec (리스크 중간)

> 선택: Bug 1-B+C (SkillSpec 모델 + 클래스별 learnings 필터링)

### 변경 파일 및 영향 분석

| 파일 | 변경 내용 | 영향 범위 |
|------|----------|----------|
| `models.py` | `SkillSpec` 모델 추가, `skills: list[str]` → `list[SkillSpec]` | GameSpec 구조 변경 |
| `game_designer_prompt.py` | 스킬에 class_name 연관 + 수량 상향 | A 노드 출력 변경 |
| `asset_planner.py:69` | `enumerate(spec.skills)` → `enumerate(s.name for s)` | B 노드 로직 변경 |
| `asset_generator_prompt.py:80-98` | `build_skills_prompt()`에 역할 힌트 추가 | C 노드 프롬프트 변경 |
| `asset_generator.py:551-586` | `generate_classes()`에 역할별 스킬 필터링 | C 노드 로직 변경 |

### 상세 변경

#### models.py — SkillSpec 추가
```python
class SkillSpec(BaseModel):
    name: str
    class_name: str  # 이 스킬을 배울 수 있는 직업

# GameSpec 변경
skills: list[SkillSpec] = []  # 기존: list[str]
```

#### game_designer_prompt.py — 스킬 가이드 변경
```
기존: - skills: 2~8개 (스킬 이름 목록)
변경: - skills: 클래스당 4~6개, 총 8~20개 (각 스킬에 class_name 지정)
```
예시 변경:
```json
"skills": [
    {"name": "파이어볼", "class_name": "마법사"},
    {"name": "힐", "class_name": "마법사"},
    {"name": "대검 강타", "class_name": "전사"},
    {"name": "대검 난무", "class_name": "전사"},
    {"name": "마나 실드", "class_name": "마법사"},
    {"name": "방패 치기", "class_name": "전사"}
]
```

#### asset_planner.py:69 — 1줄 변경
```python
# 기존
skills = {s: i + 1 for i, s in enumerate(spec.skills)}

# 변경
skills = {s.name: i + 1 for i, s in enumerate(spec.skills)}
```

#### asset_generator_prompt.py — build_skills_prompt() 역할 힌트
```python
# 기존: id와 name만 전달
skill_lines = [
    f"  - id={sid}, name={sname}"
    for sname, sid in sorted(id_table.skills.items(), ...)
]

# 변경: class_name도 전달
skill_class_map = {s.name: s.class_name for s in spec.skills}
skill_lines = [
    f"  - id={sid}, name={sname}, class={skill_class_map.get(sname, '공용')}"
    for sname, sid in sorted(id_table.skills.items(), ...)
]
```

#### asset_generator.py — generate_classes() 역할별 필터링

```python
# 기존 (line 570-574): ID 존재 여부만 체크
learnings = [
    {"level": lr.level, "skillId": lr.skillId, "note": ""}
    for lr in llm_cls.learnings
    if lr.skillId in valid_skill_ids
]

# 변경: 해당 클래스에 배정된 스킬만 허용
# spec.skills에서 class_name → skill_name 매핑 구축
skill_to_class = {s.name: s.class_name for s in spec.skills}
name_to_id = {v: k for k, v in id_table.skills.items()}  # id → name 역매핑

# 이 클래스에 허용된 스킬 ID 집합
allowed_skill_ids = {
    id_table.skills[s.name]
    for s in spec.skills
    if s.class_name == cls_name and s.name in id_table.skills
}

learnings = [
    {"level": lr.level, "skillId": lr.skillId, "note": ""}
    for lr in llm_cls.learnings
    if lr.skillId in valid_skill_ids and lr.skillId in allowed_skill_ids
]
```

### downstream 영향 (변경 불필요)

`spec.skills` 직접 참조: `asset_planner.py:69` 1곳만 (위에서 변경)
`id_table.skills`: dict[str, int] 인터페이스 동일 → downstream 변경 0개

### 하위 호환 리스크

기존 GameSpec에 `skills: list[str]`가 저장되어 있을 수 있음.
→ `SkillSpec` 모델에 `__init__` validator 추가: `str` 입력 시 `SkillSpec(name=str, class_name="공용")`으로 자동 변환

```python
class SkillSpec(BaseModel):
    name: str
    class_name: str = "공용"

class GameSpec(BaseModel):
    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, v):
        return [
            SkillSpec(name=s) if isinstance(s, str) else s
            for s in v
        ]
```

---

## 구현 순서 및 리스크 매트릭스

| Phase | 대상 버그 | 변경 파일 수 | 리스크 | 롤백 용이성 |
|-------|---------|------------|--------|-----------|
| 1 | Bug 5+4+3B | 1 (asset_generator.py) | **낮음** | 후처리 코드 삭제만으로 원복 |
| 2 | Bug 3A | 1 (asset_generator_prompt.py) | **낮음** | 프롬프트 원복만으로 원복 |
| 3 | Bug 2C | 3 (models, prompt, planner) | **중간** | fallback 있음 |
| 4 | Bug 1BC | 5 (models, 2 prompts, planner, generator) | **중간** | validator로 하위호환 |

### 검증 계획

| Phase | 검증 방법 |
|-------|----------|
| 1 | 기존 테스트 통과 + game_9e5bef58 재생성 후 Skills/Weapons/Armors iconIndex/messageType 확인 |
| 2 | 기존 테스트 통과 + LLM 출력에 effects/iconIndex/messageType 포함 여부 확인 |
| 3 | 기존 테스트 통과 + id_table.weapons/armors 카운트 > 캐릭터 수 확인 |
| 4 | 기존 테스트 통과 + Classes learnings에서 클래스별 unique skill 비율 확인 |
