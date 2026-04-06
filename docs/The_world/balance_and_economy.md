# 게임 밸런스 & 경제 시스템 설계

> Full Generation에서 LLM에게 전달할 밸런스 가이드라인 + 검증 코드
> 5~10분 플레이타임의 RPG Maker MZ 게임 기준

---

## 설계 원칙

```
1. 플레이어가 레벨 없이도 첫 전투를 이길 수 있어야 한다 (초보 진입 장벽)
2. 보스 전투는 2~3번의 도전이 필요할 수 있다 (긴장감)
3. 아이템 구매가 실질적으로 도움이 돼야 한다 (골드 가치)
4. 게임 클리어 시 레벨 5~8 정도가 자연스럽다 (5~10분 분량)
```

---

## 기본 스탯 설계 (레벨 1 기준값)

### 플레이어 (전사 직업 기준)

| 스탯 | 레벨 1 | 레벨 5 (보스 도전) | 레벨 99 |
|------|--------|-------------------|--------|
| MHP | 150~200 | 300~400 | 2,000~3,000 |
| MMP | 60~100 | 120~180 | 800~1,200 |
| ATK | 12~18 | 24~35 | 200~300 |
| DEF | 6~10 | 12~18 | 100~150 |
| MAT | 8~14 | 16~26 | 150~250 |
| MDF | 6~10 | 12~18 | 100~150 |
| AGI | 8~12 | 16~22 | 100~150 |

### 직업별 특화 보정 (레벨 1 기준값에서 %)

| 직업 | MHP | MMP | ATK | DEF | MAT | MDF | AGI |
|------|-----|-----|-----|-----|-----|-----|-----|
| 전사 | +20% | -10% | +20% | +20% | -10% | 기준 | -5% |
| 마법사 | -10% | +30% | -10% | -10% | +30% | +20% | 기준 |
| 궁수 | 기준 | -10% | +15% | -5% | 기준 | -5% | +25% |
| 성직자 | +10% | +20% | -15% | +10% | +20% | +25% | -5% |

---

## 레벨 성장 곡선 (Class.params)

### EXP 누적 표 (표준 성장)

`expParams = [30, 20, 30, 30]` 기준:

| 레벨 | 누적 EXP | 레벨업에 필요한 EXP |
|------|---------|----------------|
| 1→2 | 30 | 30 |
| 2→3 | 80 | 50 |
| 3→4 | 160 | 80 |
| 4→5 | 280 | 120 |
| 5→6 | 450 | 170 |
| 6→7 | 670 | 220 |
| 7→8 | 950 | 280 |

5~10분 게임에서 레벨 5~8 도달이 목표이므로:
- 잡몹 1마리 당 EXP: 30~70
- 던전 전투 5~8회로 레벨 5 도달

```python
def compute_exp_needed(level: int, params: list[int]) -> int:
    """
    RPG Maker MZ EXP 공식.
    params = [base, extra, acc_a, acc_b]
    """
    base, extra, acc_a, acc_b = params
    if level <= 1:
        return 0
    n = level - 1
    return int(base * (n ** (acc_a / acc_b)) + n * extra)
```

### HP 성장 코드 생성

```python
def generate_class_params(
    stat_lv1: int,
    stat_lv99: int,
    growth: str = "linear",
) -> list[int]:
    """
    레벨 1~99 스탯 배열 생성.
    growth: "linear" | "accelerate" | "decelerate"
    """
    import math
    result = []
    for lv in range(1, 100):
        t = (lv - 1) / 98  # 0.0 ~ 1.0
        if growth == "accelerate":
            t = t ** 2
        elif growth == "decelerate":
            t = math.sqrt(t)
        value = int(stat_lv1 + (stat_lv99 - stat_lv1) * t)
        result.append(value)
    return result


# 예시: 전사 HP (레벨1=180, 레벨99=2500, 가속 성장)
warrior_hp = generate_class_params(180, 2500, growth="accelerate")
assert warrior_hp[0] == 180
assert warrior_hp[98] == 2500
```

---

## 적 스탯 설계

### 5~10분 게임 기준 밸런스 공식

```python
# 플레이어 레벨 1 기준값 (전사)
PLAYER_LV1 = {
    "hp":  175,  # 중간값
    "atk": 15,
    "def": 8,
    "mat": 11,
    "mdf": 8,
}

# 적 티어별 스탯 범위
ENEMY_STAT_GUIDE = {
    "weak": {
        "hp":    (60,  100),    # 플레이어 HP × 0.35~0.57
        "atk":   (8,   13),     # 플레이어 HP의 5~7% (1번 맞으면 HP 10% 손실)
        "def":   (2,   5),
        "exp":   (25,  55),
        "gold":  (10,  30),
    },
    "normal": {
        "hp":    (120, 200),    # 플레이어 HP × 0.69~1.14
        "atk":   (13,  20),     # 플레이어 HP의 7~11%
        "def":   (4,   9),
        "exp":   (55,  100),
        "gold":  (25,  60),
    },
    "elite": {
        "hp":    (300, 500),
        "atk":   (20,  30),
        "def":   (10,  15),
        "exp":   (200, 400),
        "gold":  (80,  200),
    },
    "boss": {
        "hp":    (1800, 4000),  # 플레이어가 10~25번 공격해야 처치
        "atk":   (30,   45),    # 플레이어 HP의 17~26%
        "def":   (15,   25),
        "exp":   (1000, 3000),
        "gold":  (500,  1500),
    },
}
```

### 전투 시뮬레이션 (검증용)

```python
def simulate_battle(
    player: dict,
    enemy: dict,
    player_skill_dmg: int = 0,
) -> dict:
    """
    단순 턴제 전투 시뮬레이션.
    player/enemy: {"hp", "atk", "def", "spd"}
    반환: {"player_survives", "turns", "player_hp_remaining"}
    """
    php = player["hp"]
    ehp = enemy["hp"]
    turn = 0

    while php > 0 and ehp > 0:
        turn += 1
        # 플레이어 공격 (스킬 or 일반 공격 번갈아)
        if turn % 3 == 0 and player_skill_dmg > 0:
            pdmg = max(1, player_skill_dmg - enemy.get("def", 0))
        else:
            pdmg = max(1, player["atk"] * 2 - enemy.get("def", 0))
        ehp -= pdmg

        if ehp <= 0:
            break

        # 적 공격
        edgm = max(1, enemy["atk"] - player.get("def", 0))
        php -= edgm

    return {
        "player_survives": php > 0,
        "turns": turn,
        "player_hp_remaining": max(0, php),
        "player_hp_ratio": max(0, php) / player["hp"],
    }


def validate_boss_difficulty(player: dict, boss: dict) -> list[str]:
    """보스 전투 난이도 검증."""
    warnings = []
    result = simulate_battle(player, boss, player_skill_dmg=player["atk"] * 3)

    if not result["player_survives"]:
        warnings.append(
            f"[밸런스] 보스가 너무 강함: 플레이어가 {result['turns']}턴 만에 사망"
        )
    elif result["turns"] < 5:
        warnings.append(
            f"[밸런스] 보스가 너무 약함: {result['turns']}턴 만에 클리어 "
            f"(HP 잔여 {result['player_hp_ratio']:.0%})"
        )
    elif result["player_hp_ratio"] > 0.7:
        warnings.append(
            f"[밸런스] 보스 전투가 너무 쉬움: HP {result['player_hp_ratio']:.0%} 남음"
        )

    return warnings
```

---

## 스킬 밸런스

### MP 소비 설계 기준

```
전투당 평균 사용 스킬 수: 3~5회
던전 내 전투 수: 3~5회
→ 전체 던전 MP 소비 예상: 9~25회

전략:
  MP 포션 2~3개 구매 가능한 가격 설정
  보스 전에 MP를 다 썼을 때 포션으로 보충 가능해야 함
```

```python
def recommend_mp_cost(player_mmp: int, skill_type: str) -> dict:
    """스킬 타입별 권장 MP 소비량."""
    return {
        "single_atk":  int(player_mmp * 0.08),  # 8% (자주 사용)
        "aoe_atk":     int(player_mmp * 0.15),  # 15% (전체공격)
        "strong_single": int(player_mmp * 0.20), # 20% (강한 단일)
        "heal_single": int(player_mmp * 0.10),   # 10% (회복)
        "heal_aoe":    int(player_mmp * 0.20),   # 20% (전체회복)
        "buff":        int(player_mmp * 0.05),   # 5% (버프)
    }[skill_type]
```

### 데미지 공식 계수 기준

```python
# scope=1 (단일 공격): 계수 1.5~2.5
"a.atk * 2 - b.def"

# scope=2 (전체 공격): 계수 0.6~1.0 (낮게)
"a.atk * 0.8 - b.def"

# scope=7 (아군 1체 회복): MaxHP의 30~50%
"a.mat * 1.5 + 50"

# 강한 단일 공격 (MP 많이 소비):
"a.atk * 3 - b.def * 0.5"
```

---

## 골드 경제 시스템

### 던전 골드 획득 예상

```
잡몹 1마리: 10~30 골드
일반 1마리: 25~60 골드
던전 전투 5~8회 기준:
→ 총 획득 골드: 200~500 골드
```

### 아이템 가격 사다리

```python
ITEM_PRICE_GUIDE = {
    # HP 회복 (HP의 30~50% 회복)
    "회복 포션 (소)":   {"price": 80,   "hp_ratio": 0.3, "fixed": 20},
    "회복 포션":        {"price": 150,  "hp_ratio": 0.5, "fixed": 30},
    "회복 포션 (대)":   {"price": 300,  "hp_ratio": 0.8, "fixed": 0},
    "엘릭서":           {"price": 800,  "hp_ratio": 1.0, "fixed": 0},  # 전체 회복

    # MP 회복
    "에테르 (소)":      {"price": 60,   "mp_ratio": 0.3},
    "에테르":           {"price": 120,  "mp_ratio": 0.5},
    "에테르 (대)":      {"price": 250,  "mp_ratio": 0.8},

    # 만병통치약
    "만병통치약":       {"price": 500, "note": "HP+MP 동시 30% 회복"},
}

# 가격 정합성 검증
def validate_item_prices(items: list) -> list[str]:
    warnings = []
    for item in items:
        if not item:
            continue
        price = item.get("price", 0)
        # 소모성 아이템이 너무 비싸면 구매 안 함
        if price > 500 and item.get("consumable", True):
            warnings.append(
                f"[경제] {item['name']} 가격({price})이 너무 높아 구매 유인 없음"
            )
        # 너무 싸면 경제 붕괴
        if price < 20 and item.get("itypeId") == 1:
            warnings.append(
                f"[경제] {item['name']} 가격({price})이 너무 낮음"
            )
    return warnings
```

### 상점 구성 기준

```
마을 상점 권장 구성:
  - 회복 포션 (100~150골드): 필수 소모품
  - 에테르 (80~120골드): 마법사/힐러용
  - 초반 무기 (300~600골드): 주인공이 살 수 있는 수준
  - 초반 방어구 (200~400골드): 마을에서 획득 가능한 골드 내

설계 검증:
  - 마을 상점의 최저가 아이템 ≤ 던전 1회 골드 수입
  - 최고가 무기 ≤ 던전 3회 골드 수입
```

---

## 무기/방어구 가격 사다리

```python
WEAPON_PRICE_GUIDE = {
    # ATK 보정량별 권장 가격
    "ATK+5~10":   (150,  400),   # 초반 무기
    "ATK+11~20":  (400,  1000),  # 중반 무기
    "ATK+21~35":  (1000, 2500),  # 후반 무기
    "ATK+36+":    (2500, 8000),  # 최종 무기
}

ARMOR_PRICE_GUIDE = {
    "DEF+3~8":    (100,  300),
    "DEF+9~15":   (300,  800),
    "DEF+16~25":  (800,  2000),
}

def recommend_weapon_price(atk_bonus: int) -> int:
    """ATK 보정량으로 적정 가격 계산."""
    if atk_bonus <= 10:
        return 150 + atk_bonus * 25
    elif atk_bonus <= 20:
        return 400 + (atk_bonus - 10) * 60
    elif atk_bonus <= 35:
        return 1000 + (atk_bonus - 20) * 100
    return 2500 + (atk_bonus - 35) * 200
```

---

## 플레이타임별 콘텐츠 분량

### 5분 게임 기준

```
맵: 3개 (마을 1, 던전 1, 보스 1)
전투 수: 4~6회
레벨업: 3~4회
골드 획득: 150~300
아이템 사용: 2~4개
```

### 7분 게임 기준 (권장)

```
맵: 3~4개 (마을 1, 던전 1~2, 보스 1)
전투 수: 6~10회
레벨업: 5~6회
골드 획득: 300~600
아이템 사용: 4~8개
NPC 대화: 3~5개
```

### 10분 게임 기준

```
맵: 4개 (마을 1, 필드 1, 던전 1, 보스 1)
전투 수: 10~15회
레벨업: 7~9회
골드 획득: 600~1200
아이템 사용: 8~15개
NPC 대화: 5~8개
```

---

## 난이도 곡선 (맵별 적 강도)

```
[마을] → [던전 입구] → [던전 중반] → [보스방]
   0%        100%          150%          400%

weak 적 HP 기준 인덱스:
  마을(이벤트 전투 없음): -
  던전 입구: 60~80 HP     ← 플레이어가 2~3번 공격에 처치
  던전 중반: 80~120 HP    ← 3~5번 공격
  보스방:    2000~4000 HP ← 보스
```

### 적 배치 권장

```python
# 맵 타입별 권장 적 티어 조합
MAP_ENEMY_DISTRIBUTION = {
    "dungeon": {
        "weak":   0.5,   # 50% (초반에 몸 풀기)
        "normal": 0.4,   # 40%
        "elite":  0.1,   # 10% (던전 후반부)
    },
    "boss": {
        "boss":   1.0,   # 100% (보스만)
    },
    "field": {
        "weak":   0.7,
        "normal": 0.3,
    },
}
```

---

## LLM 프롬프트용 밸런스 가이드 (요약본)

에셋 생성 시 LLM에 전달하는 핵심 규칙 (간결 버전):

```
## 밸런스 규칙 (반드시 준수)

플레이어 기준 HP=175, ATK=15, DEF=8 (레벨 1)

적 티어별 HP:
  weak   = 60~100    (플레이어가 2~3번 공격에 처치)
  normal = 120~200   (3~5번)
  elite  = 300~500   (7~10번)
  boss   = 1800~4000 (10~25번 + 아이템 사용 필요)

적 ATK 한계 (플레이어가 한 번 맞을 때 HP 손실 ≤ 15%):
  weak   ATK ≤ 26  (약 15%)
  normal ATK ≤ 35  (약 20%)
  boss   ATK ≤ 50  (약 29%)

스킬 MP 소비:
  단일 공격: 플레이어 MMP의 8~15%
  전체 공격: 플레이어 MMP의 15~25%
  회복:      플레이어 MMP의 8~15%

아이템 가격:
  회복 포션: 100~200골드 (던전 1회 골드 수입의 30~50%)
  무기(초반): 300~600골드 (던전 2회 수입 내)

EXP 설계 (레벨 5 도달에 던전 전투 6~10회):
  weak EXP:   25~55
  normal EXP: 55~100
  boss EXP:   1000~3000
```

---

## 검증기에서 실행할 밸런스 체크

```python
# agent/generation/nodes/generation_validator.py 추가

def check_full_balance(assets: dict, spec: GameSpec) -> list[str]:
    """전체 밸런스 검증."""
    warnings = []

    # 1. 스탯 범위 검사
    warnings += _check_enemy_stats(assets)

    # 2. 전투 시뮬레이션
    warnings += _check_boss_difficulty(assets)

    # 3. 경제 검증
    warnings += _check_economy(assets)

    # 4. EXP 곡선 검증
    warnings += _check_exp_curve(assets, spec)

    return warnings


def _check_exp_curve(assets: dict, spec: GameSpec) -> list[str]:
    """레벨 5 도달에 필요한 전투 수가 적절한지 확인."""
    warnings = []
    enemies = [e for e in assets.get("Enemies.json", []) if e]
    if not enemies:
        return warnings

    avg_exp = sum(e.get("exp", 0) for e in enemies) / len(enemies)
    # 레벨 5까지 필요 EXP ≈ 280 (표준 expParams)
    needed_fights = 280 / avg_exp if avg_exp > 0 else float("inf")

    if needed_fights < 3:
        warnings.append(
            f"[경제] 레벨업이 너무 빠름: 전투 {needed_fights:.1f}회로 레벨 5 도달 "
            f"(적 평균 EXP={avg_exp:.0f})"
        )
    elif needed_fights > 20:
        warnings.append(
            f"[경제] 레벨업이 너무 느림: 전투 {needed_fights:.1f}회 필요 "
            f"(적 평균 EXP={avg_exp:.0f})"
        )

    return warnings
```

---

## 참고 링크

- 전체 생성 계획: `docs/The_world/full_generation_plan.md`
- 리스크 R7 (밸런스 검증): `docs/The_world/risks_and_mitigations.md#r7`
- 에셋 생성 상세: `docs/The_world/asset_generation.md`
- RPG Maker 스키마 제약: `docs/The_world/rpgmaker_constraints.md`
