# TODO List - Editor

## 버그 / 기능 이슈

### [game_index_resolve] create 시 재라우팅 버그
- **현상**: "적 슬라임 만들어줘" → Definition이 `Enemies.json` create로 정확히 내보냄 → `game_index_resolve`가 `Enemies.json → Skills.json`으로 재라우팅 → 스킬 "공격"이 생성됨
- **원인**: `_resolve_subject`가 `subject.id`가 없으면 전체 파일 검색(`find_entity`)을 실행. 신규 생성(create)인데도 기존 엔티티를 찾으려 해서 fuzzy match로 엉뚱한 파일의 엔티티에 매칭, file을 덮어씀
- **재현**: 빈 프로젝트에서 "적 슬라임 만들어줘" — 슬라임만 재현됨 (다른 이름은 정상)
- **수정 방향**: create action일 때 `_resolve_subject`의 전체 검색 + 재라우팅을 skip하거나, operation의 action이 create이면 id resolve 자체를 건너뛰기

### [definition] 상대값("절반", "2배" 등) 처리 불가
- **현상 1 (definition 조기 종료)**: "마왕의 공격력을 절반으로 낮춰줘" → Step 5 LLM이 구체 수치 변환 실패 → `params_sufficient=False` → `__end__`로 바로 종료
- **현상 2 (빈 updates 통과)**: 같은 입력이 LLM 비결정성으로 `params_sufficient=True` + `updates: {}` 로 넘어감 → planner가 `update_all` 생성 → executor UNSUPPORTED
- **원인**: 현재 파이프라인에 "현재 게임 데이터를 읽어서 상대값을 절대값으로 변환"하는 로직이 없음
- **수정 방향**:
  1. definition Step 5 또는 game_index_resolve에서 대상 entity의 현재 데이터를 읽어 프롬프트에 주입 → LLM이 "공격력 100 → 50" 계산 가능
  2. planner에서 updates가 비어있으면 error step으로 처리 (현상 2 방지)

### [definition] System.json 수정 대상을 Actors.json bulk로 오인
- **현상**: "주인공 목록 첫번째를 프리실라로 바꿔줘" → System.json의 `partyMembers` 수정이어야 하는데, definition Step 5가 Actors.json bulk update 20개로 해석
- **원인**: definition Step 5 LLM이 "주인공 목록" = "Actor 전체"로 오해
- **수정 방향**: definition prompt에 "주인공 목록/파티 구성 → System.json partyMembers" 매핑 가이드 추가. 또는 Step 4.6에서 "주인공 목록" 키워드를 System.json으로 라우팅

### [MCP] create 함수들의 필드 누락
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

### [router/definition] 코어퍼런스 해소 실패
- **현상**: "방금 만든 애 직업을 무술가로 바꿔줘" → router의 resolved_input이 원본 그대로 넘어옴 → definition이 entity 못 찾음 → planner가 error step 생성 → executor UNSUPPORTED
- **원인**: router prompt가 "방금", "직전", "그", "이것" 같은 대명사/시간 표현을 conversation_history와 매칭하지 못함
- **위치**: `agent/prompts/router_prompt.py` (coref resolution 가이드), `agent/graph/nodes/router.py`
- **수정 방향**:
  1. router prompt에 "방금/직전/그" 표현 처리 가이드 강화. 직전 턴의 생성/수정 대상을 resolved_input에 명시적으로 치환
  2. definition Step 1 prompt에도 conversation_history 기반 보정 추가

### [executor] backup 파일 무한 누적
- **현상**: 매 실행마다 `Actors.json.20260413_HHMMSS.bak` 등 백업 파일이 `_backups/` 디렉토리에 쌓이고 정리되지 않음. 장기적으로 디스크 점유
- **위치**: `executor.py` `_create_backups()` 함수
- **수정 방향**: 게임별로 최근 N개(예: 10개)만 유지하는 cleanup 로직 추가. 또는 N일 경과 시 자동 삭제

### [executor] snapshot 디렉토리 누적
- **현상**: 매 실행마다 `.executor_snapshots/<run_id>/` 디렉토리 생성되고 정리되지 않음
- **위치**: `executor.py` 스냅샷 로직
- **수정 방향**: 실행 성공 후 즉시 삭제 (실패 시만 보존), 또는 N일 경과 시 cleanup

### [state/validator] changes_log 누적 reducer 이슈
- **현상**: `changes_log: Annotated[list, add]` reducer로 retry 시 이전 로그가 누적됨. validator/judge가 step_id별 최신 로그만 봐야 하는데 명시적인 헬퍼가 없음
- **위치**: `agent/graph/state.py`, `agent/graph/nodes/validator/`
- **수정 방향**: `step_id`별 마지막 로그만 추출하는 헬퍼 함수 (`get_latest_per_step`) 명시적 도입. validator/judge에서 일관되게 사용

### [executor/MCP] profiler → executor 필드 전달 경로 불일치
- **현상**: profiler가 채운 필드가 최종 게임 데이터에 반영되지 않는 경우가 있음
- **원인**: executor 내 경로별로 profiler 결과 반영 수준이 다름
  | 경로 | profiler 필드 반영 |
  |------|-------------------|
  | MCP 성공 | **부분만** — MCP 서버가 받는 필드만 반영 |
  | 레거시 매니저 fallback | **부분만** — Skills의 경우 4개만 전달 |
  | executor_v2 dispatch fallback | **전체 반영** |
  | JSON 직접 저장 (Items/Enemies) | **전체 반영** |
- **수정 방향**: MCP create 확장(위 이슈)으로 동시 해결, 또는 create는 MCP 우회

## 해결됨

### ~~[MCP] 서버 cwd 경로 문제 (Windows)~~ ✅
- 절대경로로 변경하여 해결

### ~~[executor] MCP 미지원 step → executor_v2 dispatch fallback 추가~~ ✅
- UNSUPPORTED 반환 직전에 dispatch_step 시도 추가

### ~~[executor] 커스텀 업데이트 키(_equip 등) → MCP skip, v2 직행~~ ✅
- MCP 호출 전 커스텀 키 guard 추가

### ~~[executor] guard 경로 changes_log 필수 필드 누락~~ ✅
- step_id, tool_name, success 필드 추가

## 리팩터링

### [전체] 노드 패키지화 (executor 제외)
- **범위**: executor를 제외한 전 노드를 1노드 = 1패키지 구조로 전환
- **planner**: `planner_v2/` → `planner/` (v2 접미사 제거). **승인 완료**
- **definition**: `definition.py` (1290줄) → `definition/` 패키지 4분할
- **단일 파일 → 패키지**: router, reader, profiler, synthesizer, game_index_resolve
- **상세**: `refactor_plan.md` 참고

### [executor] 단일 파일 분할 (2900줄)
- **현상**: `executor.py`가 2,944줄 단일 파일. MCP 인터셉트 + 레거시 매니저 + 구조화 분기 + 스냅샷 + 로그 정규화가 한 파일에 공존
- **위치**: `agent/graph/nodes/executor.py`
- **수정 방향**: refactor_plan.md의 executor/ 패키지 구조로 분할 (`structured.py`, `mcp.py`, `legacy_handlers.py`, `dispatch.py`, `handlers/`, `utils/`)
- **선행 조건**: executor 담당자와 협의 필요

### [definition] step 구조 간소화
- **현상**: 12 step (소수점 7개) — 가독성/추적 어려움
- **위치**: `agent/graph/nodes/definition.py`
- **수정 방향**: 5 step 구조로 통합 (Step 1+2 LLM 통합, 보정 단계 통합 등)
- **상세**: `definition_simplify.md` 참고

## 최적화

### [definition] LLM 호출 횟수 축소
- **현상**: definition 노드에서 최소 3회 LLM 호출 (Step 1 추출 + Step 2 분류 + Step 5 명세). bulk 조건 시 Step 5 재시도까지 4회
- **수정 방향**:
  1. Step 1+2 통합: 추출과 분류를 하나의 structured output으로 합침 → 1회로 감소
  2. Step 4.6 성공률 향상: 코드 기반 IR 생성이 더 많은 케이스를 커버하면 Step 5 LLM 호출 자체를 건너뜀
  3. Step 2 분류 결과 캐싱: 동일 이름에 대한 분류를 게임 세션 내에서 재사용

### [router] 대화 이력 토큰 비용 증가
- **현상**: conversation_history를 프롬프트에 넣기 때문에 대화가 길어지면 토큰 비용이 선형 증가
- **수정 방향**: 최근 N턴 슬라이딩 윈도우 (현재 5턴) 유지하되, 요약 압축 적용 검토

### [profiler] create step별 LLM 호출
- **현상**: create step마다 LLM 1회 호출. 여러 엔티티 동시 생성 시 호출 횟수가 선형 증가
- **수정 방향**:
  1. 같은 target_file의 create step을 배치 처리 (1회 LLM으로 여러 엔티티 프로파일링)
  2. 스키마 기반 기본값 템플릿으로 LLM 없이 처리할 수 있는 필드 비율 늘리기

### [profiler] RAG 도입 — 유사 엔티티 참고 생성
- **현상**: profiler가 LLM으로 필드를 채울 때, 같은 카테고리의 기존 엔티티를 참고하지 않아 품질이 일관되지 않음. "파이어볼 만들어줘"에서 매번 다른 damage formula/effects 생성 가능
- **수정 방향**: 신규 생성 시 같은 target_file의 기존 엔티티 1~2개를 RAG로 검색해 프롬프트 컨텍스트로 주입
  - 인덱싱 대상: 현재 게임의 모든 엔티티 (name + description + note + 주요 필드)
  - 검색 키: 신규 엔티티의 name + description
  - 적용 위치: `profile_one()` 의 LLM 호출 직전
- **효과**: 출력 일관성 향상, hallucination 감소, 장르 톤 자동 유지 (판타지/SF 등 게임마다)
- **확장 가능성**: 안정화 후 게임 용어집(외부 사전) 추가 → definition Step 2 분류 보강용으로도 활용

### [executor] step 순차 실행
- **현상**: 병렬 가능한 조회 step도 순차 실행. depends_on이 없는 step끼리는 병렬화 가능
- **수정 방향**: depends_on 기반 의존성 그래프에서 동시 실행 가능한 step을 asyncio.gather로 병렬화

### [executor] 스냅샷/백업 매 실행마다 생성
- **현상**: 매 executor 실행 시 대상 파일 전체 스냅샷 + 백업 생성. 파일 수에 비례해 I/O 증가
- **수정 방향**: 변경 예정 파일만 선택적 백업. 또는 copy-on-write 방식으로 실제 변경 시에만 백업

### [validator] judge LLM 호출 operation별 1회
- **현상**: operation_tuples 개수만큼 judge LLM 호출. 5개 operation이면 5회 호출
- **수정 방향**:
  1. 여러 operation을 하나의 judge 프롬프트에 배치 처리
  2. 단순 create 성공은 LLM judge 없이 결정론으로 통과 처리 (changes_log의 success + entity 존재 확인만)

### [synthesizer] LLM 제거 후 템플릿 품질
- **현상**: 결정론 템플릿 응답이 다양성이 부족할 수 있음. "요청을 성공적으로 처리했습니다" 반복
- **수정 방향**: 템플릿 변형 추가 (action 종류별, 대상 종류별 문구 분기). 필요 시 경량 LLM 1회로 자연스러운 응답 생성 옵션
