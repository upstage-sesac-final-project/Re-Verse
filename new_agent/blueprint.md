# new-agent Blueprint

## 목적

현재 `agent/` 워크플로우는 6단 파이프라인(router → [reader] → definition → planner → executor → validator → synthesizer)으로 동작한다. 설계 자체는 면밀하지만 실전 결과물이 신통치 않고, 유지보수 비용이 빠르게 커지고 있다. 이 문서는 그걸 대체할 실험 구조 `new_agent`의 설계서다.

실험이 실패하면 `agent/`로 롤백하고, 성공하면 점진적으로 전환한다. 현재 동작 중인 `agent/` 코드는 그대로 둔다.

---

## 현재 구조의 진단

코드 레벨에서 가장 크게 아픈 지점은 네 가지다.

1. **각 단계가 다음 단계를 위한 JSON을 LLM으로 예측하고, 다음 단계가 그 예측을 사후 보정한다.** Definition Step 5.5 재시도, Planner의 `_restore_bulk_updates_from_definition`, Executor의 `_enrich_*` 계열 함수가 모두 이 패치 작업이다.
2. **ID 해소를 실제 파일을 보기 전에 한다.** Definition이 `RPGRetriever` + `SequenceMatcher(0.5)`로 추측한 ID가 틀리면 downstream 전체가 틀린 엔티티를 수정한다. 단일 최대 실패 원천.
3. **Retry 루프가 재작업하지 않는 레이어에 실제 bug가 산다.** Validator는 실패 시 executor만 재호출한다. 대부분의 실패는 definition 단계의 의도 해석 오류에서 오는데 definition은 재실행되지 않는다.
4. **State 계약이 실제 runtime과 어긋난다.** `message_for_user`, `modified_file_paths`는 노드가 반환하지만 `AgentState`에 선언되지 않았고, `game_context` / `operation_id`는 선언되어 있지만 사실상 쓰이지 않는다.

Executor는 3,286줄까지 불어났고, reader는 자기 자신만의 912줄짜리 `_REFERENCE_MAP`을 유지한다. 쓰기와 읽기가 엔티티 해소 로직을 별도로 들고 있다.

---

## 설계 원칙

다음 세 원칙을 모든 노드 설계에 일관되게 적용한다.

1. **executor_yb를 재활용한다.** 이미 존재하는 `new-agent/executor_yb.py`는 MCP/legacy 경로가 제거된 1,412줄짜리 순수 CRUD executor다. 구조화 플랜(`step_id / action_type / target_file / target_info / depends_on`) 포맷에 planner 출력을 맞춰서 그대로 쓴다.
2. **각 노드는 "다른 메커니즘"이어야 한다.** 노드 수가 현재와 비슷해도 내부 동작 원리가 달라야 실험 가치가 있다. 같은 LLM 호출 패턴을 반복하는 구조는 만들지 않는다.
3. **LLM은 꼭 필요한 곳에만 둔다.** 가능한 모든 단계를 결정론 Python으로 만들고, 남는 LLM 예산을 "실제로 LLM이 아니면 못 하는 일"(대화 맥락 해소, 의미적 엔티티 생성, 의미적 결과 판정)에 집중시킨다.

---

## 전체 구조

```
START
  ↓
intake       (LLM 1회: history + coref + intent + operation 추출)
  ↓
planner      (Python 결정론: WRITE_DEPENDENCIES 그래프 워크)
  ↓
profiler     (LLM 1회/create step: 의미적 필드 생성, create 없으면 skip)
  ↓
executor_yb  (Python: structured plan 실행, entity/map handler 분리)
  ↓
validator    (Python schema + LLM judge + partial retry loop, final_response 작성)
  ↓
END
```

**노드 5개.** 현재 6개(+reader 분기 7개)에서 줄었다. LLM이 호출되는 위치는 3곳(intake / profiler / validator의 judge)뿐이고, 나머지 2곳(planner / executor_yb)과 validator의 schema 단계는 전부 결정론 Python이다.

Reader는 별도 노드로 존재하지 않는다. `_REFERENCE_MAP`의 구조적 지식은 planner의 `WRITE_DEPENDENCIES`로 이식되고, 조회 요청은 planner가 trivial 1-step read plan을 만들어 executor_yb가 처리한다.

Router도 존재하지 않는다. intake가 "actionable / chat / out_of_scope / need_more_info" 분류까지 한 번에 처리한다.

---

## 노드 상세 설계

### 1. intake

**책임**: 사용자 원문과 직전 대화 이력을 받아 자립적인 요청으로 해소하고, 행동 유형을 분류하며, 구체 operation tuple을 뽑는다.

**메커니즘**: LLM 1회, structured output.

**입력**
- `user_input: str`
- `conversation_history: list[dict]` (직전 N턴만 slice, 기본 4턴)
- `game_id: str`

**출력**
```python
{
  "kind": "actionable" | "chat" | "out_of_scope" | "need_more_info",
  "resolved_input": str,          # 자립적으로 완성된 요청 문장
  "operation_tuples": [            # kind=actionable일 때만
    {
      "op": "create" | "update" | "delete" | "read",
      "file": "Actors.json" | "Armors.json" | ... | "Map",
      "subject": {"name": str},    # 대상 엔티티 (이름만, ID X)
      "field": str | None,         # 수정 대상 필드
      "value": {                   # op에 필요한 값 명세 (이름/자연어 수준)
        "kind": str,
        "name": str,
        "hints": str | None
      } | None,
    },
    ...
  ],
  "clarification_question": str | None,  # kind=need_more_info일 때만
  "final_response": str | None,          # kind in {chat, out_of_scope, need_more_info}
}
```

**프롬프트 설계 원칙**
1. 번호가 매겨진 순서를 명시한다: "(1) 이전 대화에서 언급된 대상/동작/속성을 식별 → (2) 현재 입력의 생략/대명사/'~도'를 이전 대화로 채움 → (3) resolved_input 작성 → (4) kind/operation 분류".
2. **ID를 절대 찍지 않는다.** 이름과 자연어만 다룬다.
3. kind=need_more_info일 때 `clarification_question`을 `final_response`로도 복사한다. 다음 턴에 intake가 대화 이력을 보고 해소한다.

**현재 대비 특징**
- 현재 router는 history를 쓰지만 definition은 안 쓴다 → multi-turn coref 불가. intake는 한 노드에서 해소 + 분류 + 추출을 번들한다.
- "리드에게 치유 스킬 줘" → "예빈에게도 해줘"의 "해줘" 해소가 intake의 단일 책임으로 깔끔하게 들어간다.
- 현재 definition Step 1(subject/property/value 추출)과 기능이 겹치지만, 여기서는 파이프라인 하부로 전달되는 계약이 훨씬 얇다(ID 해소/카테고리 매핑/NEW ID 치환 모두 없음).

---

### 2. planner

**책임**: intake의 `operation_tuples`를 받아 RPG Maker MZ 의존성 그래프에 따라 선행조건을 Python으로 결정한 다음, executor_yb가 바로 먹을 수 있는 structured plan을 만든다.

**메커니즘**: 순수 Python. **LLM 0회.**

**입력**
- `operation_tuples: list[dict]`
- `game_id: str`

**출력**
- `execution_plan: list[dict]` (executor_yb 포맷: `step_id`, `action_type`, `target_file`, `target_info`, `depends_on`)
- `plan_meta: dict` (operation_tuple별로 어떤 step_id들이 속하는지 역매핑 — validator의 partial retry가 쓸 것)

**처리 단계**
1. **그래프 워크**: `WRITE_DEPENDENCIES` 정적 사전에서 각 operation의 `(file, field, value.kind)`를 lookup해 `Requirement` 목록을 얻는다.
2. **선행조건 실측**: 각 Requirement를 **실제 게임 파일을 열어서** 존재 여부를 확인한다. 존재하면 resolved_id를 기록하고, 없으면 `create` Requirement로 승격한다. Reader의 `_REFERENCE_MAP` 검색 로직(이름 매칭, `SequenceMatcher`)을 재활용한다.
3. **위상 정렬**: Requirement 사슬을 `depends_on`으로 묶어 step 목록을 만든다. 같은 operation 내의 create 단계는 순서가 강제된다 (System armorType → Armors 생성 → Actors equips 업데이트).
4. **executor_yb 포맷으로 직렬화**: 각 step에 `step_id`, `action_type`, `target_file`, `target_info`를 채운다. create step의 `target_info`는 아직 **이름과 ref만 채워져 있고 의미적 필드(traits/params/description)는 비어 있다**. 이 빈칸은 profiler가 채운다.

**read-only 요청 처리**: operation이 전부 `read`면 그래프 워크 없이 단일 read step만 생성한다. executor_yb가 그대로 읽어서 응답한다. reader 노드의 역할은 여기에 흡수된다.

**`WRITE_DEPENDENCIES` 정의 위치**: `new-agent/planner/dependencies.py`. reader의 `_REFERENCE_MAP`을 쓰기 방향으로 뒤집은 한 파일. 여기가 프로젝트의 RPG Maker 도메인 지식 단일 원천이다.

**현재 대비 특징**
- 현재 planner는 LLM structured output으로 plan을 짠다. 신규는 LLM 0회, 결정론. ID 해소 brittleness 원천 제거.
- 현재 definition Step 4 + Step 5 + Step 7이 하던 "RAG 추측 → 매칭 → NEW ID 치환" 전부가 여기서 **실제 파일 조회**로 대체된다.

---

### 3. profiler

**책임**: planner가 만든 plan 중 `create_entity` step의 `target_info`를 의미적으로 채운다. "슬라임" → 물리 면역/화염 취약, "치유의 목걸이" → 체력 회복 trait 같은 개념-to-데이터 번역이 여기 집중된다.

**메커니즘**: LLM N회 (create step 개수만큼). step 단위로 독립 호출 가능하게 `profile_one(step, feedback=None) → enriched_step` 형태로 설계한다. validator의 partial retry 루프가 특정 step만 다시 부를 수 있어야 하기 때문이다.

**입력 (per step)**
- `step: dict` (planner가 만든 create step, name/ref만 채워짐)
- `schema_excerpt: str` (해당 파일의 관련 필드 스키마)
- `trait_codes_reference: str` (`traits_util`에서 제공하는 code → 자연어 참조표)
- `examples: list[dict]` (해당 파일의 잘 만들어진 기존 엔트리 1~2개)
- `feedback: str | None` (validator가 재호출 시 주입하는 실패 이유)

**출력 (per step)**
- `enriched_step: dict` (target_info의 의미적 필드가 채워진 동일 step)

**skip 조건**
- plan에 create step이 전혀 없으면 profiler 노드 통째로 우회한다 (pure update/delete/read 케이스).
- Map 파일 create step은 skip한다. Map 콘텐츠 생성(L4)은 MVP 밖 (아래 Map 스코프 절 참고).

**이름 결정 근거**: annotator는 기계적 필드 채움을 의미하고, profiler는 엔티티의 성격을 파악하는 의미적 목적을 강조한다. "슬라임은 물리 면역" 같은 판단이 핵심이므로 profiler가 맞다.

**프롬프트 품질이 전체 만족도의 60%를 좌우한다.** trait code 지식을 얼마나 잘 압축해서 프롬프트에 주는지가 결정적이다. `traits_util`의 참조표가 이 품질을 만든다.

---

### 4. executor_yb

**책임**: structured plan을 받아 RPG Maker MZ 파일에 실제 쓰기를 한다.

**메커니즘**: Python, CRUD 전용. LLM 0회. **기존 `executor_yb.py` 재활용**, 내부만 handler 트리로 분리한다.

**분해 후 구조**
```
new-agent/executor/
  __init__.py              # executor_yb() entry
  dispatch.py              # target_file → handler family 라우팅
  handlers/
    entity.py              # Actors/Classes/Skills/Items/Enemies/Weapons/Armors/States/System
    map.py                 # Map00x.json + MapInfos.json, L1(메타)만 구현, L4 확장 인터페이스
  utils/
    traits.py              # traits/effects code 참조표 + edit 헬퍼 (profiler도 import)
    locks.py               # game_locks 이동
```

**traits/effects는 cross-cutting 유틸이다.** 별도 executor 경로가 아니다. 8개 entity 파일이 모두 공유하는 포맷이고, profiler가 prompt에서 참조하는 code 테이블과 executor가 쓰는 edit 헬퍼가 **같은 파일을 import**해서 single source of truth가 된다.

**Map 핸들러 스코프**
- **MVP (L1)**: 메타데이터만. 지도 이름 변경, 부모 폴더 이동, 새 빈 지도 생성, 삭제. MapInfos.json 트리 조작.
- **MVP 밖 (L2/L3)**: 이벤트 배치, 인카운터 리스트 수정. 필요 시 추가.
- **확장 여지 (L4)**: 타일맵 콘텐츠 생성. 팀의 "초기 게임 생성 당시 이벤트 배치 및 타일셋 배치" 작업이 끝나면 `handlers/map.py`에 `content_ops` stub을 실제 구현으로 채우는 형태로 접합한다. 지금은 interface만 stub으로 남긴다.

**Map 핸들러 인터페이스 (L4 대비)**
```python
class MapHandler:
    def metadata_ops(self, action, target_info) -> Result: ...  # L1 구현
    def content_ops(self, action, target_info) -> Result:       # L4 stub
        raise NotImplementedError("Map content ops — L4")
```

profiler는 Map create를 받으면 `metadata_ops` 한정 필드만 생성하고 content 생성은 건너뛴다. 나중에 content_ops가 구현되면 profiler의 Map 분기도 확장한다.

**병렬 실행은 v1에서 하지 않는다.**
- planner가 만든 `depends_on` topological order대로 순차 실행한다.
- 현재 `game_locks[game_id]`로 게임 단위 직렬화. 안전.
- 병렬화는 파일 단위 락이 필요한데, 대부분의 plan이 3~5 step이고 그중 상당수가 dep로 묶여 있어 실제 이득이 작다. 프로파일링해서 정말 이득이 나오는 패턴이 관찰되면 그때 도입한다. plan에 이미 depends_on이 있으니 인프라 절반은 준비되어 있다.

---

### 5. validator

**책임**: executor가 쓴 결과를 검증하고, 실패 시 partial retry 루프를 돌리고, 최종 `final_response`를 작성한다. 현재의 synthesizer 역할까지 흡수한다.

**메커니즘**: Python schema 검증 + LLM judge + 내부 retry 오케스트레이션.

**검증 단계**

1. **Schema 검증 (Python, pydantic)**
   - executor가 쓴 파일을 `SCHEMA_MAP`으로 파싱한다.
   - 실패 시 loc/msg를 step_id별로 묶어 structured failure로 기록.
   - traits/effects의 code/dataId/value 포맷 오류가 여기서 잡힌다.

2. **Semantic judge (LLM 1회/operation)**
   - Schema를 통과한 결과에 대해서만 실행.
   - operation 단위로 판정 (intake의 `operation_tuples` 그대로 활용).
   - 입력: 사용자 원문 + 해석된 의도 + 실행 결과(traits는 `traits_util`이 자연어로 번역해서 포함).
   - 출력: `{match: bool, confidence: float, reason: str}`

   **Confidence 처리 규칙**
   | match | confidence | 처리 |
   |---|---|---|
   | True | ≥ 0.7 | 통과 |
   | True | < 0.7 | 통과 + 응답에 "확신 낮음" 태그 |
   | False | ≥ 0.5 | retry |
   | False | < 0.5 | 통과 (judge 자신도 확신 없음) |

   False negative(실제 틀림, judge는 맞다 판정)는 schema가 1차 방어선이라 허용 가능한 리스크다.

3. **명시적으로 제거된 것: step 이행도 검증**
   - 기존 validator가 했던 "changes_log의 각 step이 실제 파일에 반영됐는가"는 **하지 않는다**.
   - 이유: executor가 skip/no-op도 success로 보고하는 기존 문제 때문에 기존 구조에서도 무력했다. semantic judge가 "결과가 의도와 맞는가"를 보면 조용히 skip된 케이스도 자연스럽게 잡힌다. 덜 정밀하지만 더 넓게 덮는다.

**Partial retry 루프**

validator 내부에서 돈다. 별도 노드 backedge 없음.

```
for failed in failures:
    if failed.kind == "schema":
        # step_id 정확히 지목 가능
        patched = profile_one(failed.step, feedback=failed.text)
        execute_one(patched)
    elif failed.kind == "judge" and operation_has_create(failed.operation):
        # 해당 operation의 create step들만 재돌림
        for step in create_steps_of(failed.operation):
            patched = profile_one(step, feedback=failed.text)
            execute_one(patched)
    elif failed.kind == "judge" and not operation_has_create(failed.operation):
        # update-only operation의 judge 실패는 intake 의도 해석 자체가 의심됨.
        # intake 회귀는 너무 크고 같은 입력으로 재시도해도 동일 결과 가능성 높음.
        # → retry 없이 실패 보고.
        break
re-validate
```

`profile_one`, `execute_one`은 validator가 직접 import하는 utility 함수다. 노드 재진입이 아니다. 현재 "retry가 이전 노드로 회귀"라는 개념이 깨지고 **"실패한 부분만 patch"** 라는 더 정확한 개념으로 대체된다.

**Feedback text 생성**
- Schema failure: pydantic error location + msg를 profiler가 이해할 수 있는 한국어 문장으로 변환. traits/effects 오류는 `traits_util`의 해석을 덧붙임. 예: `"step 2 Armors.json create: traits[0]의 code=11은 dataId가 1~9 범위의 원소 id를 요구합니다. 현재 값: 99"`.
- Judge failure: judge의 `reason`을 그대로 활용 + 해당 operation의 원문 인용.

**최종 응답 작성 (현재의 synthesizer 역할 흡수)**
- **성공**: 결정론 템플릿. plan의 execution_steps 결과를 포맷팅. LLM 0회.
- **실패 (retry 소진)**: 결정론 템플릿 + `validation_feedback`을 사용자 친화적으로 포함. 기본은 LLM 0회. 정말 문장이 어색한 경우에만 조건부 LLM 호출.

현재 synthesizer가 LLM인 이유는 state가 난잡하고 요약 기준이 없기 때문이다. 신규 validator는 깔끔한 result 구조를 가지므로 템플릿이 더 적합하다.

---

## 데이터 흐름 요약

```
user_input + conversation_history
    ↓ intake (LLM)
resolved_input, kind, operation_tuples
    ↓ planner (Python)
execution_plan (ID 해소 완료, 의미 필드 비어있음), plan_meta
    ↓ profiler (LLM, create step만)
execution_plan (의미 필드 채워짐)
    ↓ executor_yb (Python)
changes_log, modified_file_paths, backup_paths
    ↓ validator (Python schema + LLM judge + retry loop)
final_response
```

---

## LLM 호출 수 비교 (현재 vs 신규)

| 시나리오 | 현재 | 신규 |
|---|---|---|
| 단순 update ("리드 atk +10") | 6+ 회 | intake(1) = **1회** |
| 조회 | 3회 (reader) | intake(1) = **1회** |
| 복합 create ("적에 슬라임 추가") | 6~7회 | intake(1) + profiler(1) + judge(1) = **3회** |
| 복합 + 1회 retry | 최대 8회 | intake(1) + profiler(1) + judge(1) + profiler(1) + judge(1) = **5회** |
| 실패 종료 | 최대 8회 | 3~5회 |

**평균 LLM 호출 40~70% 감소**. 주 원인: planner / executor_yb / validator schema 단계 / 응답 템플릿이 전부 결정론.

---

## 정확도 전망 (현재 대비)

| 요청 유형 | 현재 | 신규 | 주 근거 |
|---|---|---|---|
| 단순 CRUD | 높음 | 동등~↑ | SequenceMatcher 오매칭 제거 |
| 엔티티 이름 모호 | 중하 | ↑↑ | planner가 실제 파일을 보고 해소 |
| 조회 | 높음 | 동등 | `_REFERENCE_MAP` 로직 이식 |
| 복합/의존성 체인 | 중하 | ↑↑ | planner 그래프 결정론 |
| 새 의존성 패턴 | N/A | ↑ | `WRITE_DEPENDENCIES`에 노드만 추가 |
| Multi-turn coref | 낮음 | ↑↑ | intake가 history 기반 해소 |
| 의미적 엔티티 생성 | 없음 | **새 기능** | profiler가 전담 |
| 의미 판정 | 없음 | **새 기능** | validator judge가 전담 |

전체 정확도 기대값: **현재 대비 +10~20%**. 특히 multi-turn과 의존성 체인에서 두드러진다.

---

## 주요 의사결정 요약과 근거

### Router 제거
- 현재 router의 역할(action/chat/out_of_scope 분류)은 intake가 결합해서 처리한다.
- LLM 호출 1회 절약, multi-turn coref와 intent 분류가 같은 prompt에서 이뤄져 정합성 상승.

### Reader 제거
- reader의 존재 이유는 "현재 파이프라인이 너무 무거워서 만든 bypass"였다. 신규 파이프라인이 경량이라 bypass가 불필요.
- reader의 실질 자산(`_REFERENCE_MAP`)은 planner의 `WRITE_DEPENDENCIES`와 executor의 `describe_entity` 류 helper로 이식된다.

### Planner 유지 (단, 메커니즘 전면 교체)
- "Planner 없애고 agent_loop가 순서 판단" 안이 나왔으나 solar-pro3 기준으로 4단 의존성 체인을 안정적으로 계획할 수 없다고 판단.
- 대신 planner를 **LLM 없는 Python rule engine**으로 재설계. 순서 판단은 100% 결정론.

### 합성 tool(`equip_actor_armor` 등) 기각
- enumerative 설계라 새 패턴마다 함수가 필요. 유저 쿼리 다양성을 감당 못함.
- 대안: planner의 `WRITE_DEPENDENCIES`가 generative 의존성 해소 담당.

### Profiler 신설
- 현재 구조엔 없는 기능이다. "슬라임" → 의미적 traits 생성 같은 요구는 기존 파이프라인이 만들지 못한다.
- step 단위로 독립 호출 가능하게 설계해 validator의 partial retry와 자연스럽게 맞물린다.

### Step 이행도 검증 제거
- 현재 validator가 하던 기능이지만 executor의 거짓 성공(skip을 success로 보고) 때문에 무력했다.
- Semantic judge가 더 넓게 같은 문제를 덮는다.

### Semantic judge 추가
- "결과가 사용자 의도와 맞는가?"를 schema와 별개로 판단하는 LLM judge. operation 단위.
- confidence 비대칭 threshold로 false positive/negative 균형.

### Partial retry
- 실패한 step만 profiler 재호출. 전체 회귀 금지.
- retry가 "이전 노드로 회귀"가 아니라 "부분 패치"라는 다른 개념이 된다.
- validator 내부 루프로 구현, backedge 없음.

### 병렬 실행 연기
- 원칙은 맞지만 실제 이득이 작다. plan의 `depends_on` 인프라만 준비하고 실행은 v1 순차.

---

## 리스크

1. **`WRITE_DEPENDENCIES` 커버리지 공백**
   - 그래프에 빠진 `(file, field)` 조합은 planner가 선행조건을 못 만들고 통과시킨다.
   - 대응: reader `_REFERENCE_MAP`을 1:1로 이식하면 주요 필드 대부분 커버. Maps/CommonEvents/Troops 같은 덩어리는 MVP 밖으로 명시적 제외.

2. **profiler 프롬프트 품질이 결정적**
   - "슬라임 → 화염 취약"을 traits code 18(elementRate)로 매핑하는 지식을 얼마나 잘 압축하는지가 관건.
   - 대응: `traits_util` 참조표를 먼저 잘 만들고 profiler가 이를 import. 초반 튜닝에 시간 배정.

3. **judge의 over-strict / over-lax**
   - over-strict: "목걸이 줘" 요청에 description이 살짝 덜 "목걸이스럽다"는 이유로 reject.
   - over-lax: 완전히 엉뚱한 결과에도 match=True.
   - 대응: confidence threshold 비대칭 튜닝 (True: 0.7, False: 0.5). schema가 1차 방어선.

4. **retry 비수렴**
   - feedback이 구체적이지 않으면 profiler가 같은 실수 반복.
   - 대응: feedback 포맷을 엄격히 설계. "어느 step, 어느 필드, 어떤 기대, 현재 값"의 4요소 구조.

5. **Intake의 coref 실수**
   - history가 애매하면 resolved_input이 틀릴 수 있다.
   - 대응: scope=bulk거나 resolved_input이 user_input과 크게 다를 때 확인 프롬프트(선택). history는 직전 4턴만 slice.

6. **State 계약 정리 미포함**
   - 기존 `AgentState`의 drift 문제(`message_for_user` 등)는 이 실험 범위 밖. 신규는 새 state를 처음부터 깨끗하게 정의한다.

---

## 폴더 구조

```
new-agent/
  blueprint.md                    # 이 문서
  workflow.py                     # LangGraph 배선
  state.py                        # 신규 AgentState (얇게)

  nodes/
    intake.py                     # LLM: history + coref + operation 추출
    planner/
      __init__.py                 # planner 노드 entry
      dependencies.py             # WRITE_DEPENDENCIES 정적 그래프
      rule_engine.py              # 그래프 워크 + 실측
    profiler.py                   # LLM: profile_one(step, feedback)
    validator/
      __init__.py                 # validator 노드 entry
      schema_check.py             # pydantic 검증
      judge.py                    # LLM judge
      retry_loop.py               # partial retry 오케스트레이션
      feedback.py                 # feedback text 생성
      responder.py                # final_response 템플릿

  executor/                       # 기존 executor_yb.py를 분해 이식
    __init__.py                   # executor_yb() entry
    dispatch.py                   # target_file → handler 라우팅
    handlers/
      entity.py                   # 8개 entity JSON + System
      map.py                      # L1 metadata_ops + L4 content_ops stub
    utils/
      traits.py                   # traits/effects code 참조표 + helper
      locks.py                    # game_locks

  tools/                          # 이미 존재
    rpgmaker_crud.py
    entity_templates.py

  executor_yb.py                  # 원본 보존 (참조용, 배선에선 new executor/ 사용)
```

---

## 착수 순서

의존성 역방향으로 정렬.

1. **`executor/utils/traits.py`** — traits/effects code 참조표. profiler와 executor 양쪽이 기다린다. 프로젝트 전체의 single source of truth.
2. **`planner/dependencies.py`** — `WRITE_DEPENDENCIES` 초안. reader `_REFERENCE_MAP`을 쓰기 방향으로 뒤집는 작업. Map L1 엔트리 포함.
3. **`planner/rule_engine.py`** — 그래프 워크 + 실측. LLM 0회.
4. **`executor/` 핸들러 분리** — 기존 `executor_yb.py`의 `_dispatch_crud` 및 file-specific preprocessing을 `handlers/entity.py`로 이식. `handlers/map.py`는 L1 metadata_ops만 신규 작성, content_ops는 stub. `utils/locks.py`에 `game_locks` 이동.
5. **`nodes/profiler.py`** — `profile_one(step, feedback)`. `traits_util` 참조표를 prompt에 include. 초반 튜닝 시간 충분히 배정.
6. **`nodes/intake.py`** — history 기반 해소 + 분류 + operation 추출 프롬프트.
7. **`nodes/validator/`** — schema_check → feedback → judge → retry_loop → responder 순.
8. **`state.py` + `workflow.py`** — 배선 및 스모크 테스트.

---

## 팀 커뮤니케이션용 한 문단

> new-agent는 현재와 비슷한 5단 skeleton이지만 **LLM이 필요한 곳을 재배치**한다. 대화 맥락을 해소하는 intake, 엔티티 의미를 파악해 필드를 채우는 profiler, 사용자 의도와 결과의 일치를 판정하는 validator judge — 이 세 곳에만 LLM이 있다. 나머지 planner / executor / validator의 schema 검증 / final_response 작성은 전부 Python 결정론이다. Planner는 LLM으로 plan을 짜는 대신 RPG Maker 의존성 그래프(`WRITE_DEPENDENCIES`)를 Python으로 워크하고 실제 파일에서 선행조건을 실측한다. Executor는 기존 `executor_yb.py`를 entity handler와 map handler(L1 메타데이터만, L4 확장 interface 준비)로 분리해 재활용한다. Validator는 실패 시 "이전 노드로 회귀"가 아니라 **실패한 step만 profiler를 재호출해 부분 패치**한다. Reader와 router는 각각 planner와 intake에 흡수되어 별도 노드로 존재하지 않는다.

---

## 명시적으로 MVP 범위 밖

- Map L2/L3 (이벤트 배치, 인카운터 편집)
- Map L4 (타일맵 콘텐츠 생성) — 팀의 타일/이벤트 배치 작업 완료 후 `handlers/map.py::content_ops`에 접합
- 병렬 실행
- CommonEvents, Troops, Animations 같은 큰 덩어리 파일의 복잡한 편집
- 현재 `agent/`의 state drift 정리 (신규는 새 state로 시작)

---

## 추가 결정 사항

- **executor_yb.py 원본은 작업 완료 시점에 삭제한다.** 분해된 `executor/` 패키지가 그 자리를 대체한다.
- **모든 LLM 프롬프트는 `new-agent/prompts.py`에 모은다.** 프롬프트별로 함수 단위로 분리해서 작성한다.
- **테스트는 두 종류**:
  - `new-agent/test_interactive.py` — 사용자 입력을 받아 새 워크플로우를 즉석 실행하는 REPL.
  - `new-agent/test_pytest.py` — 사전 정의된 시나리오를 pytest로 자동 실행.
