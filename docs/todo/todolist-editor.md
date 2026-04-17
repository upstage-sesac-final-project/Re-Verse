# TODO List - Editor

## 우선순위 기준

- **P0**: 데이터 무결성 훼손 / 기본 시나리오 블로커 — 즉시 수정
- **P1**: 주요 기능 손상, 사용자 체감 높음 — 빠르게 수정
- **P2**: 운영/UX 열화, 장기적 누적 문제 — 여유 있을 때

## executor 경로 구분

- **v1 (MCP)**: `MCP_ENABLED=true` 시 executor가 MCP tool(`update_actor`, `addSkill` 등)을 호출. 실패 시 legacy manager로 fallback
- **v2 (structured/dispatch)**: `_executor_structured()` → `_execute_one_structured_step()`의 executor_v2 dispatch / handler 경로. MCP 미지원 조합에서 동작하며 `MCP_ENABLED=false`면 주 경로
- **공통**: 두 경로가 공유하는 로직 (snapshot, backup, changes_log, 파일 I/O 등)

---

## 버그 (기능은 있으나 잘못 동작)

### [MCP] create 함수들이 schema 필수 필드를 누락해 저장
- **우선순위**: P0
- **경로**: v1 (MCP)
- **현상**: MCP `add_*` tool로 생성한 엔티티가 pydantic schema 필수 필드를 빠뜨려 저장됨. 저장 후 검증 단계에서 실패, 게다가 파일은 invalid 상태로 남아 연쇄 실패
  | 대상 | 누락 필드 (확인됨) |
  |------|--------------------|
  | `addActor` → Actors.json | `battlerName`, (추정) `characterName`, `faceName` |
  | `addSkill` → Skills.json | `messageType` |
  | `addArmor` → Armors.json | (도메인 위반) `etypeId=1`로 저장 (Armor는 >=2) — 아래 profiler 이슈 참고 |
- **원인**: MCP create 함수 시그니처가 좁아서 profiler가 넘긴 값을 무시하거나, 필수 필드를 받지 않고 하드코딩 기본값도 schema를 만족하지 않음 (아래 "[MCP] create 함수들의 필드 누락" 이슈의 구체 재현)
- **위치**: `mcp/integration_MCP/handlers/database.ts` 전반
- **수정 방향**: 아래 "[MCP] create 함수들의 필드 누락" 이슈 수정 시 schema 필수 필드 먼저 채움. 임시 대응: executor create 분기에서 MCP 우회하고 JSON 직접 저장 경로로 전환

### [MCP] `update_*` tool이 entity id를 `undefined`로 전달 — 모든 update 실패
- **우선순위**: P0
- **경로**: v1 (MCP)
- **현상**: Plan의 `target_info.id`는 정확히 채워져 있는데 MCP 호출 단계에서 id가 누락됨. 로그: `update_weapon: Error: Weapon undefined not found`, `update_armor: Error: Armor undefined not found`, `update_class: Error: Class undefined not found`, `update_enemy: Error: Enemy undefined not found`
- **재현**: `장검 가격 300`, `마법사 직업 maxLevel 80`, `마왕 이름 대마왕`, `까마귀 공격력 80` 등 id 기반 update 요청 거의 전부
- **원인 추정**: executor의 MCP 바인딩 레이어가 `target_info.id` → MCP 파라미터 매핑 시 키 이름 불일치 (예: `id` vs `weaponId`/`armorId`) 또는 `target_info`에서 id를 꺼내지 않고 top-level에서 찾아 `undefined` 전달
- **위치**: `agent/editor/nodes/executor.py` MCP dispatcher, `agent/mcp_toolbox.py`
- **수정 방향**:
  1. executor → MCP 파라미터 빌더에 target_file별 id 필드 매핑 테이블 추가 (`Weapons.json → weaponId`, `Armors.json → armorId` 등)
  2. id 누락 시 MCP 호출 전에 guard로 FAIL 처리해 `undefined` 전달 원천 차단
  3. 현재는 legacy fallback도 "MCP_ABORT_NO_FALLBACK"으로 중단되므로 fallback 경로도 재점검

### [executor_v2/struct] Actors.update 핸들러가 미지원 필드를 silent drop
- **우선순위**: P1
- **경로**: v2 (structured)
- **현상**: `케이시의 최대 레벨을 70으로` 실행 시 로그에 `[struct_0] 지원하지 않는 필드 무시: maxLevel` 경고. 이번 배치에선 다른 update도 같이 있어 성공으로 끝났으나, `maxLevel` 단독 요청이면 빈 updates가 돼 silent no-op로 빠질 가능성
- **원인**: `_executor_structured()` 계열 Actors.update 핸들러가 허용 필드 화이트리스트를 좁게 잡고 있고, 리스트 밖 필드를 에러가 아닌 "무시"로 처리
- **위치**: `agent/editor/nodes/executor.py` structured Actors.update 분기
- **수정 방향**:
  1. 화이트리스트에 `maxLevel`, `initialLevel`, `nickname`, `profile`, `note` 등 schema 상 허용 필드를 모두 포함
  2. 미지원 필드는 drop 대신 step FAIL로 승격해 사용자에게 드러나게 함

### [executor_v2/handlers] `structured_classes_update` 핸들러 FAIL
- **우선순위**: P0
- **경로**: v2 (structured)
- **현상**: `도적 직업의 최대 레벨을 90으로` → `실패한 스텝들: ['step_0:structured_classes_update']`로 종료. MCP 경로에선 `update_class: Class undefined not found`로 가려져 있던 문제 — MCP 끄면 executor_v2 Classes 핸들러 자체가 FAIL 반환
- **원인 추정**: Classes.update structured handler 구현 누락 또는 `target_info.id`/`updates` 파싱 버그
- **위치**: `agent/editor/nodes/executor.py` `_execute_one_structured_step` Classes 분기
- **수정 방향**: handler 구현 완성 (Classes update 필드별 적용, 특히 `maxLevel`, `expParams`, `learnings` 등). MCP 제거 전 필수 수정

### [executor_v2/create] Armor 생성 시 trait `value` 대신 `value1` 키 사용
- **우선순위**: P0
- **경로**: v2 (structured create)
- **현상**: `"수정 갑옷" 방어구를 추가해줘` → `traits[18]`가 `{code: 61, dataId: 0, value1: 0.0}`로 저장. pydantic 실패: `value Field required`, `value1 Extra inputs are not permitted`
- **원인**: executor_v2 Armor create 경로의 trait 템플릿/프로파일러 산출물이 `value1` 키를 씀. schema는 `value` 단일 키를 요구
- **위치**: `agent/editor/nodes/executor.py` Armor create dispatch, 관련 프로파일러 출력 포맷
- **수정 방향**: trait 빌더에서 `value1` → `value`로 키 통일. 역사적 호환용이면 저장 시점에 정규화

### [mapgen/sample_selector] 카탈로그-디스크 동기화 깨짐 — 존재하지 않는 sample map 선정
- **우선순위**: P0
- **경로**: definition Step 4.6 (맵 추가 분기) → executor_v2 map handler
- **현상**: `"새로운 맵 묘비 만들어줘"` → Step 4.6의 `sample_selector` 가 `Map046.json` 을 best match (score=5.500) 로 선정 → executor 가 `storage/games/base_game/samplemaps/Map046.json` 읽으려 하나 **파일 없음** → `[map] sample map not found` → `UNSUPPORTED_STRUCTURED_STEP` 으로 실패. validator retry 도 같은 이유 실패
- **원인**: sample selector가 참조하는 카탈로그/인덱스(랭킹 대상 메타데이터) 와 실제 디스크 `samplemaps/` 폴더가 동기화되지 않음. 인덱스에는 Map046 이 등재돼 있으나 파일은 누락
- **위치**:
  - 호출: `agent/editor/nodes/definition.py` Step 4.6 맵 분기 (`[Step4.6] 맵 추가 요청 감지`)
  - 인덱스: `agent/generation/mapgen/sample_selector/` (selector + filter + ranker)
  - 디스크: `storage/games/base_game/samplemaps/`
- **수정 방향**:
  1. sample selector 기동 시 디스크 실재 파일과 카탈로그 교집합으로 후보 풀 좁히기 (없는 파일은 ranking 대상에서 제외)
  2. 또는 executor map handler 에서 file-not-found 시 후순위 후보로 자동 retry
  3. base_game/samplemaps 자체를 정비 — 인덱스에 등재된 모든 맵이 실제 존재하도록 보장
- **추가 잔존 이슈 (재현 시 추가 진단 필요)**: 이 실패 case 에서도 사용자 측에 "묘비가 2개 생김" 보고됨. executor 실패에도 MapInfos.json 에 항목 일부 쓰기가 일어났을 가능성. validator schema 검증 대상 아닌 파일이라 silent persistence 우려

### [executor_v2/create] State 생성 시 `stepsToRemove=0`으로 schema 위반
- **우선순위**: P1
- **경로**: v2 (structured create)
- **현상**: `"천둥의 화살" 스킬을 추가해줘` (카테고리가 States로 오라우팅된 이슈와 별개로) 생성 시 `stepsToRemove=0` 저장 → schema `>=1` 위반
- **원인**: executor_v2 State create의 기본값 테이블이 schema 도메인을 반영하지 않음 (Armor `etypeId=1`과 같은 계열 문제)
- **위치**: `agent/editor/nodes/executor.py` State create 기본값, 또는 프로파일러 State 템플릿
- **수정 방향**: 카테고리별 schema 도메인 제약을 기본값에 반영. pydantic schema에서 자동 추출 권장

### [definition/Step5] Step 5가 Step 1·2 결과를 무시하고 name/category를 재작성 — hallucination·오라우팅 근본 원인
- **우선순위**: P0
- **현상**: Step 5가 create 시 Step 1에서 추출된 `subject`와 Step 2에서 확정된 `category`를 존중하지 않고 자체적으로 다시 결정. 이름을 템플릿(`X I`, 다른 고유명사)으로 덮어쓰거나 target_file을 다른 카테고리로 바꿈
- **시도 & 결과** (적용됨):
  1. Step 5 프롬프트에 `[Step 1·2 결과 존중 — 최상위 규칙]` 블록 추가 (name literal 유지, category 그대로 매핑, 기능 추론은 세부 필드에만). `definition_prompt.py:STEP5_SYSTEM_PROMPT` 반영
  2. `apply_index_resolution` (구 game_index_resolve 노드)을 Definition 내부로 통합 → Step 5 LLM 출력 후 operation IR 단계에서 GameIndex 기반 file/id 교정 가능해짐
  - 검증 (동일 10건 재실행): name 보존 5/10 → 7/10, category 정답 7/10 → 9/10. 개선되나 완전 해결 아님 (`#3 치유 I`, `#10 근성의 반지` 잔존)
  - 새 부작용: `#1 수호의 방패`가 Step 5에서 System.json으로 오분류 → create 가드 때문에 reroute 못 해서 실패
- **남은 원인**:
  - 일부 케이스에서 LLM이 여전히 RPG 템플릿 이름으로 재생성 (프롬프트 규칙 무시)
  - Step 5 target_file 오분류 시 교정 경로 없음 (create 가드 때문)
- **다음 수정 방향**:
  1. 결정론 post-process 추가: `modifications[i].params.name`이 user_input에 substring으로 없으면 Step 1의 subject로 덮어쓰기
  2. create 가드 정밀화: Step 5가 내놓은 target_file이 Step 2 classifications의 category와 어긋나면 classifications 기반으로 교정 허용 (create일 때도)
  3. Step 4.6 (코드 기반 IR) 커버리지 확장 → Step 5 LLM에 도달하는 create 케이스 자체를 줄임

### [definition/전처리] user_input에서 따옴표가 strip되어 Step 1 도달 — quote-preservation 가이드 무력화
- **우선순위**: P1
- **현상**: 진단 로그에서 `user_input='용맹의 반지 장신구를 만들어줘'` 처럼 **따옴표가 이미 제거된 채** Step 1에 도달. 원래 입력은 `"용맹의 반지"라는 장신구를 만들어줘`였음
- **원인**: router 노드가 LLM의 `resolved_input`으로 `state.user_input`을 덮어쓰는데 (`router.py:89`), coref 해소 과정에서 LLM이 따옴표를 제거하며 재생성
- **시도 & 결과** (적용됨):
  - router prompt에 `[resolved_input 원문 보존 규칙]` 블록 추가 (따옴표·대괄호 원문 보존, 치환 금지). `router_prompt.py` 반영
  - 검증: 일부 케이스는 따옴표 보존되나 여전히 strip되는 케이스 있음. LLM 준수 불안정
- **다음 수정 방향**:
  1. 결정론 대안: `state.user_input`을 원본 그대로 보존하고 coref 해소 결과는 별도 필드(예: `resolved_input`)로 저장. downstream 노드가 어느 쪽을 읽을지는 목적별로 분리
  2. 또는 router 후처리에서 원문의 따옴표 구간을 resolved_input에 재주입

### [definition/Step1] subject 경계 오류 — 따옴표 없이 받은 입력에서 category 지시어까지 포함
- **우선순위**: P1
- **현상**: "용맹의 반지 장신구를 만들어줘" (따옴표 제거된 상태) → `subject='용맹의 반지 장신구'`로 추출
- **시도 & 결과** (적용됨):
  - Step 1 프롬프트에 `[고유명사 보존 — 최상위 규칙]` 추가 (따옴표/대괄호 literal 유지, 검증 절차 포함). `definition_prompt.py:STEP1_SYSTEM_PROMPT` 반영
  - 효과: 따옴표 보존이 router에서 전달되면 Step 1 subject 경계 문제 대부분 자연 해결. 그러나 따옴표가 이미 strip된 입력에선 경계 실수 잔존
- **다음 수정 방향**:
  1. 상위 "[definition/전처리] 따옴표 strip" 이슈 먼저 해결하면 이 이슈도 함께 해결됨
  2. 추가 가드: Step 1 프롬프트에 "subject 뒤의 category 지시어(무기/아이템/방어구/스킬/상태/직업/적/액터/장신구)는 subject에서 제외" 명시 규칙 추가

### [definition] 고유명사 hallucination — 입력 `name`을 임의 재생성 (Step5 재작성 이슈의 부분 현상)
- **우선순위**: P0 (상위 "Step5 재작성" 이슈와 함께 해결)
- **현상** (이전 배치 기준):
  - `"생명의 반지"라는 방어구` → `subject='근성의 반지'`
  - `"얼음 창"이라는 무기` → `subject='얼음 I'`
  - `"회복초" 회복 아이템` → `subject='회복 I'`
- **진단**: Step 1은 정상, Step 5가 덮어씀. 위 "[definition/Step5] Step 5 재작성" 이슈의 증상
- **시도 & 결과**:
  - Step 1 프롬프트에 name 보존 규칙 + positive/negative example 추가 → Step 1 출력은 개선(`얼음 활`, `수면초` 등 보존). **최종 결과 개선 없음** (Step 5가 재작성하기 때문)
  - negative example ("생명의 반지"→"근성의 반지") 제거 시 동일 실패 재현. contamination이 아닌 LLM prior로 추정
- **수정 방향**: 상위 "[definition/Step5] Step 5 재작성" 이슈로 통합 해결

### [definition/Step5] 카테고리 오인 — Step 2가 정해도 Step 5가 재라우팅
- **우선순위**: P0 (상위 "Step5 재작성" 이슈와 함께 해결)
- **현상**:
  - `"얼음 활"이라는 무기` → Step 2 category=Weapon ✓ → **Step 5가 Skills.json으로 재라우팅** ❌
  - `"수면초"라는 회복 아이템` → Step 2 category=Item ✓ → **Step 5가 Skills.json으로 재라우팅** ❌
- **진단**: Step 2는 개선된 프롬프트로 category indicator를 정확히 신뢰("'무기' 지시어 기반" reason 확인). 그러나 Step 5가 이를 무시하고 target_file을 다시 결정
- **시도 & 결과**:
  - Step 2 프롬프트에 category indicator 우선 규칙 + 합성어 예시 추가 → Step 2 출력은 대부분 정답. **최종 결과는 일부만 개선** (Step 5가 재라우팅하는 케이스 여전)
- **수정 방향**: 상위 "[definition/Step5] Step 5 재작성" 이슈로 통합 해결

### [definition] 복합/곡선 필드 수정 지시 미지원 — `expParams` 등
- **우선순위**: P1
- **현상**: `기사 직업의 경험치 곡선을 더 완만하게 조정해줘` → `execution_plan 비어있음`으로 조기 실패. `expParams`처럼 4개 수치로 구성된 곡선 파라미터, `params` 배열 같은 복합 필드에 대한 상대적 조정("더 완만하게", "가파르게", "균형 잡히게")을 지시로 번역하지 못함
- **원인**: Definition이 단일 scalar 필드 수정만 전제. 곡선/배열 필드의 의미(완만 vs 가파름, 저/고레벨 성장률) 매핑 로직 없음
- **관련 이슈**: 기존 "[definition] 상대값 처리 불가"의 복합 필드 변형
- **수정 방향**:
  1. Classes.expParams, params 배열 같은 주요 복합 필드에 대한 의미 ↔ 수치 매핑 프리셋 (예: "완만" → basis 증가, extra 감소)
  2. 최소한 "지원하지 않는 지시 형태"로 명확히 사용자에게 알리고 종료 — 현재는 내부 에러 문구 노출

### [definition] conversation_history 오염 — 연속 턴에서 직전 subject로 shift
- **우선순위**: P0
- **현상**: 배치 테스트에서 `장검의 가격을 300으로 바꿔줘` → subject='미스릴 갑옷 방어구' (직전 턴 주제)로 오추출, 다음 턴 `물약의 설명을...` → subject='장검' price 300 (또 직전 턴 주제)로 오추출. 입력 문장과 무관하게 **이전 턴의 subject + 현재 턴의 field/value**가 섞인 operation이 만들어짐
- **원인 추정**: Definition Step 1이 conversation_history를 프롬프트에 넣으면서 현재 `user_input`과 history 간 경계를 명확히 구분하지 못함. LLM이 history 속 엔티티를 현재 입력의 subject로 착각
- **재현**: 연속된 수정 요청 2턴 이상, 주제(대상)가 턴마다 다를 때
- **위치**: `agent/editor/nodes/definition.py` Step 1, `agent/editor/prompts/definition_*` 프롬프트
- **수정 방향**:
  1. Step 1 프롬프트에서 current turn과 history를 명확한 구분자/역할로 분리하고 "subject는 현재 turn에서만 추출" 가이드 추가
  2. history는 coreference 해소가 필요한 경우에만 참조하도록 conditional 주입 (대명사/생략 감지 시에만)
  3. Step 1 출력 후 현재 `user_input`에 subject 토큰이 등장하는지 post-check 추가 — 없으면 재추출

### [profiler] 엔티티 맥락(직업/역할) 반영 부족 — 품질 이슈
- **우선순위**: P2
- **경로**: 공통 (profiler → v2 create)
- **현상**: `"리드라는 액터 추가해줘. 직업은 힐러"` → actor 생성은 성공하지만, profiler가 채운 traits/params/equips가 힐러 맥락과 무관함. judge가 `match=False, confidence=0.60, reason="힐러 직업과 관련된 능력치·스킬이 전혀 반영되지 않았으며, 공격 속도 보정 등 부적절한 trait가 포함"` 로 지적
- **원인**: profiler user prompt에 이름만 전달되고, **classId/직업명/역할** 같은 맥락이 프롬프트에 명시적으로 녹아 있지 않거나 LLM이 무시함. 결과적으로 모든 신규 actor가 비슷한 일반값으로 채워짐
- **위치**: `agent/editor/prompts/profiler_prompt.py` (user prompt 빌더), `agent/editor/nodes/profiler.py` (step 전달)
- **수정 방향**:
  1. profiler user prompt 에 `classId` 해소된 직업명(예: "힐러"), 사용자 원문 의도("…직업은 힐러")를 명시적으로 포함
  2. 카테고리별 전형(healer/tank/dps) 기본 trait 템플릿을 schema/constants 로 두고 LLM은 이를 참고·조정만 하게 가이드
  3. 테스트: judge 기준 confidence >= 0.8 으로 통과하는지 회귀 검증 (`힐러/탱커/마법사` 각 시나리오)

### [profiler] 카테고리별 기본값 테이블 오류 — Armor `etypeId=1`
- **우선순위**: P1
- **현상**: `"미스릴 갑옷"이라는 방어구를 만들어줘` → 생성된 Armor 엔트리가 `etypeId=1`. schema 검증 실패 (Armor는 `etypeId >= 2`, 1은 무기 슬롯 타입)
- **원인**: profiler 또는 MCP `addArmor`의 기본값 테이블이 Weapon/Armor를 구분하지 못하고 공용 default=1 사용
- **위치**: profiler 카테고리별 기본값, `mcp/integration_MCP/handlers/database.ts` `addArmor`
- **수정 방향**: 카테고리별 schema 도메인 제약(`etypeId`, `atypeId`, `wtypeId` 등)을 반영한 기본값 테이블 정비. pydantic schema에서 min/max를 읽어 자동 추출하는 방향도 가능

### [definition] `update_all`에 target/updates가 비어도 silent success — Definition 차단 완료
- **우선순위**: P0
- **현상**: `독 상태이상의 지속 턴을 5로` → `States.json.update_all`, `target_info={"updates": {}}` → executor OK, validator 참고만 남김, success=True. 실제로는 States.json 아무것도 안 바뀜. `침묵 아이콘 13`, `분노 10턴`도 동일
- **시도 & 결과** (적용됨):
  - Definition에 **Step 9: operation_tuples degenerate 검증** 추가 (`_validate_operation_tuples`)
  - 판정 기준: action이 update/delete/read인데 subject.id·name 모두 없음 OR updates 페이로드 비었음
  - 적중 시 `params_sufficient=False`, `message_for_user` + `final_response` 에 사용자 안내 설정 ("'독 상태이상'을(를) States.json에서 찾지 못했습니다" 등)
  - 검증: `독/침묵/분노 상태이상` 3케이스 모두 execution 도달 전 차단. 사용자에게 명확한 응답 노출
- **잔여 이슈**:
  - `침묵 상태이상의 아이콘을 13번으로` 는 별개 버그(execution_plan 비어있음)로 Planner 단에서 실패 — 아래 "[definition/planner] execution_plan 비어있음" 이슈 참고
  - Executor `update_all({})` 자체는 여전히 no-op 허용. Definition이 뚫리는 케이스에 대비해 B 안전망 (executor guard) 추가 권장
- **후속 권장**:
  1. Executor `update_all` 핸들러 입구에 empty updates FAIL guard (안전망)
  2. Validator semantic 체크에서 "작업만으로는 … 확인할 수 없다" 계열 → success=False 승격

### [game_index_resolve] create 시 재라우팅 버그 — 부분 해결
- **우선순위**: P1
- **상태**: `_resolve_subject`에 `action == 'create'` 가드 추가 (`game_index_resolve.py`). 신규 생성 시 전체 파일 검색으로 인한 file 재라우팅 차단. "적 슬라임 만들어줘" 같은 기본 케이스 해결
- **남은 부작용**: create 가드가 너무 넓어서 Step 5 LLM이 잘못된 target_file을 내놓은 경우(예: "수호의 방패" → System.json)에도 교정이 안 됨. 아래 "[definition/Step5]" 이슈에서 classifications 기반 sanity check 추가로 보완 예정
- **재현 필요**: "적 슬라임" 케이스 회귀 테스트

### [definition] System.json 수정 대상을 Actors.json bulk/delete로 오인
- **우선순위**: P1
- **현상 1**: "주인공 목록 첫번째를 프리실라로 바꿔줘" → System.json의 `partyMembers` 수정이어야 하는데, definition Step 5가 Actors.json bulk update 20개로 해석
- **현상 2**: "로자를 파티에서 빼줘" → System.json `partyMembers` 배열에서 해당 id 제거여야 하는데 `Actors.json.delete`로 해석, 액터 자체가 삭제됨 (success=True로 보고됨)
- **원인**: definition Step 5 LLM이 "주인공 목록", "파티에서 빼다" 같은 파티/시스템 어휘를 Actor 조작으로 오해
- **수정 방향**: definition prompt에 "주인공 목록/파티 구성/파티에서 빼다/추가하다 → System.json partyMembers" 매핑 가이드 추가. 또는 Step 4.6에서 "파티" 관련 키워드를 System.json으로 라우팅

### [definition] "X의 Y" 패턴에서 category가 Y가 아닌 X로 오인
- **우선순위**: P1
- **현상**: `"용사의 검"이라는 무기를 추가해줘` → subject='용사'로 추출되어 `Actors.json.create`로 plan됨. 리드의 `nickname='용사'`와 매칭되며 기존 리드 전체 필드를 복제한 신규 Actor 생성까지 진행됨
- **원인**: Definition Step 1에서 "용사의 검"에서 `subject`를 "용사"로 끊음 ("의" 소유격 앞까지). category 분류(Step 2)도 문장 내 "무기" 단서를 압도하지 못함. Step 4의 RAG/SequenceMatcher가 "용사" → 리드.nickname으로 fuzzy 매칭해 Actors로 굳어짐
- **위치**: `agent/editor/nodes/definition.py` Step 1 / Step 2 프롬프트, `agent/editor/prompts/definition_*`
- **수정 방향**:
  1. Step 1 프롬프트에 "A의 B" 패턴에서 category 단서(무기/방어구/아이템/스킬 등)가 문장에 있으면 B를 subject로 우선 선택하도록 가이드
  2. Step 2 category 분류가 문장 내 카테고리 키워드("무기", "방어구" 등)를 signal로 받도록 입력 확장
  3. Step 4 SequenceMatcher 매칭이 category 확정 후에만 동작하도록 순서 조정 (category mismatch면 기존 엔티티 매칭 skip)

### [definition/planner] 수정 요청이 `execution_plan` 비어있음으로 조기 실패
- **우선순위**: P1
- **현상**: `고블린 최대 HP 500`, `검사 직업 HP 1.5배` 등 평범한 수정 요청이 `[Planner] operation_tuples 비어 있음 / execution_plan이 비어있음` 로그와 함께 guard FAIL로 종료. retry도 시도되지 않고 final_response에 "재시도 대상 없음" 그대로 노출
- **원인 추정**:
  1. `고블린 최대 HP 500` — Enemies에서 이름 매칭은 되지만 Definition Step 5가 params 필드(`mhp` 등)를 찾지 못해 operation을 비워서 반환
  2. `검사 직업 HP 1.5배` — 상대값 처리 실패 (아래 "[definition] 상대값 처리 불가" 이슈와 동일 계열). 다만 이 케이스는 `params_sufficient=True`지만 operation 자체가 빈 상태
- **수정 방향**:
  1. planner에서 `operation_tuples`가 비면 즉시 사용자에게 "어떤 필드를 바꿀지 명시" 안내 final_response 생성 (현재는 내부 에러 문구 그대로 노출)
  2. Definition Step 5가 빈 op을 반환할 수 있는 경로를 `params_sufficient=False` + `message_for_user` 경로로 통합
  3. 상대값 케이스는 기존 상대값 이슈와 함께 해결

### [executor/MCP] profiler → executor 필드 전달 경로 불일치
- **우선순위**: P1
- **경로**: v1 (MCP/legacy) 주, v2는 전체 반영으로 OK
- **현상**: profiler가 채운 필드가 최종 게임 데이터에 반영되지 않는 경우가 있음
- **원인**: executor 내 경로별로 profiler 결과 반영 수준이 다름
  | 경로 | profiler 필드 반영 |
  |------|-------------------|
  | MCP 성공 | **부분만** — MCP 서버가 받는 필드만 반영 |
  | 레거시 매니저 fallback | **부분만** — Skills의 경우 4개만 전달 |
  | executor_v2 dispatch fallback | **전체 반영** |
  | JSON 직접 저장 (Items/Enemies) | **전체 반영** |
- **수정 방향**: MCP create 확장(아래 이슈)으로 동시 해결, 또는 create는 MCP 우회

### [state/validator] changes_log 누적 reducer 이슈
- **우선순위**: P2
- **경로**: 공통
- **현상**: `changes_log: Annotated[list, add]` reducer로 retry 시 이전 로그가 누적됨. validator/judge가 step_id별 최신 로그만 봐야 하는데 명시적인 헬퍼가 없음
- **위치**: `agent/editor/state.py`, `agent/editor/nodes/validator/`
- **수정 방향**: `step_id`별 마지막 로그만 추출하는 헬퍼 함수 (`get_latest_per_step`) 명시적 도입. validator/judge에서 일관되게 사용

---

## 기능 미구현 (필요한 기능이 아직 없음)

### [executor] schema 검증 실패 시 파일 롤백 없음 — 오염 전파
- **우선순위**: P0
- **경로**: 공통 (v1·v2 모두 해당)
- **현상**: `"카엘" 액터 추가` → MCP `addActor`가 `battlerName` 없이 엔트리 추가 → 파일 저장 후 schema 검증 단계에서 실패. 파일은 **invalid 상태로 남고**, 이후 `게일 직업을 마법사로 바꿔줘`, `용사의 검 무기 추가` 등 Actors.json을 건드리는 모든 후속 요청이 동일 schema 에러로 연쇄 실패
- **원인**: executor가 MCP/legacy 실행 성공 후 파일 쓰기까지 마친 뒤 validator에서 schema 실패를 감지해도 backup으로 되돌리지 않음. 실행 로그는 `OK`인데 파일은 망가진 상태로 게임 세션에 계속 남음
- **재현**: game_001에서 `"카엘"이라는 새 액터를 추가해줘` 1회 → 이후 임의의 Actor 수정 요청 전부 실패
- **수정 방향**:
  1. validator에서 schema 실패 판정 시 해당 run의 `backup_paths`로부터 자동 롤백하는 경로 추가
  2. 또는 executor가 파일을 쓰기 전에 in-memory에서 schema dry-run을 먼저 돌리고 실패 시 write 자체를 skip

### [MCP] create 함수들의 필드 누락 — MCP 서버 구현
- **우선순위**: P0
- **경로**: v1 (MCP)
- **현상**: profiler가 traits, effects, damage 등을 채워서 넘기지만, MCP로 생성된 엔티티에는 기본값만 들어감
- **원인**: `mcp/integration_MCP/handlers/database.ts`의 create 함수들이 소수 파라미터만 받고 나머지를 하드코딩
  | 함수 | 받는 필드 | 무시되는 필드 |
  |------|----------|-------------|
  | `addSkill` | name, mpCost, tpCost, scope, occasion (5개) | damage, effects, traits, iconIndex, description 등 16개 |
  | `addActor` | name, classId, initialLevel, maxLevel (4개) | traits, nickname, note, profile, equips 등 8개 |
  | `addItem` | name, price, consumable, scope, occasion (5개) | damage, effects, iconIndex, description 등 12개 |
  - `addWeapon`, `addArmor`, `addEnemy`, `addClass`, `addState`는 MCP에 구현 자체가 없음
- **수정 방향 (택 1)**:
  1. **(권장) MCP create 함수 확장**: 전달받은 모든 필드를 반영하도록 `database.ts` 수정
  2. **create는 MCP 우회**: create 액션은 executor_v2 dispatch로 직접 처리. MCP는 update/query에만 사용
  3. **create 후 update 2-step**: MCP create → MCP update로 나머지 필드 채움

### [definition] 상대값("절반", "2배" 등) 처리 불가
- **우선순위**: P1
- **현상 1 (definition 조기 종료)**: "마왕의 공격력을 절반으로 낮춰줘" → Step 5 LLM이 구체 수치 변환 실패 → `params_sufficient=False` → `__end__`로 바로 종료
- **현상 2 (빈 updates 통과)**: 같은 입력이 LLM 비결정성으로 `params_sufficient=True` + `updates: {}` 로 넘어감 → planner가 `update_all` 생성 → executor UNSUPPORTED
- **원인**: 현재 파이프라인에 "현재 게임 데이터를 읽어서 상대값을 절대값으로 변환"하는 로직이 없음
- **수정 방향**:
  1. definition Step 5 또는 game_index_resolve에서 대상 entity의 현재 데이터를 읽어 프롬프트에 주입 → LLM이 "공격력 100 → 50" 계산 가능
  2. planner에서 updates가 비어있으면 error step으로 처리 (현상 2 방지)

### [router/definition] 코어퍼런스 해소 실패
- **우선순위**: P1
- **현상**: "방금 만든 애 직업을 무술가로 바꿔줘" → router의 resolved_input이 원본 그대로 넘어옴 → definition이 entity 못 찾음 → planner가 error step 생성 → executor UNSUPPORTED
- **원인**: router prompt가 "방금", "직전", "그", "이것" 같은 대명사/시간 표현을 conversation_history와 매칭하지 못함
- **위치**: `agent/editor/prompts/router_prompt.py` (coref resolution 가이드), `agent/editor/nodes/router.py`
- **수정 방향**:
  1. router prompt에 "방금/직전/그" 표현 처리 가이드 강화. 직전 턴의 생성/수정 대상을 resolved_input에 명시적으로 치환
  2. definition Step 1 prompt에도 conversation_history 기반 보정 추가

### [executor] backup 파일 무한 누적
- **우선순위**: P2
- **경로**: 공통
- **현상**: 매 실행마다 `Actors.json.20260413_HHMMSS.bak` 등 백업 파일이 `_backups/` 디렉토리에 쌓이고 정리되지 않음. 장기적으로 디스크 점유
- **위치**: `executor.py` `_create_backups()` 함수
- **수정 방향**: 게임별로 최근 N개(예: 10개)만 유지하는 cleanup 로직 추가. 또는 N일 경과 시 자동 삭제

### [executor] snapshot 디렉토리 누적
- **우선순위**: P2
- **경로**: 공통
- **현상**: 매 실행마다 `.executor_snapshots/<run_id>/` 디렉토리 생성되고 정리되지 않음
- **위치**: `executor.py` 스냅샷 로직
- **수정 방향**: 실행 성공 후 즉시 삭제 (실패 시만 보존), 또는 N일 경과 시 cleanup

---

## 해결됨

### ~~[MCP] 서버 cwd 경로 문제 (Windows)~~ ✅
- 절대경로로 변경하여 해결

### ~~[executor] MCP 미지원 step → executor_v2 dispatch fallback 추가~~ ✅
- UNSUPPORTED 반환 직전에 dispatch_step 시도 추가

### ~~[executor] 커스텀 업데이트 키(_equip 등) → MCP skip, v2 직행~~ ✅
- MCP 호출 전 커스텀 키 guard 추가

### ~~[executor] guard 경로 changes_log 필수 필드 누락~~ ✅
- step_id, tool_name, success 필드 추가

### ~~[workflow] `game_index_resolve` 노드를 Definition 내부로 통합~~ ✅
- `game_index_resolve.py`의 async 노드 래퍼 제거 → `apply_index_resolution(ops, game_id)` 순수 함수만 남김
- `definition.py`가 Step 4.6 early return 직전 + LLM 경로 마지막 operation IR 변환 직후에 `apply_index_resolution` 호출 (두 경로 통합)
- `workflow.py`에서 노드/엣지 제거, `definition → planner` 직결 (노드 수 8 → 7)
- 부가: `_resolve_subject`에 `action == 'create'` 가드 추가 → "적 슬라임 만들어줘" 같은 create 재라우팅 버그 차단 (단 부작용 있음, 위 "[game_index_resolve]" 참조)

---

## 리팩터링

### [전체] 노드 패키지화 (executor 제외)
- **우선순위**: P2
- **범위**: executor를 제외한 전 노드를 1노드 = 1패키지 구조로 전환
- **planner**: `planner_v2/` → `planner/` (v2 접미사 제거). **승인 완료**
- **definition**: `definition.py` (1290줄) → `definition/` 패키지 4분할
- **단일 파일 → 패키지**: router, reader, profiler, synthesizer, game_index_resolve
- **상세**: `refactor_plan.md` 참고

### [executor] 단일 파일 분할 (2900줄)
- **우선순위**: P2
- **경로**: 공통 (v1·v2 분리 선행)
- **현상**: `executor.py`가 2,944줄 단일 파일. MCP 인터셉트 + 레거시 매니저 + 구조화 분기 + 스냅샷 + 로그 정규화가 한 파일에 공존
- **위치**: `agent/editor/nodes/executor.py`
- **수정 방향**: refactor_plan.md의 executor/ 패키지 구조로 분할 (`structured.py`, `mcp.py`, `legacy_handlers.py`, `dispatch.py`, `handlers/`, `utils/`)
- **선행 조건**: executor 담당자와 협의 필요

### [definition] step 구조 간소화
- **우선순위**: P2
- **현상**: 12 step (소수점 7개) — 가독성/추적 어려움
- **위치**: `agent/editor/nodes/definition.py`
- **수정 방향**: 5 step 구조로 통합 (Step 1+2 LLM 통합, 보정 단계 통합 등)
- **상세**: `definition_simplify.md` 참고

---

## 최적화

### [definition] LLM 호출 횟수 축소
- **우선순위**: P1
- **현상**: definition 노드에서 최소 3회 LLM 호출 (Step 1 추출 + Step 2 분류 + Step 5 명세). bulk 조건 시 Step 5 재시도까지 4회
- **수정 방향**:
  1. Step 1+2 통합: 추출과 분류를 하나의 structured output으로 합침 → 1회로 감소
  2. Step 4.6 성공률 향상: 코드 기반 IR 생성이 더 많은 케이스를 커버하면 Step 5 LLM 호출 자체를 건너뜀
  3. Step 2 분류 결과 캐싱: 동일 이름에 대한 분류를 게임 세션 내에서 재사용

### [router] 대화 이력 토큰 비용 증가
- **우선순위**: P2
- **현상**: conversation_history를 프롬프트에 넣기 때문에 대화가 길어지면 토큰 비용이 선형 증가
- **수정 방향**: 최근 N턴 슬라이딩 윈도우 (현재 5턴) 유지하되, 요약 압축 적용 검토

### [profiler] create step별 LLM 호출
- **우선순위**: P2
- **현상**: create step마다 LLM 1회 호출. 여러 엔티티 동시 생성 시 호출 횟수가 선형 증가
- **수정 방향**:
  1. 같은 target_file의 create step을 배치 처리 (1회 LLM으로 여러 엔티티 프로파일링)
  2. 스키마 기반 기본값 템플릿으로 LLM 없이 처리할 수 있는 필드 비율 늘리기

### [profiler] RAG 도입 — 유사 엔티티 참고 생성
- **우선순위**: P2
- **현상**: profiler가 LLM으로 필드를 채울 때, 같은 카테고리의 기존 엔티티를 참고하지 않아 품질이 일관되지 않음. "파이어볼 만들어줘"에서 매번 다른 damage formula/effects 생성 가능
- **수정 방향**: 신규 생성 시 같은 target_file의 기존 엔티티 1~2개를 RAG로 검색해 프롬프트 컨텍스트로 주입
  - 인덱싱 대상: 현재 게임의 모든 엔티티 (name + description + note + 주요 필드)
  - 검색 키: 신규 엔티티의 name + description
  - 적용 위치: `profile_one()` 의 LLM 호출 직전
- **효과**: 출력 일관성 향상, hallucination 감소, 장르 톤 자동 유지 (판타지/SF 등 게임마다)
- **확장 가능성**: 안정화 후 게임 용어집(외부 사전) 추가 → definition Step 2 분류 보강용으로도 활용

### [executor] step 순차 실행
- **우선순위**: P2
- **경로**: 공통
- **현상**: 병렬 가능한 조회 step도 순차 실행. depends_on이 없는 step끼리는 병렬화 가능
- **수정 방향**: depends_on 기반 의존성 그래프에서 동시 실행 가능한 step을 asyncio.gather로 병렬화

### [executor] 스냅샷/백업 매 실행마다 생성
- **우선순위**: P2
- **경로**: 공통
- **현상**: 매 executor 실행 시 대상 파일 전체 스냅샷 + 백업 생성. 파일 수에 비례해 I/O 증가
- **수정 방향**: 변경 예정 파일만 선택적 백업. 또는 copy-on-write 방식으로 실제 변경 시에만 백업

### [validator] judge LLM 호출 operation별 1회
- **우선순위**: P2
- **현상**: operation_tuples 개수만큼 judge LLM 호출. 5개 operation이면 5회 호출
- **수정 방향**:
  1. 여러 operation을 하나의 judge 프롬프트에 배치 처리
  2. 단순 create 성공은 LLM judge 없이 결정론으로 통과 처리 (changes_log의 success + entity 존재 확인만)

### [synthesizer] LLM 제거 후 템플릿 품질
- **우선순위**: P2
- **현상**: 결정론 템플릿 응답이 다양성이 부족할 수 있음. "요청을 성공적으로 처리했습니다" 반복
- **수정 방향**: 템플릿 변형 추가 (action 종류별, 대상 종류별 문구 분기). 필요 시 경량 LLM 1회로 자연스러운 응답 생성 옵션
