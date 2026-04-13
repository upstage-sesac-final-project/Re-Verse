# LLM 구조화 출력 가이드 — Full Generation

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06

---

## 핵심 원칙

**`_extract_json(raw)` 방식을 사용하지 않는다.**

이전 설계 문서(sprint_plan.md, prompt_engineering.md 등)의 일부 의사코드에서
`raw = await invoke_llm(prompt); data = _extract_json(raw)` 패턴을 사용했지만,
이는 실제 코드베이스 패턴과 다르다.

**실제 코드베이스의 표준 패턴**:
```python
result = cast(GameSpec, await invoke_llm(messages, structured_output=GameSpec))
```

`invoke_llm(structured_output=Pydantic모델)`은 내부적으로
`llm.with_structured_output(모델, method="function_calling")`을 호출하며
직접 Pydantic 인스턴스를 반환한다.

---

## `invoke_llm` 시그니처

```python
# agent/core/llm_client.py

async def invoke_llm(
    messages: list[BaseMessage],
    structured_output: type[BaseModel] | None = None,
) -> str | BaseModel:
    """
    structured_output 미지정 → str 반환 (synthesizer 등 자유 텍스트 생성 시)
    structured_output 지정   → 해당 Pydantic 인스턴스 반환
    """
```

---

## Full Generation 노드별 사용 패턴

### A. 기획자 (game_designer.py)

```python
from typing import cast
from langchain_core.messages import HumanMessage, SystemMessage
from agent.core.llm_client import invoke_llm
from agent.generation.state import GenerationState

# GameSpec은 Pydantic BaseModel
from agent.generation.models import GameSpec

async def run_game_designer(state: GenerationState) -> dict:
    messages = [
        SystemMessage(content=GAME_DESIGNER_SYSTEM_PROMPT),
        HumanMessage(content=f"사용자 요청: {state['user_input']}"),
    ]
    # structured_output → invoke_llm이 GameSpec 인스턴스 직접 반환
    spec = cast(GameSpec, await invoke_llm(messages, structured_output=GameSpec))
    return {"game_spec": spec}
```

> **주의**: `cast()`는 mypy 타입 힌트용이다. 런타임에 아무것도 하지 않는다.
> `invoke_llm`이 `None`을 반환하면 내부에서 `ValueError`를 이미 raise한다.

### C. 에셋 생성 (asset_generator.py)

에셋 타입별로 서로 다른 Pydantic 스키마를 사용한다:

```python
ASSET_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "actors":   ActorListOutput,
    "classes":  ClassListOutput,
    "skills":   SkillListOutput,
    "items":    ItemListOutput,
    "weapons":  WeaponListOutput,
    "armors":   ArmorListOutput,
    "enemies":  EnemyListOutput,
}

async def _generate_asset(asset_type: str, ...) -> list[dict]:
    schema = ASSET_OUTPUT_SCHEMAS[asset_type]
    messages = build_asset_messages(asset_type, ...)
    result = cast(schema, await invoke_llm(messages, structured_output=schema))
    # result는 schema 인스턴스; .items 또는 .data 등 래퍼 필드를 통해 접근
    return [item.model_dump() for item in result.items]
```

> **래퍼 모델 필요**: `with_structured_output`은 최상위 객체 하나를 반환한다.
> 따라서 리스트를 직접 반환할 수 없고, 래퍼 모델이 필요하다:
> ```python
> class SkillListOutput(BaseModel):
>     items: list[RpgSkill]
> ```

### F. 이벤트 기획자 (event_planner.py)

이벤트 기획자만은 **structured_output을 사용하지 않는다** — YAML DSL은
function_calling 스키마로 표현하기 어렵고, 맵당 이벤트 수가 가변적이어서
스키마 크기를 예측할 수 없기 때문이다.

대신 **자유 텍스트 + YAML 파싱** 방식:
```python
raw: str = cast(str, await invoke_llm(messages))  # structured_output 미지정
dsl_list = _parse_yaml_dsl(raw)                   # YAML 섹션 추출 후 파싱
```

이 경우만 예외적으로 `_extract_yaml()` 패턴을 사용한다.

---

## Solar Pro 2 Function Calling 제약

### 알려진 문제

| 증상 | 원인 | 대응 |
|------|------|------|
| `None` 반환 | 스키마가 너무 복잡함 | 스키마 단순화 또는 분할 |
| `ValidationError` | LLM이 필드를 누락 | `Optional` + 기본값 추가 |
| 타임아웃 | 대형 스키마 처리 시간 초과 | 병렬화 또는 스키마 분할 |
| 한국어 필드값에 영어 혼입 | 언어 드리프트 | system prompt에 언어 규칙 명시 |

### 스키마 복잡도 가이드라인

**Safe** (함수 호출 안정):
```python
class RpgSkill(BaseModel):
    id: int
    name: str
    description: str
    mpCost: int
    scope: int              # 0~14
    occasion: int           # 0~3
    damage_type: int = 0
    damage_formula: str = ""
```

**Risky** (함수 호출 불안정):
```python
class RpgSkill(BaseModel):
    id: int
    name: str
    description: str
    mpCost: int
    scope: int
    damage: RpgSkillDamage  # 중첩 모델
    effects: list[RpgEffect]  # 가변 길이 중첩 리스트
    note: str
    # ... 20개 이상 필드
```

**규칙**: 최상위 필드 수 ≤ 12, 중첩 깊이 ≤ 2, 중첩 리스트는 최소화.

### 스키마 설계 원칙

```python
# 나쁜 예: 깊은 중첩
class RpgEnemyAction(BaseModel):
    skillId: int
    rating: int
    conditionType: int
    conditionParam1: int
    conditionParam2: int

class RpgEnemy(BaseModel):
    id: int
    name: str
    params: list[int]
    actions: list[RpgEnemyAction]  # 중첩 객체 리스트
    dropItems: list[RpgDropItem]   # 또 다른 중첩

# 좋은 예: 플랫화 + 제약 명시
class RpgEnemyForGeneration(BaseModel):
    """LLM 생성용 적 스키마 (내부 구조 단순화)."""
    id: int
    name: str
    hp: int              # params[0]으로 변환
    mp: int = 0          # params[1]
    atk: int             # params[2]
    def_stat: int        # params[3]  (def는 Python 예약어)
    exp: int
    gold: int
    drop_item_id: int = 0  # 단일 아이템만 (dropItems[0])
    skill_ids: list[int]   # actions로 변환
```

Integrator/Validator가 이를 RPG Maker MZ 형식으로 변환:
```python
def _convert_enemy_to_rpgmaker(e: RpgEnemyForGeneration) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "params": [e.hp, e.mp, e.atk, e.def_stat, 0, 0, 10, 10],
        "dropItems": [
            {"kind": 1 if e.drop_item_id else 0, "dataId": e.drop_item_id, "denominator": 10},
            {"kind": 0, "dataId": 0, "denominator": 1},
            {"kind": 0, "dataId": 0, "denominator": 1},
        ],
        "actions": [{"skillId": sid, "rating": 5, "conditionType": 0, ...}
                    for sid in e.skill_ids],
    }
```

---

## 재시도 전략

### 구조화 출력 재시도

```python
async def invoke_with_retry(
    messages: list[BaseMessage],
    schema: type[BaseModel],
    max_attempts: int = 3,
) -> BaseModel:
    """구조화 출력 실패 시 단순화된 프롬프트로 재시도."""
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            result = await invoke_llm(messages, structured_output=schema)
            if result is None:
                raise ValueError(f"{schema.__name__} 반환값이 None")
            return result
        except (ValueError, ValidationError) as e:
            last_error = e
            if attempt < max_attempts - 1:
                # 재시도 시 오류 컨텍스트 추가
                error_msg = f"\n\n이전 시도 실패: {e}\n규칙을 다시 확인하고 정확히 응답해주세요."
                messages = messages[:-1] + [
                    HumanMessage(content=messages[-1].content + error_msg)
                ]
    raise RuntimeError(f"{schema.__name__} 생성 {max_attempts}회 실패: {last_error}")
```

### 이벤트 기획자 YAML 재시도

```python
async def _plan_single_map_with_retry(
    spec: MapSpec, id_table: IdTable, ...
) -> list:
    errors: list[str] = []
    for attempt in range(3):
        raw: str = cast(str, await invoke_llm(build_event_messages(..., errors)))
        try:
            dsl = _extract_yaml_blocks(raw)
            validated = [DslEvent.model_validate(e) for e in dsl]
            # 좌표/이름 참조 검증
            coord_errors = _validate_coords(validated, spec)
            name_errors  = _validate_name_refs(validated, id_table)
            if not coord_errors and not name_errors:
                return [e.model_dump() for e in validated]
            errors = coord_errors + name_errors
        except (ValidationError, yaml.YAMLError) as e:
            errors = [str(e)]
    # 3회 모두 실패 → 안전한 폴백
    return _build_fallback_events(spec, ...)
```

---

## 모의 LLM 픽스처 (테스트용)

테스트에서 실제 LLM을 호출하지 않으려면 `invoke_llm`을 모킹한다:

```python
# agent/tests/generation/conftest.py

import pytest
from unittest.mock import AsyncMock, patch
from agent.generation.models import GameSpec, CharacterSpec, EnemySpec, MapSpec

MOCK_GAME_SPEC = GameSpec(
    title="테스트 게임",
    theme="판타지",
    playtime_minutes=7,
    story={"synopsis": "테스트 스토리", "acts": ["시작", "중반", "결말"]},
    characters=[
        CharacterSpec(name="해럴드", class_name="전사", role="주인공", personality="용감함"),
        CharacterSpec(name="세라",   class_name="마법사", role="서포터", personality="지혜로움"),
    ],
    enemies=[
        EnemySpec(name="슬라임",  tier="weak",   location="숲"),
        EnemySpec(name="고블린",  tier="normal", location="던전"),
        EnemySpec(name="드래곤",  tier="boss",   location="보스 방"),
    ],
    maps=[
        MapSpec(name="출발 마을", type="town",    description="시작 지점", connects_to=["어둠의 숲"]),
        MapSpec(name="어둠의 숲",  type="dungeon", description="중간 지대", connects_to=["출발 마을", "드래곤 소굴"]),
        MapSpec(name="드래곤 소굴", type="boss",   description="최종 보스", connects_to=["어둠의 숲"]),
    ],
    key_items=["영웅의 검", "치유의 포션"],
)

@pytest.fixture
def mock_llm(monkeypatch):
    """invoke_llm을 모킹하여 스키마에 따라 적절한 픽스처 반환."""
    async def _fake_invoke_llm(messages, structured_output=None):
        if structured_output is GameSpec:
            return MOCK_GAME_SPEC
        if structured_output is not None:
            # 스키마 이름으로 적절한 픽스처 선택
            fixture = MOCK_FIXTURES.get(structured_output.__name__)
            if fixture:
                return fixture
            raise ValueError(f"Mock fixture 없음: {structured_output.__name__}")
        return "모의 텍스트 응답"  # 자유 텍스트 (event_planner 등)

    monkeypatch.setattr("agent.generation.nodes.game_designer.invoke_llm", _fake_invoke_llm)
    monkeypatch.setattr("agent.generation.nodes.asset_generator.invoke_llm", _fake_invoke_llm)
    monkeypatch.setattr("agent.generation.nodes.event_planner.invoke_llm", _fake_invoke_llm)
```

> **패턴**: `monkeypatch.setattr`로 각 노드 모듈의 `invoke_llm`을 교체.
> `agent.core.llm_client.invoke_llm`을 교체하지 않는 이유:
> 싱글톤 패치 시 다른 테스트에 영향을 미칠 수 있음.

---

## 토큰 계산 및 컨텍스트 예산

Solar Pro 2의 컨텍스트 창은 **32K 토큰** (2026년 4월 기준).

| 노드 | System | User | 출력 스키마 크기 | 합계 추정 |
|------|--------|------|----------------|---------|
| game_designer | ~400 | ~100 | GameSpec ~200 | ~700 |
| asset_generator (skills) | ~500 | ~300 | SkillListOutput ~400 | ~1,200 |
| asset_generator (enemies) | ~500 | ~400 | EnemyListOutput ~600 | ~1,500 |
| map_designer | ~600 | ~200 | MapSpecListOutput ~300 | ~1,100 |
| event_planner (맵당) | ~800 | ~500 | — (자유 텍스트) | ~1,300 |

**스키마 크기 주의**: `with_structured_output`은 스키마를 JSON Schema로 직렬화하여
function calling definitions에 추가한다. 복잡한 스키마일수록 토큰을 소비한다.

`SkillListOutput`에 스킬 15개 × 필드 8개 = 예상 출력 ~600 토큰.
스키마 정의 ~400 토큰 포함 시 총 입력 ~1,600 토큰.

---

## 기존 문서와의 불일치 수정 노트

다음 문서의 의사코드는 `_extract_json(raw)` 패턴을 사용하고 있으나,
실제 구현 시 이 문서의 `invoke_llm(structured_output=...)` 패턴을 따른다:

| 문서 | 수정 필요 부분 |
|------|-------------|
| sprint_plan.md Sprint 2 | `game_designer.py`의 `_parse_game_spec(raw)` → `cast(GameSpec, await invoke_llm(..., structured_output=GameSpec))` |
| sprint_plan.md Sprint 2 | `asset_generator.py`의 `_extract_json(raw)` → `cast(schema, await invoke_llm(..., structured_output=schema))` |
| prompt_engineering.md | `_extract_json()` 유틸리티 → 불필요, 삭제 |
| asset_generation.md | `generate_with_retry()` 내부 JSON 추출 → `invoke_with_retry()` |

> 이 수정은 실제 구현 시 코드에서 직접 반영한다.
> 설계 문서는 의사코드이므로 파일 수정 없이 이 문서를 참조 기준으로 삼는다.

---

## 요약: Do / Don't

| 하면 안 되는 것 | 대신 해야 하는 것 |
|----------------|-----------------|
| `raw = await invoke_llm(messages)` → `json.loads(raw)` | `cast(Schema, await invoke_llm(messages, structured_output=Schema))` |
| `raw.split("```json")[1]` | 불필요 — structured_output이 처리 |
| 20개 이상 필드의 복잡한 스키마 | 12개 이하로 제한, 필요시 분할 |
| 중첩 BaseModel 3단계 이상 | 최대 2단계, 또는 플랫화 |
| event_planner에 structured_output 적용 | 자유 텍스트 + `_extract_yaml_blocks()` |
| 실패 시 바로 예외 전파 | `invoke_with_retry()` 3회 시도 후 폴백 |
