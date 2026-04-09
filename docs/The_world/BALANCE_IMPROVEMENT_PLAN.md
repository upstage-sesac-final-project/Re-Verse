# 밸런스 개선 계획

> 작성일: 2026-04-09
> 핵심 원칙: **LLM → DSL (0~10 점수) → 컴파일러 → RPG Maker MZ**
> LLM은 의미/다양성을 담당하고, 컴파일러가 수치를 결정한다.

---

## 설계 철학

```
LLM의 역할: 0~10 점수로 "얼마나 강한지" 판단
컴파일러의 역할: 점수 → 실제 RPG Maker MZ 수치로 매핑

LLM에게 숫자 배열을 맡기면 → 보스 HP=150, 방어구 DEF=0 같은 사고 발생
LLM에게 0~10 점수만 맡기면 → "7 정도" 같은 직관적 판단은 잘 함
```

**0~10 점수 패턴** (모든 에셋에 통일):
```
0  = 없음/최약
3  = 초반
5  = 중반
7  = 후반
10 = 최강/궁극
```

iconTag DSL과 동일한 사상:
- iconTag: LLM이 `"sword"` → 시스템이 `97`
- 밸런스: LLM이 `power: 7` → 시스템이 `ATK+25, formula="a.atk*3.5-b.def*2"`

---

## 현재 문제점 (실측 데이터 기반)

### P1. 적 스탯이 tier와 무관하게 동일

```
일반 좀비(weak):    HP=150, ATK=10, DEF=1
부패된 보스(boss):  HP=150, ATK=18, DEF=1  ← 보스가 잡몹과 HP 같음
```

- 원인: LLM이 생성한 params를 그대로 사용
- LLM은 8개 스탯 배열의 밸런스를 맞출 능력이 없음

### P2. 무기 params 구조 오류 + 효과 없음

```
목검: params=[15, 0, 0, 0, 0, 0, 0, 0]  ← MHP에 15 (ATK이어야 함)
손전등: params=[0, 0, 0, 0, 0, 0, 0, 0]  ← 장착해도 효과 없음
```

- 원인: LLM이 params 순서([MHP,MMP,ATK,DEF,MAT,MDF,AGI,LUK])를 모름

### P3. 방어구 params 전부 [0,0,0,0,0,0,0,0]

```
강화 조끼: params=[0,0,0,0,0,0,0,0]  ← DEF 보정 없음
```

- 원인: P2와 동일

### P4. 모든 클래스가 동일 스탯

```
생존자/의사/기술자: 전부 MHP(150,2000) ATK(14,200)  ← 구분 없음
```

- 원인: `_normalize_role()`이 비판타지 클래스를 전부 `default`로 매핑

### P5. 스킬 데미지 공식 단조로움

```
고압 세척 / 폭발물 설치 / 전기 충격: 전부 "a.atk * 2 - b.def"
```

- 원인: LLM이 프롬프트 예시를 그대로 복사

---

## 개선 계획

### Phase 1: 적 스탯 — tier 기반 알고리즘 강제

**DSL**: LLM은 tier만 출력 (이미 GameSpec.enemies에 있음). 시스템이 tier → 고정 스탯 주입.

**RPG Maker MZ 데미지 공식** (실측):
```
데미지 = a.atk * 4 - b.def * 2    (음수면 0)
```

**시뮬레이션 검증 완료** (warrior 기준, 파티 3명):

| tier | 조우 레벨 | 1명 킬턴 | 파티3 킬턴 | 생존턴 | 여유도 |
|------|----------|---------|-----------|--------|--------|
| weak | lv2 | 2.4 | 0.8 | 7.8 | 3.3x(1명) |
| normal | lv6 | 3.8 | 1.3 | 10.5 | 2.8x(1명) |
| elite | lv12 | 7.5 | 2.5 | 12.9 | 1.7x(1명) |
| boss | lv18 | 14.9 | 5.0 | 15.1 | 3.0x(파티) |

**최종 tier별 적 스탯 테이블**:

| tier | MHP | MMP | ATK | DEF | MAT | MDF | AGI | LUK | EXP | GOLD |
|------|-----|-----|-----|-----|-----|-----|-----|-----|-----|------|
| weak | 200 | 20 | 16 | 10 | 11 | 8 | 8 | 5 | 12 | 8 |
| normal | 500 | 50 | 28 | 18 | 20 | 14 | 14 | 8 | 35 | 25 |
| elite | 1500 | 150 | 45 | 30 | 31 | 24 | 22 | 14 | 100 | 70 |
| boss | 4000 | 400 | 60 | 42 | 42 | 34 | 30 | 18 | 400 | 250 |

**전제 조건** (클래스 스탯):
```
warrior lv1:  HP=200, ATK=15, DEF=8
warrior lv20: HP=2000, ATK=60, DEF=40
```

**체크리스트**:
- [ ] `_ENEMY_STAT_BY_TIER` 테이블 정의 (위 수치)
- [ ] `generate_enemies()` 후처리에서 tier → params 강제 주입 (LLM params 무시)
- [ ] exp/gold도 tier 기반 강제
- [ ] `_CLASS_STAT_TEMPLATE` 수정: lv1 스탯을 전투 가능 수준으로 상향
  - `"default"` 기존: mhp(150,2000), atk(14,200)
  - `"default"` 변경: mhp(200,2000), atk(15,60) — maxLevel=20 기준 곡선

### Phase 2: 무기/방어구 — power(0~10) + 타입 프로파일

**DSL**: LLM이 `power: 0~10` 출력. 시스템이 (power, wtypeId/etypeId) → params 계산.

```
LLM 출력:
  { name: "산탄총", iconTag: "gun", wtypeId: 9, power: 5 }
  { name: "플라즈마 라이플", iconTag: "gun", wtypeId: 9, power: 9 }

컴파일러:
  무기 프로파일: gun → ATK 위주
  power=5 → ATK+18
  power=9 → ATK+35
```

**무기 타입별 스탯 프로파일**:

| 타입 | 주 스탯 | 부 스탯 | 비고 |
|------|--------|--------|------|
| sword/dagger/axe/mace/spear | ATK 100% | - | 근접 물리 |
| bow/crossbow/gun | ATK 80% | AGI 20% | 원거리 |
| staff | MAT 70% | MDF 30% | 마법 |
| claw/gauntlet | ATK 60% | AGI 40% | 속도형 |

**스탯 수치 = power 기반 보간**:
```
주 스탯 = round(power * max_stat * profile_ratio / 10)
  max_stat = { ATK: 50, MAT: 45, DEF: 40, MDF: 35, AGI: 30 }

예: gun + power=5 → ATK = round(5 * 50 * 0.8 / 10) = 20
    gun + power=9 → ATK = round(9 * 50 * 0.8 / 10) = 36
```

**방어구 타입별 프로파일**:

| etypeId | 슬롯 | 주 스탯 | 부 스탯 |
|---------|------|--------|--------|
| 4 (몸통) | body | DEF 100% | - |
| 2 (방패) | shield | DEF 80% | MDF 20% |
| 3 (머리) | head | DEF 50% | MDF 50% |
| 5 (장신구) | accessory | MDF 60% | LUK 40% |

**체크리스트**:
- [ ] `RpgWeapon`/`RpgArmor`에 `power: int = 5` 필드 추가
- [ ] `params` 필드를 Pydantic 스키마에서 제거 (LLM에 안 보여줌)
- [ ] 무기 타입별 스탯 프로파일 테이블 정의
- [ ] 방어구 슬롯별 스탯 프로파일 테이블 정의
- [ ] power → 수치 보간 공식 구현
- [ ] `generate_weapons()` 후처리에서 power 기반 params 계산
- [ ] `generate_armors()` 후처리에서 power 기반 params 계산
- [ ] price도 power 기반 자동 계산 (power=3→500, power=7→3000 등)
- [ ] 프롬프트에서 params 가이드 제거, power 가이드 추가
- [ ] base_game 데이터와 비교 검증

### Phase 3: 클래스 역할 — role_type DSL

**DSL**: LLM이 `role_type` 태그 출력. 시스템이 스탯 성장 템플릿 결정.

```
LLM 출력 (GameSpec.characters):
  { name: "생존자", class_name: "생존자", role_type: "warrior" }
  { name: "의사", class_name: "의사", role_type: "healer" }

유효값: warrior | mage | healer | thief | balanced
```

**role_type → 스탯 템플릿** (기존 _CLASS_STAT_TEMPLATE 재사용):

| role_type | 특성 | MHP | ATK | MAT | DEF | AGI |
|-----------|------|-----|-----|-----|-----|-----|
| warrior | 체력+물리 | 높음 | 높음 | 낮음 | 높음 | 보통 |
| mage | 마력 | 낮음 | 낮음 | 높음 | 낮음 | 보통 |
| healer | 회복+방어 | 보통 | 낮음 | 보통 | 보통 | 보통 |
| thief | 속도+운 | 보통 | 보통 | 낮음 | 낮음 | 높음 |
| balanced | 균형 | 보통 | 보통 | 보통 | 보통 | 보통 |

**체크리스트**:
- [ ] `CharacterSpec`에 `role_type: str = "balanced"` 필드 추가
- [ ] `game_designer_prompt`에 role_type 선택 가이드 추가
- [ ] `generate_classes()`에서 `role_type` 직접 사용 (→ 기존 `_normalize_role()` 대체)
- [ ] 하위호환: role_type 없으면 기존 `_ROLE_KEYWORDS` fallback

### Phase 4: 스킬 — power(0~10) + 타입 → formula 자동 생성

**DSL**: LLM이 `power: 0~10` 출력. 시스템이 (iconTag, power, scope) → formula/mpCost 계산.

```
LLM 출력:
  { name: "고압 세척", iconTag: "physical_melee", power: 3, scope: 1 }
  { name: "좀비 퇴치", iconTag: "physical_strong", power: 8, scope: 1 }
  { name: "신형 백신", iconTag: "heal", power: 6, scope: 7 }

컴파일러:
  physical + power=3 + single → formula="a.atk * 2.05 - b.def",     mpCost=4
  physical + power=8 + single → formula="a.atk * 3.8 - b.def * 1.6", mpCost=16
  heal     + power=6 + ally   → formula="a.mat * 1.6 + 60",          mpCost=10
```

**formula 보간 규칙**:

| 스킬 타입 | power=0 | power=10 | scope 보정 |
|----------|---------|----------|-----------|
| 물리 공격 | `a.atk * 1.5 - b.def` | `a.atk * 5 - b.def * 2` | 전체(scope=2): 배율 ×0.6 |
| 마법 공격 | `a.mat * 1.5 - b.mdf` | `a.mat * 5 - b.mdf * 2` | 전체(scope=2): 배율 ×0.6 |
| 회복 | `a.mat + 20` | `a.mat * 3 + 200` | 전체(scope=8): 배율 ×0.7 |
| 흡수 | `a.atk * 1.5 - b.def` | `a.atk * 3.5 - b.def` | - |

**mpCost = power × 2** (0=0, 5=10, 10=20)

**체크리스트**:
- [ ] `RpgSkill`에 `power: int = 5` 필드 추가
- [ ] `damage` 필드를 Pydantic 스키마에서 제거 (LLM에 안 보여줌)
- [ ] `mpCost` 필드를 Pydantic 스키마에서 제거
- [ ] (iconTag 카테고리, power, scope) → formula 보간 공식 구현
- [ ] power → mpCost 자동 계산
- [ ] `generate_skills()` 후처리에서 formula/mpCost 자동 생성
- [ ] 프롬프트에서 formula/mpCost 가이드 제거, power 가이드 추가
- [ ] 적 전용 스킬 템플릿(`_ENEMY_SKILL_DATA`)도 power 기반으로 전환

---

## 완료 조건 (DoD)

### 전체 DoD

- [ ] 모든 tier의 적이 구분 가능한 난이도를 가진다 (weak < normal < elite < boss)
- [ ] 무기 장착 시 power에 비례하여 ATK/MAT이 올라간다
- [ ] 방어구 장착 시 power에 비례하여 DEF/MDF가 올라간다
- [ ] 서로 다른 role_type의 클래스가 서로 다른 스탯 성장을 가진다
- [ ] power 0~10에 따라 스킬 데미지가 연속적으로 달라진다
- [ ] 전투에서 장비 교체/스킬 선택이 의미 있는 차이를 만든다
- [ ] 5~15분 플레이 기준으로 자연스러운 난이도 곡선이 형성된다

### Phase별 DoD

**Phase 1 DoD** (적 스탯):
- [ ] weak(score=2) HP < normal(4) HP < elite(7) HP < boss(10) HP
- [ ] 보스 HP가 2000 이상
- [ ] 모든 적의 DEF가 1이 아닌 의미 있는 값
- [ ] tier 간 exp/gold 비율이 자연스러움

**Phase 2 DoD** (무기/방어구):
- [ ] 모든 무기의 주 스탯(ATK 또는 MAT)이 0이 아님
- [ ] 모든 방어구의 주 스탯(DEF 또는 MDF)이 0이 아님
- [ ] power가 높을수록 params 수치가 높음 (단조 증가)
- [ ] 무기 타입별 스탯 분포가 다름 (검≠지팡이≠활)

**Phase 3 DoD** (클래스 역할):
- [ ] 비판타지 테마(좀비, SF, 해적 등)에서도 클래스별 스탯이 다름
- [ ] warrior 계열 ATK > mage 계열 ATK
- [ ] healer 계열 MAT+MDF > warrior 계열 MAT+MDF
- [ ] thief 계열 AGI > 나머지 계열 AGI

**Phase 4 DoD** (스킬 공식):
- [ ] power=3과 power=8의 데미지가 최소 2배 차이
- [ ] 전체 공격(scope=2)이 단일 공격(scope=1)보다 약함
- [ ] 회복 스킬의 회복량이 적 1회 공격 데미지의 50~100%
- [ ] 같은 iconTag라도 power가 다르면 formula가 다름

---

## 구현 순서 및 리스크

| Phase | 대상 | 변경 파일 | 리스크 | 예상 영향 |
|-------|------|----------|--------|----------|
| 1 | 적 스탯 | asset_generator.py | 낮음 (후처리만) | 전투 난이도 정상화 |
| 2 | 무기/방어구 | asset_generator.py, prompt | 낮음 (후처리+스키마) | 장비 의미 생김 |
| 3 | 클래스 역할 | models.py, prompt, generator | 중간 (모델 변경) | 캐릭터 개성 |
| 4 | 스킬 공식 | asset_generator.py, prompt | 중간 (스키마 변경) | 스킬 다양성 |

### 공통 패턴

모든 Phase에서 동일한 패턴:
1. Pydantic 스키마에 `power: int` (0~10) 추가 (또는 기존 tier/role_type 활용)
2. LLM이 숫자 배열 대신 점수 하나만 출력
3. 컴파일러가 점수 → 실제 RPG Maker MZ 수치로 보간
4. LLM이 출력한 수치 필드(params, formula, mpCost)는 무시

```
LLM 부담: "이건 7 정도" (직관적)
시스템 보장: 7 → 항상 같은 규칙으로 수치 생성 (일관적)
```
