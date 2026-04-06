# Classes.json 생성 — LLM + 알고리즘 분리 패턴

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06
> 관련 문서: asset_generation.md, balance_and_economy.md, llm_structured_output.md

---

## 문제: LLM이 792개 숫자를 못 만든다

RPG Maker MZ의 `Classes.json`에서 `params` 필드는 **2D 배열**이다:

```json
"params": [
  [150, 155, ...],   // MHP lv1~99 (99개)
  [60,  63,  ...],   // MMP
  [12,  13,  ...],   // ATK
  [6,   7,   ...],   // DEF
  [8,   9,   ...],   // MAT
  [6,   7,   ...],   // MDF
  [8,   9,   ...],   // AGI
  [8,   9,   ...]    // LUK
]
```

8개 스탯 × 99레벨 = **792개 정수**.
Solar Pro 2에게 이 배열을 생성하도록 요청하면:
- 토큰 낭비 (792개 숫자 = ~3000 토큰)
- 배열 길이 오류 (97개, 100개 등 불안정)
- function_calling 스키마 제약 (Solar Pro 2는 복잡한 nested list 불안정)

---

## 해결: LLM은 "개념", 알고리즘은 "숫자"

```
generate_classes(spec, id_table)
    │
    ├── LLM (structured_output=LlmClassList)
    │   └── 각 직업별: name, description, expParams, traits, skillTypes
    │
    └── 알고리즘: _build_params_2d(class_role)
        └── generate_class_params() × 8 스탯
            └── Classes.json params 2D 배열 완성
```

---

## LLM 출력 스키마 (Solar Pro 2 호환)

Solar Pro 2 제약: ≤12 필드, ≤2 중첩 레벨.
`params` 배열은 **스키마에서 제외**.

```python
# agent/generation/nodes/asset_generator.py

class LlmLearning(BaseModel):
    """스킬 습득 항목 (level + skillId)."""
    level: int       # 습득 레벨 (1~99)
    skillId: int     # 스킬 ID (id_table.skills에서 확정)

class LlmClass(BaseModel):
    """LLM이 생성하는 직업 데이터 (params 제외)."""
    id: int
    name: str                        # 직업명 (예: "전사")
    expParams: list[int]             # 경험치 곡선 파라미터 [basis, extra, acc_a, acc_b]
    learnings: list[LlmLearning]     # 스킬 습득 목록 (level + skillId)
    note: str = ""

class LlmClassList(BaseModel):
    """structured_output 루트 타입."""
    classes: list[LlmClass]

# ※ 중첩 레벨: LlmClassList → list[LlmClass] → list[LlmLearning] → 필드
#   Solar Pro 2 제약(≤2 중첩)에서 LlmLearning은 플랫 필드이므로 안전.
# ※ 기존 agent/schemas/classes.py의 Class 모델에는 description 필드가 없음.
#   LlmClass에서 description을 제거하고 note만 사용.
```

**`expParams` 가이드라인** (LLM 프롬프트에 포함):
- 일반 직업: `[30, 20, 30, 30]`
- 성장이 느린 마법사: `[30, 20, 15, 30]`
- 빠른 성장: `[30, 20, 40, 30]`

---

## 알고리즘: `_build_params_2d(role)`

```python
# agent/generation/nodes/asset_generator.py

# 역할별 lv1/lv99 기준값 (balance_and_economy.md 기반)
CLASS_STAT_TEMPLATE: dict[str, dict[str, tuple[int, int]]] = {
    "warrior": {
        "mhp": (180, 2500), "mmp": (60, 800),
        "atk": (18, 280),   "def": (10, 150),
        "mat": (8,  135),   "mdf": (8,  110),  # MAT: balance_and_economy 기준 150-250에서 전사 -10% 적용 = 135~225
        "agi": (9,  110),   "luk": (8,  80),
    },
    "mage": {
        "mhp": (130, 1600), "mmp": (100, 1400),
        "atk": (10, 140),   "def": (6,  90),
        "mat": (18, 280),   "mdf": (12, 160),
        "agi": (10, 120),   "luk": (9,  90),
    },
    "healer": {
        "mhp": (150, 2000), "mmp": (90, 1200),
        "atk": (10, 150),   "def": (8,  120),
        "mat": (14, 200),   "mdf": (14, 200),
        "agi": (9,  110),   "luk": (10, 100),
    },
    "thief": {
        "mhp": (140, 1800), "mmp": (50, 700),
        "atk": (15, 220),   "def": (7,  110),
        "mat": (8,  100),   "mdf": (8,  100),
        "agi": (18, 280),   "luk": (15, 200),
    },
    "default": {   # 알 수 없는 역할
        "mhp": (150, 2000), "mmp": (70, 1000),
        "atk": (14, 200),   "def": (8,  120),
        "mat": (12, 160),   "mdf": (8,  120),
        "agi": (10, 140),   "luk": (9,  90),
    },
}

STAT_ORDER = ["mhp", "mmp", "atk", "def", "mat", "mdf", "agi", "luk"]

def _build_params_2d(role: str) -> list[list[int]]:
    """
    8 × 99 params 2D 배열 생성.
    역할(role)에 따라 lv1/lv99 값 결정, generate_class_params()로 채움.
    """
    template = CLASS_STAT_TEMPLATE.get(role, CLASS_STAT_TEMPLATE["default"])
    params_2d = []
    for stat in STAT_ORDER:
        lv1, lv99 = template[stat]
        growth = "accelerate" if stat in ("mhp", "mmp") else "linear"
        params_2d.append(generate_class_params(lv1, lv99, growth=growth))
    return params_2d  # shape: [8][99]
```

---

## `generate_classes()` 전체 흐름

```python
async def generate_classes(
    spec: GameSpec,
    id_table: IdTable,
) -> list[dict]:
    """
    Classes.json 배열 생성.
    반환: RPG Maker MZ 형식 리스트 (index 0 = null).
    """
    # 1. 직업 목록 + 역할 추출 (GameSpec.characters에서)
    class_roles: dict[str, str] = {}  # class_name → role
    for char in spec.characters:
        class_roles.setdefault(char.class_name, char.role)

    class_names = list(id_table.classes.keys())  # asset_planner 확정 순서

    # 2. LLM: 이름/설명/expParams/스킬 습득 생성
    messages = _build_classes_prompt(spec, id_table, class_names)
    llm_result = cast(LlmClassList, await invoke_llm(messages, structured_output=LlmClassList))

    # 3. LLM 결과 → id_table 순서로 재정렬
    llm_by_name = {cls.name: cls for cls in llm_result.classes}

    # 4. params 2D 배열 알고리즘으로 생성 + 합성
    output: list[dict | None] = [None]  # index 0 = null
    for class_name in class_names:
        cid = id_table.classes[class_name]
        role = class_roles.get(class_name, "default")

        llm_cls = llm_by_name.get(class_name)
        if llm_cls is None:
            # LLM이 누락한 경우 폴백
            logger.warning("LLM이 직업 '%s'를 생성하지 않음, 기본값 사용", class_name)
            llm_cls = LlmClass(id=cid, name=class_name,
                               expParams=[30, 20, 30, 30], learnings=[])

        # learnings: LlmLearning → dict 변환
        learnings = [{"level": l.level, "skillId": l.skillId, "note": ""}
                     for l in llm_cls.learnings]

        # ※ 기존 Class 스키마(agent/schemas/classes.py)에 맞춰 필드 구성:
        #   id, name, note, expParams, params, learnings, traits (description/meta 없음)
        rpg_class = {
            "id": cid,
            "name": class_name,
            "expParams": _validate_exp_params(llm_cls.expParams),
            "params": _build_params_2d(role),  # ← 알고리즘 생성, list[list[int]] 8×99
            "learnings": learnings,
            "traits": [],
            "note": llm_cls.note,
        }
        output.append(rpg_class)

    return output
```

---

## 역할 → 클래스 역할 매핑

`GameSpec.characters[].role`은 LLM이 자유 텍스트로 생성한다.
역할 정규화 함수:

```python
def _normalize_role(raw_role: str) -> str:
    """
    LLM이 '근접 전투', '전사', 'warrior' 등 다양하게 생성하므로 정규화.
    """
    role_lower = raw_role.lower()
    if any(k in role_lower for k in ["warrior", "전사", "근접", "검사", "기사"]):
        return "warrior"
    if any(k in role_lower for k in ["mage", "마법사", "마도사", "wizard"]):
        return "mage"
    if any(k in role_lower for k in ["healer", "힐러", "성직자", "치유", "priest"]):
        return "healer"
    if any(k in role_lower for k in ["thief", "도적", "ninja", "닌자", "rogue"]):
        return "thief"
    return "default"
```

---

## Classes.json 최종 구조 (RPG Maker MZ)

```json
[
  null,
  {
    "id": 1,
    "name": "전사",
    "description": "강인한 체력의 근접 전투 전문가",
    "expParams": [30, 20, 30, 30],
    "params": [
      [180, 184, ..., 2500],  // MHP lv1~99
      [60,  61,  ...,  800],  // MMP
      ...                      // ATK, DEF, MAT, MDF, AGI, LUK
    ],
    "learnings": [
      {"level": 1, "skillId": 1},
      {"level": 5, "skillId": 3}
    ],
    "traits": [],
    "note": "",
    "meta": {}
  }
]
```

---

## 리스크

### R-C1: LLM이 직업 누락 (P2)

LLM이 클래스 목록 일부를 생성하지 않는 경우.

**완화**: `llm_by_name.get(class_name)` 누락 시 기본값으로 폴백 + 경고 로그.

### R-C2: expParams 범위 오류 (P2)

LLM이 `expParams`를 `[30, 20, 30, 30]` 대신 `[30, 20, 300, 30]`처럼 비정상 값 생성.

**완화**:
```python
def _validate_exp_params(ep: list[int]) -> list[int]:
    if len(ep) != 4:
        return [30, 20, 30, 30]
    # RPG Maker MZ 기본값 범위: basis=10~50, extra=10~40, acc_a=15~50, acc_b=20~50
    clipped = [
        max(10, min(50, ep[0])),
        max(10, min(40, ep[1])),
        max(15, min(50, ep[2])),
        max(20, min(50, ep[3])),
    ]
    return clipped
```

### R-C3: params 2D 배열 길이 오류 (P1)

`generate_class_params()`가 99개 미만/초과 반환 시 RPG Maker MZ가 로드 오류.

**완화**: 생성 후 어설션:
```python
assert len(row) == 99, f"params row length error: {len(row)}"
```

### R-C5: `LlmLearning.skillId`가 id_table에 없는 경우 (P2)

LLM이 존재하지 않는 skillId를 생성하면 RPG Maker MZ에서 스킬 습득 항목이 비어보임.

**완화**: `learnings` 구성 시 id_table.skills에 해당 ID가 있는지 확인:
```python
valid_ids = set(id_table.skills.values())
learnings = [
    {"level": l.level, "skillId": l.skillId, "note": ""}
    for l in llm_cls.learnings
    if l.skillId in valid_ids  # 유효하지 않은 ID 제거
]
```

### R-C4: 역할 정규화 실패 → 잘못된 스탯 (P2)

LLM이 알 수 없는 역할 문자열 생성 → `_normalize_role()` → `"default"` 폴백.
플레이어에게는 영향 없지만 밸런스가 의도와 다를 수 있음.

**완화**: asset_generator 통합 테스트에서 역할별 스탯 범위 검증.

---

## 테스트

```python
# agent/tests/generation/test_classes.py

def test_build_params_2d_warrior():
    params = _build_params_2d("warrior")
    assert len(params) == 8          # 8 스탯
    assert len(params[0]) == 99      # 99 레벨
    assert params[0][0] == 180       # MHP lv1
    assert params[0][98] == 2500     # MHP lv99

def test_build_params_2d_unknown_role():
    """알 수 없는 역할은 default 템플릿 사용."""
    params = _build_params_2d("unknown_xyz")
    assert len(params) == 8

def test_validate_exp_params_clips_out_of_range():
    result = _validate_exp_params([30, 20, 999, 30])
    assert result[2] == 50  # acc_a 클리핑

def test_generate_classes_result_format(mock_invoke_llm):
    """generate_classes() 반환값 첫 요소 null, 이후 id 연속."""
    result = # ... (monkeypatched LLM)
    assert result[0] is None
    assert result[1]["id"] == 1
    assert len(result[1]["params"]) == 8
    assert len(result[1]["params"][0]) == 99
```
