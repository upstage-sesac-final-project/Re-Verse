# Reader

Reader는 `게임_요소_조회` intent에 대한 빠른 처리 경로다.
기존 workflow의 definition → planner → executor → validator → synthesizer 5단계를 건너뛰고,
기본적으로 LLM 1회 + 직접 파일 읽기로 조회 결과를 즉시 반환한다.
필요한 경우에만 entity_type 추정, semantic name matching fallback을 위해 LLM을 추가 호출한다.

## 파일 구성

```
agent/graph/nodes/reader.py      # 노드 함수 본체
agent/prompts/reader_prompt.py   # 프롬프트 빌더 (다른 노드들과 동일한 구조)
agent/tests/test_reader.py       # 인터랙티브 smoke 스크립트
```

## 역할

- LLM 1회로 사용자 쿼리를 구조화된 조회 의도로 변환한다.
- 변환된 의도를 기반으로 게임 JSON 파일을 직접 읽고 결과를 rule-based 템플릿으로 포맷해서 `final_response`로 반환한다.

LLM은 쿼리 이해, entity_type 분류 fallback, semantic name matching fallback에만 사용한다.
파일 읽기, 직접 매칭, 대부분의 응답 포맷은 rule-based다.
파일을 수정하지 않으므로 snapshot, backup, validation이 필요 없다.

**entity_name은 Step 1에서 사용자 입력 그대로 파싱한다.** 게임 데이터가 한국어로 저장돼 있으므로 영문 변환을 하지 않는다.
직접 매칭은 reader.py의 `_find_candidates()`가 담당하고, 실패 시 `_apply_semantic_name_match()`가 의미론적 fallback을 한 번 더 시도한다.

## 입력

Reader는 state에서 아래 값을 읽는다.

- `user_input`
- `game_id`

## 출력

Reader는 아래 필드만 반환한다.

- `final_response`

## 노드 함수 구조

다른 노드들과 동일한 패턴을 따른다.

```python
"""Reader 노드 — 게임_요소_조회 빠른 처리 경로."""

import logging
import time
from difflib import SequenceMatcher
from typing import Literal, cast

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.reader_prompt import (
    build_entity_name_match_prompt,
    build_entity_type_guess_prompt,
    build_prompt,
)
from agent.utils.game_data_io import CATEGORY_TO_PLURAL, read_game_json

logger = logging.getLogger(__name__)


async def reader(state: AgentState) -> dict:
    _t0 = time.perf_counter()
    logger.info("─── 📖 Reader START ────────────────────────────────")
    logger.info("  input : %r", state.get("user_input"))
    logger.info("  game  : %s", state.get("game_id"))

    messages = build_prompt(state)
    ...
    response = ...
    return _finish_reader(_t0, response)
```

에러가 발생하면 exception을 밖으로 던지지 않고 `final_response`에 안내 메시지를 담아 반환한다. 이는 다른 모든 노드의 공통 규칙이다.

## 쿼리 스키마 (_ReaderQuery)

`reader.py` 내부에 private 클래스로 선언한다. 다른 노드들의 `_RouterOutput`, `_PlannerOutput` 등과 동일한 위치 규칙이다.

```python
class _ReaderQuery(BaseModel):
    reasoning: str
    query_type: Literal["single_entity", "field_value", "bulk_list", "existence", "aggregate"]
    entity_type: str | None   # 카테고리 (영문 단수형). 예: "enemy", "item", "actor"
    entity_name: str | None   # 사용자 입력 그대로. 영문 변환하지 않음.
                              # 예: "고블린" → "고블린", "엑스칼리버" → "엑스칼리버"
                              # bulk_list / aggregate 전체 대상이면 None
    field_name: str | None    # 조회할 JSON 필드명 (영문). 예: "maxHp", "atk", "price"
                              # single_entity / bulk_list / existence 에서는 None
    filters: dict | None      # 역방향 참조 필터. 예: {"classId": "마법사"}, {"effects": "독"}
    sort: str | None          # 정렬 기준 필드명. ranked_list 패턴을 별도 타입 없이 흡수
    limit: int | None         # 반환 최대 개수
    aggregate_fn: Literal["count", "min", "max", "avg", "sum"] | None
```

LLM 호출은 router, planner와 동일하게 `invoke_llm(messages, structured_output=_ReaderQuery)` 패턴을 쓴다.

```python
try:
    result = cast(_ReaderQuery, await invoke_llm(messages, structured_output=_ReaderQuery))
    logger.info("  query_type=%s entity_type=%s entity_name=%s", ...)
except Exception as e:
    logger.error("[Reader] LLM 호출 실패: %s", e, exc_info=True)
    return {"final_response": "요청을 이해하지 못했습니다. 다시 입력해주세요."}
```

## query_type 정의

| query_type | 의미 | 예시 |
|---|---|---|
| `single_entity` | 특정 엔티티 전체 정보 | "페가수스 정보 알려줘", "드래곤 나이트 스탯 전부 보여줘" |
| `field_value` | 특정 엔티티의 특정 속성 하나 | "페가수스 HP가 얼마야?", "포션 가격 알려줘" |
| `bulk_list` | 카테고리 전체 또는 조건 결과 목록 | "아이템 목록 보여줘", "모든 무기 이름 알려줘" |
| `existence` | 존재 여부 (예/아니오) | "드래곤이라는 적 있어?", "치유의 물약 있어?" |
| `aggregate` | 집계 (count / min / max / avg / sum) | "적이 몇 마리야?", "가장 강한 무기 뭐야?" |

`bulk_list`는 definition 노드의 bulk 처리와 네이밍을 맞춘 것이다.
`sort` + `limit` 슬롯으로 "HP 높은 적 상위 3개" 같은 ranked_list 패턴을 별도 타입 없이 흡수한다.

## 프롬프트 구조 (reader_prompt.py)

`reader_prompt.py`는 세 종류의 프롬프트를 가진다.
- Step 1 구조화용: `_SYSTEM` + `build_prompt(state)`
- Step 3b entity_type fallback용: `_ENTITY_TYPE_GUESS_SYSTEM` + `build_entity_type_guess_prompt(entity_name)`
- Step 3c semantic name match fallback용: `_ENTITY_NAME_MATCH_SYSTEM` + `build_entity_name_match_prompt(query_name, available_names)`

```python
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from agent.graph.state import AgentState

def _build_messages(system_content: str, human_content: str) -> list[BaseMessage]:
    return [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]

def build_prompt(state: AgentState) -> list[BaseMessage]: ...
def build_entity_type_guess_prompt(entity_name: str) -> list[BaseMessage]: ...
def build_entity_name_match_prompt(query_name: str, available_names: list[str]) -> list[BaseMessage]: ...
```

프롬프트에서 반드시 명시해야 하는 내용:
- `entity_name`은 사용자 입력 그대로 반환한다. 영문 변환하지 않는다.
- `field_name`은 영문 JSON 필드명으로 반환한다 (예: "HP" → "maxHp", "공격력" → "atk")
- `entity_type`은 영문 단수형으로 반환한다 (예: "적" → "enemy", "아이템" → "item")
- "누구누구 있어?", "뭐가 있어?" 형태는 bulk_list로 분류한다 (entity_name=null)
- 게임 제목 등 시스템 설정 조회는 entity_type=system으로 분류한다

## 파일 읽기

`agent/utils/game_data_io.read_game_json(game_id, file_name)` 을 직접 재사용한다.
`CATEGORY_TO_PLURAL`도 `game_data_io`에 이미 정의돼 있으므로 재정의하지 않는다.

```python
from agent.utils.game_data_io import read_game_json, CATEGORY_TO_PLURAL

# entity_type → 파일명 변환
file_name = CATEGORY_TO_PLURAL[entity_type] + ".json"
data = read_game_json(game_id, file_name)  # None이면 파일 없음
```

snapshot을 만들지 않고 원본 게임 JSON을 바로 읽는다.

## 매칭 결과 상태 (resolution_status)

`ambiguous_lookup`을 query_type으로 두지 않고, 엔티티 매칭 결과를 내부 분기로 처리한다.
코드에 별도 `ResolutionStatus` 타입을 선언하지는 않지만, 동작상 아래 세 상태로 나뉜다.

| resolution_status | 조건 | 처리 |
|---|---|---|
| `matched` | 후보가 정확히 1개 | 정상 조회 진행 |
| `ambiguous` | 유사 후보가 2개 이상 | 후보 목록을 나열하고 명확화 요청 |
| `not_found` | 후보가 0개 | 없다고 안내 + 유사 이름 제안 (있으면) |

엔티티명 매칭은 아래 우선순위로 수행한다.

0. **ID 숫자 직접 접근** — entity_name이 숫자면 `item["id"]`와 비교 (예: "7번 아이템" → id=7)
1. **exact match** — 대소문자 구분 완전 일치
2. **case-insensitive exact** — 대소문자 무시 일치
3. **prefix match** — `entity_name`으로 시작하는 이름 전부
4. **fuzzy match** — SequenceMatcher 기반 유사도 매칭
5. **semantic name match fallback** — 직접 매칭 결과가 없을 때 `_guess_entity_name()`으로 의미론적 보정

fuzzy threshold는 초기 구현 후 테스트 결과 기반으로 조정한다. 0.6은 과매칭 위험이 있어 TODO로 남긴다.

## LLM 호출 횟수

| 상황 | LLM 호출 |
|---|---|
| entity_type 정상 추출 + 직접 매칭 성공 | 1회 (Step 1만) |
| entity_type 정상 추출 + 직접 매칭 실패 | 2회 (Step 1 + semantic name match) |
| entity_type=None + 전체 JSON 검색으로 발견 | 1회 (Step 1만) |
| entity_type=None + 전체 JSON 검색 실패 + entity_type fallback으로 해결 | 2회 (Step 1 + Step 3b) |
| entity_type=None + 전체 JSON 검색 실패 + 재검색도 이름 불일치 | 3회 (Step 1 + Step 3b + semantic name match) |

## 처리 흐름

### Step 1 — LLM으로 조회 의도 구조화

`build_prompt(state)`로 메시지를 만들고 `invoke_llm(..., structured_output=_ReaderQuery)`로 파싱한다.
실패 시 즉시 fallback 메시지를 반환한다.

### Step 2 — 파일 읽기

`entity_type=system`이면 `System.json`을 직접 읽는다.
그 외에 Step 1에서 `entity_type`이 결정된 경우 `_load_items_for_entity_type()`가 `CATEGORY_TO_PLURAL`로 파일명으로 변환해 해당 JSON을 읽고 `_valid_items()`까지 적용한다.

`entity_type`이 None인데 `entity_name`도 없으면 (bulk_list / aggregate 전체 대상이 아닌 경우) 에러를 반환한다.

### Step 3 — 엔티티 매칭

`entity_name`이 있으면 `_find_candidates()`로 후보를 찾는다.
우선순위는 `ID 숫자 직접 접근 → exact → case-insensitive exact → prefix → fuzzy`다.
`bulk_list` / `aggregate`처럼 entity_name이 None이면 매칭 단계를 건너뛴다.

### Step 3a — entity_type=None + entity_name 있음: global entity lookup

Step 1에서 `entity_type`이 None이고 `entity_name`이 있으면 (`single_entity` / `field_value` / `existence` 해당),
모든 카테고리를 순회하며 entity_name으로 매칭을 시도한다.

이는 **global entity lookup** — 카테고리 미지정 상태에서 어느 파일에 해당 이름이 있는지 찾는 것이다.
미지원 범위인 **cross-file traversal**(한 파일의 참조를 따라 다른 파일 내용을 계산)과 다르다.

```python
for category, plural in CATEGORY_TO_PLURAL.items():
    data = read_game_json(game_id, plural + ".json")
    candidates = _find_candidates(entity_name, _valid_items(data or []))
    if candidates:
        entity_type = category  # 첫 번째 매칭 카테고리로 확정
        break
```

발견 시 entity_type을 해당 카테고리로 확정하고 Step 4로 진행한다.
미발견 시 Step 3b로 내려간다.

### Step 3b — entity_type=None + 전체 검색 실패: LLM 2nd call (fallback)

9개 파일 어디에도 없는 경우 LLM이 entity_type을 추정한다.

`agent/prompts/definition_prompt.py`의 `STEP2_SYSTEM_PROMPT`를 직접 import하지 않는다.
reader는 definition 내부 규칙에 묶여서는 안 된다 — definition 프롬프트가 바뀌면 reader도 흔들린다.
대신 `reader_prompt.py` 안에 entity-type-guess 전용 system prompt를 별도로 선언한다.

```python
# agent/prompts/reader_prompt.py
_ENTITY_TYPE_GUESS_SYSTEM = """\
사용자가 언급한 이름이 RPG Maker MZ의 9개 카테고리 중 어느 것에 해당하는지 판별하라.
카테고리: actor, enemy, item, weapon, armor, class, state, skill, system
...
"""
```

`_EntityTypeGuess`는 reader.py 내부 private 클래스로 선언한다.

```python
class _EntityTypeGuess(BaseModel):
    entity_type: str | None
    reasoning: str
```

분류된 entity_type으로 해당 파일을 재검색한다. 여기서도 미발견이면 LLM이 추정한 카테고리를 포함해 안내한다.

```
'Pegasus'라는 적을 찾지 못했습니다.
유사한 이름: Dragon (ID: 3), Pegasos (ID: 7)
```

유저는 이 응답을 보고 "액터 페가수스" 등으로 카테고리를 명시해 재요청할 수 있다.

### Step 3c — 직접 매칭 실패: semantic name matching fallback

직접 매칭 결과가 0개이면 `_guess_entity_name()`이 LLM으로 의미론적 이름 매핑을 한 번 더 시도한다.
이 fallback은 다음 두 경로에서만 실행된다.

- `entity_type`이 이미 있는 상태에서 `_find_candidates()`가 실패한 경우
- Step 3b의 entity_type fallback 후 재검색에서도 후보가 없는 경우

`build_entity_name_match_prompt(query_name, available_names)`로 후보 이름 목록을 함께 보내고,
LLM이 반환한 이름이 실제 목록에 존재할 때만 `query.entity_name`을 그 이름으로 갱신한다.

### Step 4 — 조회 실행

query_type별 처리:

- `single_entity`: 매칭된 엔티티의 **핵심 필드**만 반환. raw dump 전체 출력은 하지 않는다 (아래 참고).
- `field_value`: 매칭된 엔티티에서 `field_name` 필드만 반환.
- `bulk_list`: 파일 전체 `id` + `name` 목록 반환. `filters` / `sort` / `limit` 적용. 결과가 30개를 초과하면 상위 30개만 출력하고 안내 메시지를 덧붙인다 (아래 참고).
- `existence`: 후보 수에 따라 존재 / 모호 / 미발견 응답을 반환한다.
- `aggregate`: `aggregate_fn`에 따라 집계. `count`를 제외하면 거의 항상 `field_name`이 필요하다 (아래 참고).

#### single_entity 핵심 필드 노출 기준

RPG Maker MZ JSON에는 보여줄 가치가 낮은 필드(중첩 배열, 메타데이터 등)가 많다.
기본 응답은 핵심 필드만 노출하고, 필요 시 raw/full view는 향후 확장으로 남긴다.

- params 배열이 있으면 8개 기본 스탯(maxHp/maxMp/atk/def/mat/mdf/agi/luk) 한 줄 요약
- 그 외 스칼라 값(str/int/float/bool)만 표시
- 중첩 리스트, 이중 배열(traits, effects 등)은 제외

#### bulk_list 30개 초과 처리

`limit`이 지정되지 않은 `bulk_list` 결과가 30개를 넘으면 상위 30개만 출력하고 아래 안내를 덧붙인다.

```
스킬 목록 (총 47개 중 30개 표시):
 1. Fire (ID: 1)
 ...
 30. Cure (ID: 30)
더 보려면 범위를 좁혀 검색해 주세요. 예) "공격 계열 스킬 보여줘"
```

재질문(확인 요청) 방식은 채택하지 않는다. reader는 `user_input`과 `game_id`만 읽으므로
"이전 응답이 확인 요청이었는지" 여부를 state 변경 없이 안정적으로 판별하기 어렵다.

#### aggregate와 field_name

`count`는 field_name 없이 전체 항목 수를 반환한다.
`min` / `max` / `avg` / `sum`은 **field_name이 필수**다. 없으면 에러 메시지를 반환한다.

```
[aggregate / count]   → field_name 불필요
[aggregate / max]     → field_name="atk" 필요  ("가장 강한 무기" → atk 추론은 LLM Step 1 담당)
[aggregate / avg]     → field_name="price" 필요 ("아이템 평균 가격" → price 추론은 LLM Step 1 담당)
```

### Step 5 — 결과 포맷 → final_response

LLM을 쓰지 않고 rule-based 템플릿으로 포맷한다.

```
[field_value]
페가수스의 maxHp는 800입니다.

[single_entity]
페가수스 (ID: 12)
 - 스탯: maxHp: 800 / maxMp: 0 / atk: 95 / def: 40 / mat: 60 / mdf: 60 / agi: 70 / luk: 50
 - exp: 300
 - gold: 150

[bulk_list]
무기 목록 (총 8개):
 1. 철검 (ID: 1)
 2. 강철 창 (ID: 2)
 ...

[bulk_list — 30개 초과 truncation]
스킬 목록 (총 30개):
 1. 파이어볼 (ID: 1)
 ...
 30. 힐 (ID: 30)

(전체 47개 중 상위 30개만 표시됩니다. 범위를 좁혀서 다시 검색해보세요.)

[bulk_list + sort/limit]
atk 상위 3개 무기:
 1. 엑스칼리버 (ID: 7) — atk: 200
 2. 용 학살자 (ID: 5) — atk: 180
 3. 강철 창 (ID: 2) — atk: 120

[existence / matched]
'드래곤' 적은 현재 게임에 존재합니다. (ID: 7)

[existence / ambiguous]
'드래곤'과 유사한 이름이 여럿 있습니다. 어떤 것을 찾으시나요?
 - 드래곤 나이트 (ID: 5)
 - 불꽃 드래곤 (ID: 9)
 - 드래곤 좀비 (ID: 11)

[aggregate / count]
현재 게임의 적은 총 23마리입니다.

[aggregate / max]
atk이(가) 가장 높은 무기는 엑스칼리버 (ID: 7)입니다. (atk: 200)

[not_found]
'고블린 킹'이라는 적을 찾지 못했습니다.
유사한 이름: 고블린 (ID: 2), 고블린 전사 (ID: 4)
```

## 에러 처리

| 상황 | 처리 |
|---|---|
| LLM structured output 실패 | `"요청을 이해하지 못했습니다. 다시 입력해주세요."` |
| 파일 없음 (read_game_json → None) | `"해당 카테고리의 데이터를 찾을 수 없습니다."` |
| JSON 파싱 실패 | `"게임 데이터를 읽는 중 오류가 발생했습니다."` |

모든 에러는 `final_response`에 담아서 END로 흘러가게 한다. exception을 바깥으로 던지지 않는다. 이는 다른 모든 노드의 공통 규칙이다.

## TODO

- **맵(Map) 조회**: 현재 `CATEGORY_TO_PLURAL`에 맵 관련 항목이 없다. RPG Maker MZ의 맵 데이터는 `Map001.json`, `Map002.json` 등 파일이 분리돼 있어 단순 카테고리 매핑으로 처리하기 어렵다. 맵 조회 지원 방식은 별도로 설계 필요.

- **HOW-TO 질문 처리**: "적에게 독 상태를 넣으려면 어떻게 해야 돼?"처럼 게임 메커니즘 설명을 요청하는 질문은 reader 범위 밖이다. router가 `범위_외`로 분류해야 하나, `게임_요소_조회`로 잘못 분류되어 reader로 넘어오는 케이스가 있다. router 프롬프트 보완 또는 reader 내 HOW-TO 쿼리 감지 후 안내 반환 중 어떤 방식이 적합한지 판단 필요.

- **집계 불가 필드 처리**: "스킬 중 제일 쎈 게 뭐야?"처럼 스킬의 강도를 묻는 질문은 `damage.formula`를 파싱해야 계산 가능하다. 현재 aggregate는 숫자 필드만 집계할 수 있으며, formula 기반 강도 계산 rule을 어떻게 정의할지 설계 필요.

- **entity_name 파싱 오류 (구조적 한계)**: "치유의 마나 소모량"에서 LLM이 "치유의"만 entity_name으로 잘라내는 등, 게임 데이터를 모르는 LLM이 entity_name 경계를 잘못 판단하는 케이스가 있다. 게임 내 엔티티 이름 목록을 프롬프트에 일부 포함하거나, 파싱 실패 시 prefix 매칭 결과를 후보로 보여주는 방식을 고려할 수 있다.

- **다중 턴 모호성 해소 (미구현)**: "일으킴의 마나 소모량이 어떻게 돼?" → "일으킴 I, II, III 있슴다 어떤 거요?" → "일으킴 I" 같은 흐름에서, 후속 메시지가 앞선 조회의 clarification임을 인식해야 한다. 현재는 이 맥락이 끊겨서 "일으킴 I" 단독 입력이 router에서 `일반_대화`로 분류되거나, reader에서 field_name 맥락을 잃는다.

  구현 방향 두 가지:

  - **Option A (권장) — conversation_history를 reader 프롬프트에 포함**: `build_prompt(state)`에서 최근 1~2턴 history를 시스템 프롬프트에 추가한다. LLM이 이전 응답("여러 후보 있음")과 현재 입력("일으킴 I")을 합쳐 완전한 쿼리로 재구성할 수 있다. router 프롬프트도 history를 보고 "이전 조회의 후속"임을 감지해야 한다. 전제 조건: conversation_history가 매 요청마다 이전 turns를 포함해 올바르게 채워져야 한다.

  - **Option B — pending_reader_query 상태 필드**: reader가 모호 응답을 반환할 때 `pending_reader_query: {entity_type, field_name, query_type}`을 state에 남겨두고, 다음 턴에 이를 읽어 entity_name만 교체해 재실행한다. 구현은 단순하지만 state가 턴 간에 유지되는 구조여야만 동작한다.

## 미지원 범위

아래 패턴은 Reader에서 처리하지 않는다.

| 패턴 | 이유 |
|---|---|
| `compare` (둘 이상 비교) | 다중 엔티티 조회 + 비교 로직 필요. 1차 미지원, 향후 추가 가능 |
| `related_entities` (참조 따라가기) | 교차 파일 조회 필요. Reader 범위 밖 |
| cross-file traversal | 예: "이 스킬을 가진 캐릭터 있어?" — 여러 파일 교차 필요 |
| 복합 질의 | 조회 + 수정이 이어지는 경우. router에서 `복합_의도`로 처리 |

미지원 패턴이 감지되면 `"현재 지원하지 않는 조회 유형입니다"` 안내를 담고 END로 흘러간다.

## 기존 workflow와의 관계

Reader는 조회 전용이라 아래 노드들과 완전히 독립적이다.

- definition, planner, executor, validator, synthesizer를 전혀 거치지 않는다.
- `changes_log`, `tool_results`, `backup_paths`, `modified_game_state` 등의 state 필드를 건드리지 않는다.
- `game_id` 기준으로 게임 파일을 읽기만 하므로 게임 데이터에 부작용이 없다.

## 테스트 계획 (test_reader.py)

파일 위치: `agent/tests/test_reader.py`

현재 저장소의 `test_reader.py`는 pytest 스위트가 아니라 **인터랙티브 smoke 스크립트**다.
입력마다 아래 state를 만들어 실제 `reader(state)`를 호출한다.

```python
state = {
    "user_input": user_input,
    "game_id": "game_001",
    "conversation_history": [],
}
```

실행 방법:

```python
uv run python agent/tests/test_reader.py
```

동작 방식:
- `game_id`는 현재 `"game_001"`로 고정돼 있다.
- LLM 호출과 파일 읽기를 모두 실제 환경 그대로 사용한다.
- 종료하려면 `exit`, `q`, `quit` 중 하나를 입력한다.

향후 pytest 기반 단위/통합 테스트를 추가한다면 아래 항목을 우선 검증 대상으로 삼는다.
- `invoke_llm(..., structured_output=_ReaderQuery)` 호출 여부
- entity_type fallback (`_guess_entity_type`) 호출 여부
- semantic name matching fallback (`_guess_entity_name`) 호출 여부
- `filters` / `sort` / `limit` / aggregate 경로
- 파일 없음 / LLM 실패 시 `final_response` fallback

## 라우팅 변경 (현재 적용됨)

### routing.py

`route_after_router()`에서 `게임_요소_조회`를 기존 `definition`이 아닌 `reader`로 보낸다.

```python
if intent in ("게임_요소_생성", "게임_요소_수정"):
    return "definition"
if intent == "게임_요소_조회":
    return "reader"
return "__end__"
```

### workflow.py

`reader` 노드를 등록하고 `reader → END` 엣지를 추가한다.

```python
builder.add_node("reader", reader)
builder.add_edge("reader", END)
```

`route_after_router`의 destination map에 `"reader": "reader"` 추가.
