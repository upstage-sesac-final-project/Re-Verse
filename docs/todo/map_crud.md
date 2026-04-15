# Map CRUD 지원을 위한 Reader / Definition / Planner 개선 계획

## 배경

PR #85는 **Executor**에 맵 관련 MCP 툴을 연결하고(`list_maps`, `get_map`, `get_map_events`, `search_map_events`, `create_map_event`, `update_map_event`, `update_map`, `add_event_command`, `draw_map_tile`, `create_map`) **Router 프롬프트**에서 맵/맵 이벤트 요청이 `범위_외`로 떨어지지 않도록 바로잡았다.

그러나 Router와 Executor 사이의 **Reader / Definition / Planner**는 손대지 않았다. 그 결과 현재 파이프라인은 다음과 같이 실패한다.

| 사용자 발화 | intent | 실패 지점 | 증상 |
| --- | --- | --- | --- |
| "맵 목록 알려줘" | `게임_요소_조회` → **Reader** | Reader에 Map 분기 없음 | System.json 요약을 엉뚱하게 반환 |
| "1번 맵에 고블린 전투 이벤트 추가해줘" | `게임_요소_생성` → **Definition** | Step 2 카테고리 분류가 "1번 맵"을 System으로 폴백 | Planner가 `System.json.error` 스텝 생성 → Executor `UNSUPPORTED_STRUCTURED_STEP` |
| "3번 맵 이벤트 조건 바꿔줘" | `게임_요소_수정` → **Definition** | 동일 | 동일 |

즉 **Executor는 맵 MCP를 받을 준비가 끝났지만 앞단이 맵을 인식하지 못해 도달하지 않는다.** 이 문서는 Reader / Definition / Planner가 맵을 지원하려면 각각 무엇을 수정해야 하는지 정리한다.

## 설계 원칙

1. **대상 파일은 두 가지**: `MapInfos.json`(전체 맵 목록/메타), `MapNNN.json`(단일 맵 상세 — 필드와 `events` 배열 포함). Executor는 이 두 파일명을 기준으로 이미 MCP로 분기한다. 앞단은 이 파일명을 **그대로 target_file로 내려보내면 된다.**
2. **카테고리는 두 계층**: `map`(맵 자체) / `map_event`(맵 안의 이벤트). 구분이 필요한 이유는 action 종류가 다르기 때문이다. 맵 자체는 `list / query / create / update`, 맵 이벤트는 `list_events / search_events / create_event / update_event / add_event_command`.
3. **mapId 식별자는 파일명이 진실의 원천**. Executor가 이미 `Map003.json` → `mapId=3`을 자동 보강하므로, 앞단은 자연어에서 map id를 추출만 하면 된다("1번 맵", "악마성 맵" 등).
4. **이벤트 id(eventId)**: 이벤트 수정·커맨드 추가 시에만 필요. 존재하지 않으면 Executor 또는 Planner에서 선행 `get_map_events` 스텝을 끼워 resolve한다.
5. **draw_tile은 MVP에서 제외**. "타일을 그린다"는 시각 편집에 가까워 Router 정책과 긴장하므로 초기 스코프에서 빼고 별도 플래그로 뒤에 켠다.

## 공통 — 상수/카테고리 테이블

### `agent/constants.py`

현재 `CATEGORY_TO_PLURAL`과 `CATEGORY_TO_ID_FIELD`에는 맵/맵 이벤트가 없다. 두 가지 방식이 있다.

**A안 — 카테고리 추가 (권장)**

```python
CATEGORY_TO_PLURAL = {
    ...
    "map": "MapInfos",          # list / create 경로 기본 파일
    "map_event": "MapInfos",    # 형식 맞춤용. 실제 target_file은 MapNNN.json으로 교체됨
}

CATEGORY_TO_ID_FIELD = {
    ...
    "map": "map_id",
    "map_event": "event_id",
}
```

단, `MapInfos` 외에 실제 조작 파일은 `MapNNN.json`이라서 `category → 파일명` 단순 매핑으로는 부족하다. 아래 Definition / Planner 단계에서 **"map 카테고리 + map_id가 지정되면 target_file = MapNNN.json"으로 교체**하는 규칙을 둔다.

**B안 — 상수는 건드리지 않고 노드별 특수 분기**

범용성이 떨어지지만 블라스트 반경이 작다. map/map_event만 Reader·Definition·Planner 각각에서 하드코딩 분기로 처리. 본 문서는 **A안 기준**으로 기술한다.

### `agent/utils/game_data_io.py`

`CATEGORY_TO_PLURAL`이 constants.py와 중복으로 선언돼 있다. 맵 지원 전에 **단일 소스로 통합**하거나 두 쪽 모두 동일하게 업데이트 필요. 아래 계획은 양쪽 모두 수정되는 것을 전제로 한다.

---

## 1. Reader (`agent/editor/nodes/reader.py`)

### 현재 상태

- `_ReaderQuery.entity_type`에 문자열로 카테고리가 들어오며, `_REFERENCE_MAP` / `_FILTER_MAP` / `_CATEGORY_DISPLAY` 세 개의 테이블로 동작.
- `_execute_system_query()` 하나만 System.json 전용 특수 경로로 존재.
- **Map / MapInfos 처리 없음**. grep 결과 "맵"은 주석의 비정형 단어뿐.

### 추가해야 할 기능

맵 조회는 크게 다섯 가지로 본다.

| 발화 예 | entity_type | action | target_file | MCP tool |
| --- | --- | --- | --- | --- |
| "맵 목록 알려줘", "어떤 맵 있어?" | `map` | `list` | `MapInfos.json` | `list_maps` |
| "1번 맵 정보 보여줘" | `map` | `get` | `MapNNN.json` | `get_map` |
| "1번 맵에 이벤트 뭐 있어?" | `map_event` | `list` | `MapNNN.json` | `get_map_events` |
| "1번 맵 이벤트에서 고블린 검색" | `map_event` | `search` | `MapNNN.json` | `search_map_events` |
| "악마성 맵에 있는 이벤트 목록" | `map` → 이름→id 해소 후 `map_event.list` | — | — | (선행 `list_maps` 후) `get_map_events` |

### 구현 지점

1. **엔티티 타입 추정 프롬프트** (`build_entity_type_guess_prompt` 쪽): 후보 카테고리에 `map`, `map_event` 추가. 자연어 → `map_id` 추출 규칙("1번 맵", "세 번째 맵", "악마성 맵")도 명시.
2. **`_ReaderQuery`에 `map_id: int | None`, `search_term: str | None` 필드 추가.** 이미 있는 필터 구조에 얹을 수도 있지만, Executor의 MCP 인자와 1:1로 맞추는 편이 디버깅에 유리.
3. **새 dispatcher**: `_execute_map_query(query, game_id)` 추가.
    - `map + list` → MCP `list_maps` 호출 또는 직접 `MapInfos.json` 로드 후 이름/ID 리스트 렌더링. Reader 성격상 **MCP 경유 없이 파일에서 바로 읽는 게 자연스럽다** (Reader는 본래 변경 없는 조회이며 스냅샷/백업 불필요).
    - `map + get` + `map_id` → `MapNNN.json` 로드, 주요 필드(`width`, `height`, `tilesetId`, `bgm`, `parallaxName`, `events` 개수 등) 요약.
    - `map_event + list` → `MapNNN.json`의 `events` 배열을 `{id, name, x, y, note}` 레코드로 요약.
    - `map_event + search` + `search_term` → 각 event의 `name`, `note`, 그리고 `pages[*].list[*].parameters` 문자열을 순회하며 부분일치.
4. **맵 이름 → map_id 해소 헬퍼**: `MapInfos.json`을 읽어 `name` 부분일치(`SequenceMatcher` 임계값은 Definition과 동일한 수준으로). Reader 전역에서 재사용.
5. **`_CATEGORY_DISPLAY`에 한글 표시** 추가: `map → "맵"`, `map_event → "맵 이벤트"`.
6. **파일 IO 경유 여부 결정**: Reader는 **MCP 없이 파일 직읽기**를 권장. 이유 — Reader는 side-effect 없고, Executor의 MCP 세션 비용을 피함. 단 Executor와 일관된 스키마 해석이 필요하므로 `agent/utils/game_data_io.py`에 `load_map_infos(game_id)`, `load_map(game_id, map_id)` 유틸을 추가하고 Reader·Executor·Validator가 공통으로 쓰게 한다.

### 출력 포맷 예시

```
맵 목록 (총 5개):
  [1] 시작 마을  (20x15, tileset=2)
  [2] 동쪽 숲    (30x30, tileset=3)
  ...
```

```
1번 맵 "시작 마을" (20x15)
  tileset: 2  bgm: Village1  parallax: (없음)
  이벤트 8개 — 주요: 촌장(id=1), 상인(id=2), 여관주인(id=3) ...
```

### 테스트

- 기존 test_executor_mvp 스타일로 `agent/tests/test_reader_map.py` 추가: `MapInfos.json`/`Map001.json` 픽스처 만들고 `_execute_map_query`를 단위 테스트.
- `test_repl.py`로 "맵 목록 알려줘" / "1번 맵 정보" / "1번 맵 이벤트 목록" 3종 수동 확인.

---

## 2. Definition (`agent/editor/nodes/definition.py`)

### 현재 상태

CLAUDE.md에 적힌 5단계 파이프라인 (subject 추출 → 카테고리 분류 → system_ref 보정 → ID 매핑 → target_files/modifications 생성 + bulk/Step 6 보정 + Step 7 NEW ID 치환). `CATEGORY_TO_PLURAL`/`CATEGORY_TO_ID_FIELD`에 맵이 없어서 **Step 2에서 "1번 맵"이 어디에도 매칭 못 하고 최종적으로 System으로 폴백**한다.

### 추가해야 할 기능

생성·수정 경로에서 필요한 조합:

| 발화 예 | subject | category | action | target_file | target_info 핵심 |
| --- | --- | --- | --- | --- | --- |
| "새 맵 추가해줘 이름 시험던전 30x30" | 시험던전 | `map` | `create` | `MapInfos.json` | `{mapName, width, height, tilesetId?}` |
| "1번 맵 크기를 40x40으로" | 1번 맵 | `map` | `update` | `Map001.json` | `{mapId, updates: {width, height}}` |
| "1번 맵에 고블린 전투 이벤트 추가" | 고블린 전투 | `map_event` | `create_event` | `Map001.json` | `{mapId, name, x?, y?, note?, pages?}` |
| "3번 맵의 촌장 이벤트 대사 수정" | 촌장 | `map_event` | `update_event` | `Map003.json` | `{mapId, eventId, updates}` |
| "3번 맵 촌장 이벤트에 아이템 지급 커맨드 추가" | 촌장 | `map_event` | `add_event_command` | `Map003.json` | `{mapId, eventId, pageIndex, command, position?}` |

### 구현 지점

1. **Step 1 (subject 추출) 프롬프트**에 예시 추가:
    - `"1번 맵에 고블린 전투 이벤트 추가해줘"` → `subject="고블린 전투"`, `property=None`, `action="create"`, 그리고 **스코프 필드로 `map_id=1`**을 명시. 현재 스키마에 이 필드가 없다면 `context: {"map_id": 1}` 같은 extra 필드 허용을 도입.
2. **Step 2 (카테고리 분류)** 프롬프트:
    - 선택지에 `map`, `map_event` 추가. 판별 규칙을 프롬프트에 적시:
        - subject가 "N번 맵" / "OO 맵" / "맵 OO" → `map`
        - subject가 "이벤트" 단어를 포함하거나 context에 map_id가 있고 target이 이벤트성 동작 → `map_event`
3. **Step 3 (system_ref 보정)**: 맵은 System.json 참조 대상이 아니므로 변경 불필요. 단, **"시작 맵" / "첫 맵" → `System.json.startMapId`** 관련 요청은 기존 startMapId 처리로 흐르도록 예외 규칙 명시.
4. **Step 4 (엔티티 ID 매핑)**:
    - `map` 카테고리는 `MapInfos.json`을 ID 목록 소스로 사용. 이름→id 매칭 임계값은 기존 업데이트 경로와 동일(`0.5`). 엔티티 이름이 "1번 맵"처럼 숫자 참조면 `SequenceMatcher`를 우회하고 숫자를 바로 `map_id`로 치환하는 **전처리** 추가.
    - `map_event`는 `MapNNN.json`의 `events` 배열에서 이름 매칭. map_id가 확정돼야 매칭 가능하므로, **map 먼저, map_event 나중** 순서로 처리한다.
5. **Step 5 (target_files / modifications 생성)** 프롬프트:
    - 카테고리 → 파일 매핑 규칙에 맵 규칙 추가:
        - `category=map AND action=create` → `target_file=MapInfos.json`
        - `category=map AND action in (update, read, query)` → `target_file=Map{map_id:03d}.json`
        - `category=map_event AND *` → `target_file=Map{map_id:03d}.json`
    - action 이름을 Executor가 기대하는 정확한 소문자 토큰으로 고정: `list`, `query`, `read`, `update`, `create`, `list_events`, `search_events`, `create_event`, `update_event`, `add_event_command`.
6. **Step 6 (output 보정)**:
    - target_file이 맵 계열이면 `_enforce_map_target_file()` 헬퍼로 `Map{NNN}.json` 포맷 강제. map_id 미지정이면 `params_sufficient=False`로 떨구고 사용자에게 "몇 번 맵인가요?" clarification.
    - bulk 지원 카테고리 상수(`BULK_SUPPORTED`)에 map/map_event는 **추가하지 않음**. 맵 이벤트 일괄 수정은 요구가 생기면 그때 추가.
7. **Step 7 (NEW ID 치환)**:
    - `map` + `create`에서 새 map_id 부여. `load_map_infos()`로 읽어 마지막 +1. (기존 `get_next_entity_id()`에 `map` 지원 추가 — MapInfos는 sparse array라 index 길이 기반으로 단순 계산.)
    - `map_event` + `create_event`의 eventId는 Executor/MCP가 자체 할당하므로 Definition에서 치환하지 않음.

### clarification 규칙

`params_sufficient=False`로 종료해야 하는 경우:
- `map + update`인데 map_id도 없고 이름 매칭 후보도 없을 때
- `map_event + create_event`인데 map_id 추출 실패
- `map_event + update_event`인데 eventId 해소 실패 (이름 후보가 2개 이상이거나 0개)

메시지 예: `"어느 맵에 추가할까요? 맵 번호 또는 맵 이름을 알려주세요."`

### 테스트

- `agent/tests/test_definition_map.py`: 위 5개 발화 예를 넣어 각 단계 출력 확인.
- `full_pipeline_check.py`로 생성/수정 E2E.

---

## 3. Planner (`agent/editor/nodes/planner.py`)

### 현재 상태

- LLM 1회로 structured output을 받아 `_restore_bulk_updates_from_definition()`으로 일부 필드를 복원.
- bulk alias / target file map이 상수에 하드코딩.
- Definition 출력에 강하게 의존해서 **Definition만 맵을 지원하면 Planner 개조 범위는 크지 않다**.

### 추가해야 할 기능

1. **Planner 프롬프트 예시**에 맵 케이스 4~5개 추가. step 구조 예:

    ```json
    // "1번 맵에 고블린 전투 이벤트 추가해줘"
    [
      {
        "step_id": 0,
        "description": "이벤트 ID 충돌 회피용 현재 이벤트 목록 조회",
        "action_type": "list_events",
        "target_file": "Map001.json",
        "target_info": {"mapId": 1},
        "depends_on": []
      },
      {
        "step_id": 1,
        "description": "고블린 전투 이벤트 생성",
        "action_type": "create_event",
        "target_file": "Map001.json",
        "target_info": {"mapId": 1, "name": "고블린 전투", "x": 0, "y": 0, "note": ""},
        "depends_on": [0]
      }
    ]
    ```

2. **자동 선행 스텝 삽입 규칙** (`_augment_map_plan()` 신규):
    - `update_event` / `add_event_command`인데 target_info에 `eventId`가 없으면, 직전에 `list_events` 스텝을 자동 삽입하고 `depends_on`으로 연결. eventId는 Executor의 `decision_basis.source_query_step_ids`를 활용해 해소 — 단 Executor가 이 체인을 이벤트 이름으로 resolve할 수 있어야 하므로, 당장은 Planner가 이름을 `target_info.eventName`에 담아두고 **Executor에 `eventName → eventId` 해소 후킹을 추가**하거나, Planner가 LLM에게 "list_events 결과를 참조한다"는 의사-참조만 걸고 실제 바인딩은 Executor가 담당하도록 한다. **MVP에서는 후자**(실제 해소는 Executor 후속 작업으로 TODO).
3. **`target_file` 포맷 검증**: Planner 출력에서 `Map*.json`이면 3자리 zero-pad 강제(`Map3.json` → `Map003.json`). Executor의 `_parse_map_id_from_target_file` 정규식과 일치시키기 위함.
4. **bulk 처리**: 현재 Definition이 map/map_event에 대해 bulk을 생성하지 않도록 막았다면 Planner 쪽 `_restore_bulk_updates_from_definition`은 건드릴 필요 없음. 단, **bulk selector가 들어오면 map 계열에서는 에러 스텝을 만들게** guard 추가.

### 테스트

- `agent/tests/test_planner_map.py`: Definition 픽스처를 주입해 Planner 출력이 위 step 구조와 일치하는지.
- `full_pipeline_check.py` 회귀.

---

## 의존 관계 및 작업 순서

```
constants.py / game_data_io.py 통합
        │
        ▼
Definition (Step 2·5·6·7 프롬프트 + 헬퍼)
        │
        ├──▶ Planner (프롬프트 예시 + 선행 스텝 삽입)
        │
        └──▶ Reader (독립)
        │
        ▼
Executor (맵 이벤트 eventName → eventId 해소 훅) — 후속
        │
        ▼
Validator (MapInfos/MapNNN 스키마 + query consistency 범위 확장) — 후속
```

1. **Phase 1 — 상수 통합**: `CATEGORY_TO_PLURAL`/`CATEGORY_TO_ID_FIELD`에 map/map_event 추가. `game_data_io.py`의 중복 정의 제거 또는 동기화. `load_map_infos`, `load_map` 유틸 추가.
2. **Phase 2 — Reader 맵 조회**: 가장 독립적이고 side-effect 없음. PR 하나로 종결 가능. 맵 조회 E2E 작동 확인.
3. **Phase 3 — Definition 맵 분류**: Step 2 / Step 5 프롬프트 + Step 6 target_file 포맷 강제 + Step 7 map_id 할당. 이 단계 끝나면 Planner가 엉뚱한 `System.json.error` 스텝을 만드는 현상은 사라진다.
4. **Phase 4 — Planner 프롬프트 예시**: map create/update/create_event/update_event/add_event_command. 선행 list_events 자동 삽입은 eventId 해소 훅이 준비된 다음.
5. **Phase 5 (후속) — Executor eventName 해소 & Validator 맵 스키마**: 본 문서 범위 밖.

## 검증 체크리스트

맵 지원이 "끝났다"의 기준:

- [ ] `test_repl.py`에서 "맵 목록 알려줘" → Reader가 `MapInfos.json`을 요약 출력
- [ ] "1번 맵 정보 보여줘" → Reader가 `Map001.json` 요약 출력
- [ ] "1번 맵 이벤트 목록" → Reader가 events 배열 요약 출력
- [ ] "새 맵 추가해줘 이름 시험던전" → Definition `params_sufficient=True`, Planner가 `MapInfos.json + create`, Executor가 `create_map` 호출, `success=True`
- [ ] "1번 맵에 고블린 전투 이벤트 추가해줘" → Planner가 `Map001.json + create_event`, Executor가 `create_map_event` 호출, `success=True`
- [ ] `full_pipeline_check.py`의 종료 코드가 위 모든 발화에서 `0`
- [ ] 기존 비-맵 회귀: 액터/적/아이템/스킬 생성·수정·조회 영향 없음 (`test_executor_mvp` 통과)

## 참고 파일

- `agent/editor/nodes/executor.py` — PR #85에서 추가된 `MCP_TOOL_MAP` 맵 엔트리, `_resolve_mcp_map_file_entry`, `_normalize_mcp_arguments`의 맵 블록
- `agent/tests/executor_step4_map_test.py` — execution_plan을 수기로 짜서 Executor만 호출하는 참조 예시
- `agent/editor/prompts/router_prompt.py` — 맵 관련 Router 정책(지원 범위 / 범위_외 경계)
- CLAUDE.md §2 Definition, §3 Planner, §4 Executor
