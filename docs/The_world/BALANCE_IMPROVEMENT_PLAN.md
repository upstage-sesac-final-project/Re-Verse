# 밸런스 개선 계획 (구현 완료)

> 작성일: 2026-04-09 / 구현 완료: 2026-04-09
> 핵심 원칙: **LLM → DSL (0~10 점수) → 컴파일러 → RPG Maker MZ**
> LLM은 의미/다양성을 담당하고, 컴파일러가 수치를 결정한다.

---

## 설계 철학

```
LLM의 역할: 0~10 점수로 "얼마나 강한지" 판단
컴파일러의 역할: 점수 → 실제 RPG Maker MZ 수치로 매핑
```

**0~10 점수 패턴** (모든 에셋에 통일):
```
0  = 없음/최약
3  = 초반
5  = 중반
7  = 후반
10 = 최강/궁극
```

---

## 구현 완료 내역

### Phase 1: 적 스탯 — tier 기반 알고리즘 강제 ✅

**RPG Maker MZ 데미지 공식**: `데미지 = a.atk * 4 - b.def * 2 (음수면 0)`

**tier별 적 스탯 테이블** (코드: `_ENEMY_STAT_BY_TIER`):

| tier | MHP | ATK | DEF | MAT | MDF | AGI | EXP | GOLD |
|------|-----|-----|-----|-----|-----|-----|-----|------|
| weak | 200 | 16 | 10 | 11 | 8 | 8 | 30 | 15 |
| normal | 500 | 28 | 18 | 20 | 14 | 14 | 350 | 50 |
| elite | 1500 | 45 | 30 | 31 | 24 | 22 | 2000 | 150 |
| boss | 4000 | 60 | 42 | 42 | 34 | 30 | 4500 | 500 |

**클래스 스탯 (maxLevel=20 전용 곡선)** (코드: `_CLASS_STAT_TEMPLATE`):

| role_type | MHP | ATK | DEF | MAT | MDF | AGI |
|-----------|-----|-----|-----|-----|-----|-----|
| warrior | 400→3000 | 15→60 | 12→50 | 5→25 | 8→35 | 10→35 |
| mage | 250→1800 | 5→20 | 6→25 | 15→65 | 12→50 | 10→35 |
| healer | 350→2500 | 8→30 | 10→40 | 12→50 | 14→55 | 9→30 |
| thief | 300→2200 | 12→50 | 7→30 | 5→20 | 7→30 | 18→70 |
| balanced | 350→2500 | 12→45 | 10→40 | 10→40 | 10→40 | 12→40 |

**경험치 곡선** (코드: `_validate_exp_params`):
- `expParams = [5, 5, 2, 30]` (고정, LLM 출력 무시)
- **총 약 16전**으로 lv1→lv20 달성 (5~15분 플레이 기준)

**레벨링 시뮬**:

| 구간 | 적 tier | 레벨업당 전투 | 체감 |
|------|---------|------------|------|
| lv1→4 | weak (30exp) | 1~2전 | 쾌속 성장 |
| lv5→9 | normal (350exp) | 1~2전 | 거의 매전 레벨업 |
| lv10→15 | elite (2000exp) | 1~2전 | 거의 매전 레벨업 |
| lv16→20 | boss (4500exp) | 1~2전 | 보스급도 빠름 |

**체크리스트**:
- [x] `_ENEMY_STAT_BY_TIER` 테이블 정의
- [x] `generate_enemies()` 후처리에서 tier → params 강제 주입 (LLM params 무시)
- [x] exp/gold도 tier 기반 강제
- [x] `_CLASS_STAT_TEMPLATE` maxLevel=20 기준으로 교체
- [x] `_generate_class_params` 보간 곡선 maxLevel=20 기준으로 변경
- [x] `expParams` 고정 [5,5,2,30] — 16전 레벨링 곡선

### Phase 2: 무기/방어구 — power(0~10) + 타입 프로파일 ✅

**무기 타입별 스탯 프로파일** (코드: `_WEAPON_PROFILE`):

| 타입 | 주 스탯 | 부 스탯 |
|------|--------|--------|
| sword/dagger/axe/mace/spear | ATK 100% | - |
| bow/crossbow/gun | ATK 80% | AGI 20% |
| staff | MAT 70% | MDF 30% |
| claw/gauntlet | ATK 60% | AGI 40% |

**방어구 슬롯별 프로파일** (코드: `_ARMOR_PROFILE`):

| etypeId | 슬롯 | 주 스탯 | 부 스탯 |
|---------|------|--------|--------|
| 4 | 몸통 | DEF 100% | - |
| 2 | 방패 | DEF 80% | MDF 20% |
| 3 | 머리 | DEF 50% | MDF 50% |
| 5 | 장신구 | MDF 60% | LUK 40% |

**장비 가격 (골드 수입 기반 역산)** (코드: `_POWER_TO_PRICE_WEAPON/ARMOR`):

| power | 무기 가격 | 방어구 가격 | 비고 |
|-------|----------|-----------|------|
| 2 | 48G | 14G | 초반 |
| 4 | 137G | 55G | 중반 |
| 6 | 412G | 180G | 후반 |
| 8 | 550G | 315G | 최종 |

**골드 경제 시뮬** (16전 총 수입 2060G):

| 구간 | 전투 수입 | 장비 1세트 | 잔액 |
|------|----------|----------|------|
| 초반 (weak 4전) | 60G | 초기 장착 | - |
| 중반 (normal 5전) | 누적 310G | 227G | +83G ✅ |
| 후반 (elite 5전) | 누적 1060G | 682G | +378G ✅ |
| 최종 (boss 2전) | 누적 2060G | 910G | +1150G ✅ |

**체크리스트**:
- [x] `RpgWeapon`/`RpgArmor`에 `power: int` 필드 추가
- [x] `params` 필드를 Pydantic 스키마에서 제거
- [x] 무기 타입별 스탯 프로파일 테이블 구현
- [x] 방어구 슬롯별 스탯 프로파일 테이블 구현
- [x] power → params/price 자동 계산 구현
- [x] 프롬프트에서 params/price 가이드 제거, power 가이드 추가
- [x] 골드 수입 대비 장비 가격 밸런스 검증

### Phase 3: 클래스 역할 — role_type DSL ✅

**DSL**: LLM이 `role_type` 태그 출력 → 시스템이 스탯 성장 템플릿 결정.

```
유효값: warrior | mage | healer | thief | balanced
fallback: role_type 없으면 기존 _ROLE_KEYWORDS 키워드 매칭
```

**체크리스트**:
- [x] `CharacterSpec`에 `role_type: str = "balanced"` 필드 추가
- [x] `game_designer_prompt`에 role_type 선택 가이드 추가
- [x] `generate_classes()`에서 `role_type` 직접 사용
- [x] 하위호환: role_type 없으면 기존 `_ROLE_KEYWORDS` fallback

### Phase 4: 스킬 — power(0~10) + 타입 → formula 자동 생성 ✅

**formula 보간 규칙** (코드: `_calc_skill_formula`):

| 스킬 타입 | power=0 | power=10 | scope 보정 |
|----------|---------|----------|-----------|
| 물리 공격 | `a.atk * 1.5 - b.def` | `a.atk * 5 - b.def * 2` | 전체: ×0.6 |
| 마법 공격 | `a.mat * 1.5 - b.mdf` | `a.mat * 5 - b.mdf * 2` | 전체: ×0.6 |
| 회복 | `a.mat * 0.5 + 20` | `a.mat * 3 + 200` | 전체: ×0.7 |
| 흡수 | `a.atk * 1.5 - b.def` | `a.atk * 3.5 - b.def` | - |
| 버프/상태이상 | `"0"` (damage 없음) | `"0"` | - |

**mpCost = power × 2** (power=0→0, power=5→10, power=10→20)

**체크리스트**:
- [x] `RpgSkill`에 `power: int` 필드 추가
- [x] `damage`/`mpCost` 필드를 Pydantic 스키마에서 제거
- [x] (iconTag 카테고리, power, scope) → formula 보간 구현
- [x] power → mpCost 자동 계산
- [x] 프롬프트에서 formula/mpCost 가이드 제거, power 가이드 추가

---

## 완료 조건 (DoD)

### 전체 DoD

- [x] 모든 tier의 적이 구분 가능한 난이도를 가진다 (weak < normal < elite < boss)
- [x] 무기 장착 시 power에 비례하여 ATK/MAT이 올라간다
- [x] 방어구 장착 시 power에 비례하여 DEF/MDF가 올라간다
- [x] 서로 다른 role_type의 클래스가 서로 다른 스탯 성장을 가진다
- [x] power 0~10에 따라 스킬 데미지가 연속적으로 달라진다
- [x] 전투에서 장비 교체/스킬 선택이 의미 있는 차이를 만든다
- [x] 5~15분 플레이 기준으로 자연스러운 난이도 곡선이 형성된다
- [x] 골드 수입으로 해당 구간 장비를 구매할 수 있다
- [x] 총 약 16전으로 lv1→lv20 달성 가능하다

---

## 구현 커밋 이력

| 커밋 | 내용 |
|------|------|
| `fa617a4` | Phase1: 클래스 스탯 maxLevel=20 곡선 + 적 tier 스탯 강제 |
| `bf2f641` | Phase2: 무기/방어구 power→params/price 알고리즘 |
| `3985cf4` | Phase3+4: 클래스 role_type + 스킬 power→formula |
| `8d3e01c` | 레벨링 밸런스: expParams=[5,5,2,30] + exp 상향 |
| `aea0352` | 장비 가격을 골드 수입에 맞게 조정 |
