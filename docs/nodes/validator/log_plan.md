# Validator Loguru Logging Plan

> 상태: 계획 문서. 현재 validator는 아직 표준 `logging`을 사용하고 있으며, 이 문서는 `loguru` 전환안이다.

## 목표

`agent/graph/nodes/validator.py`에 단계별 실행 로그를 추가해서 다음을 빠르게 확인할 수 있게 한다.

- validator가 어떤 입력 상태로 시작했는지
- 어떤 파일이 검증 대상이 되었는지
- 각 파일이 어떤 이유로 성공 또는 실패했는지
- 최종 요약과 retry_count가 어떻게 결정됐는지

추가 목표:

- 기존 `logging` 대신 `loguru`를 사용한다.
- 로그가 너무 시끄러워지지 않도록 기본은 `info`, 상세 추적은 `debug`, 실패는 `warning`/`error`로 나눈다.
- 출력 JSON 계약에는 영향이 없게 한다.


## 현재 상태

현재 validator는 표준 `logging`을 사용한다.

- 시작 로그 1개
- 종료 로그 1개

현재 문제:

- 파일별 검증 흐름이 로그에 거의 남지 않는다.
- snapshot 로딩 실패, schema 미지원, strict validation 실패가 어디서 발생했는지 바로 보기가 어렵다.
- helper 단위의 흐름이 안 보여 디버깅 시 print 수준으로 내려가야 한다.


## 로그 설계 원칙

1. 로그는 상태 변경 지점과 분기 지점에만 남긴다.
2. 파일 전체 payload는 로그에 남기지 않는다.
3. 파일명, 결과, 에러 개수, retry_count처럼 운영에 필요한 메타데이터만 남긴다.
4. 정상 흐름은 `info`, 데이터 비교/세부 판단은 `debug`, 실패 가능성은 `warning`, 예외는 `error` 또는 `exception`으로 구분한다.
5. validator 출력값과 로그를 섞지 않는다. 로그는 관찰용, 반환 dict는 계약용이다.


## 적용 범위

직접 변경:

- `agent/graph/nodes/validator.py`

선택적 후속 변경:

- validator를 직접 실행하는 CLI 경로에서 loguru sink/format 초기화
- 테스트에서 caplog 대신 loguru 캡처 전략 추가


## 제안하는 로그 포인트

### 1. 모듈 초기화

목적:

- `logging.getLogger(__name__)`를 `from loguru import logger`로 대체

주의:

- 프로젝트 전체를 한 번에 바꾸지 않고 validator 파일 내부부터 국소적으로 적용한다.
- 다른 모듈은 그대로 `logging`을 써도 validator 단독으로는 동작하게 유지한다.


### 2. `extract_validation_inputs()`

남길 내용:

- `current_game_state` 개수
- `modified_game_state` 개수
- `changes_log` 개수
- `backup_paths` 개수
- 정규화된 `retry_count`

레벨:

- `debug`

예시:

```text
validator.inputs normalized current_files=14 modified_files=1 changes=0 backups=0 retry_count=0
```


### 3. `load_validation_payload()`

남길 내용:

- 어떤 파일 payload를 읽는지
- snapshot path인지 인메모리 값인지
- `_snapshot_error` 발생 여부

레벨:

- 정상 로드: `debug`
- snapshot error: `warning`

예시:

```text
validator.payload loaded target=Actors.json source=path
validator.payload snapshot_error target=Actors.json error="file not found: ..."
```


### 4. `detect_modified_files()`

남길 내용:

- 파일이 검증 대상으로 분류된 이유
  - current에 없음
  - snapshot 로딩 에러
  - current와 modified가 다름
  - 동일해서 사실상 변경 없음

레벨:

- 요약: `info`
- 파일별 판단: `debug`

예시:

```text
validator.modified detected target=Actors.json reason=payload_diff
validator.modified skipped target=System.json reason=no_diff
validator.modified summary detected=1 total_modified_state=3
```

주의:

- 현재 구현은 `modified_game_state.items()` 전체를 검증하고 있으므로, 로그와 실제 검증 대상이 어긋날 수 있다.
- 이 문서 기준에서는 먼저 로그를 넣고, 필요하면 후속 작업으로 "정말 modified_files만 검증할지"를 별도 결정한다.


### 5. `merge_reference_snapshots()`

남길 내용:

- current에서 몇 개 merge됐는지
- modified에서 몇 개 merge됐는지
- snapshot error 때문에 제외된 파일 수

레벨:

- `debug`

예시:

```text
validator.references merged current_ok=14 modified_ok=1 skipped=0 total=15
```


### 6. `validate_single_file()`

가장 중요한 로그 포인트.

남길 내용:

- 파일 검증 시작
- resolve_schema 결과
- payload 로드 실패 여부
- strict validation 성공/실패
- 실패 시 에러 개수와 대표 첫 에러

레벨:

- 시작/성공: `info`
- unsupported schema, payload error, validation failure: `warning`

예시:

```text
validator.file start target=Actors.json
validator.file schema_resolved target=Actors.json schema=ActorsFile
validator.file success target=Actors.json errors=0
validator.file unsupported_schema target=CommonEvents.json
validator.file validation_failed target=Actors.json errors=1 first_error="[1,'id'] -> Input should be a valid integer"
```

주의:

- 에러 전체를 로그에 그대로 다 덤프하면 `Skills.json` 같은 파일에서 로그가 과도해질 수 있다.
- 기본 로그는 `error_count`와 첫 번째 에러만 출력하고, 전체 에러는 반환 결과 JSON에서 확인하게 한다.
- 필요하면 `debug`에서만 전체 에러 리스트를 남긴다.


### 7. `build_validation_summary()`

남길 내용:

- 성공 파일 수
- 실패 파일 수
- 최종 summary 문자열

레벨:

- `debug`


### 8. `build_state_error()`

남길 내용:

- 왜 validator가 조기 종료됐는지
- retry_count가 얼마로 올라갔는지

레벨:

- `warning`


### 9. `validator()`

상위 orchestration 로그.

남길 내용:

- validator 시작
- 입력 파일 수
- modified_files 개수
- reference snapshot 개수
- 파일별 검증 루프 시작
- 최종 success/failure
- 최종 retry_count 포함 여부

레벨:

- 시작/종료: `info`
- 조기 종료: `warning`

예시:

```text
validator.start files=1 retry_count=0
validator.loop validating_files=1 detected_modified=1 references=1
validator.finish success=True validated_files=1 retry_count=None
validator.finish success=False validated_files=15 retry_count=1
```


## 구현 순서

1. `validator.py`에서 `logging` import와 `logging.getLogger(__name__)`를 제거하고 `loguru.logger`로 교체
2. helper 함수별 로그 포인트 추가
3. `validate_single_file()`에 파일별 시작/종료/실패 로그 추가
4. `validator()` 상위 요약 로그 보강
5. 로그 과다 여부를 보고 일부 `info`를 `debug`로 내릴지 조정


## 로그 포맷 가이드

권장 메시지 규칙:

- prefix를 `validator.<step>` 형태로 통일
- key=value 형태 메타데이터 사용
- 한국어/영어 혼용은 최소화하고, 고정 prefix는 영어, 상세 메시지는 짧은 한국어 허용

예시:

```text
validator.start files=1 retry_count=0
validator.file start target=Actors.json
validator.file validation_failed target=Actors.json errors=1 first_error="[1,'id'] -> Input should be a valid integer"
validator.finish success=False validated_files=1 retry_count=1
```


## 테스트 계획

확인할 시나리오:

1. `modified_game_state`가 비어 있는 경우 조기 종료 로그가 찍히는지
2. 단일 파일 성공 검증 시 start/file-success/finish 로그가 찍히는지
3. unsupported schema 파일에서 warning 로그가 찍히는지
4. strict validation 실패 시 warning 로그와 error_count가 찍히는지
5. snapshot path 입력에서 payload source가 path로 표시되는지

테스트 방식:

- 기존 validator 테스트는 출력 계약만 검증
- 로그 검증은 별도 테스트로 추가하거나, 일단 수동 실행으로 확인


## 리스크

1. `Skills.json` 같은 대형 실패 케이스에서 파일별 에러 로그가 너무 커질 수 있다.
2. 프로젝트 전체가 아직 `logging` 기반이라 validator만 `loguru`를 쓰면 포맷이 일시적으로 혼재될 수 있다.
3. `loguru` sink 초기화가 전역에서 중복되면 로그가 두 번 출력될 수 있다.


## 권장 결정

1차 작업에서는 아래까지만 한다.

- validator 내부만 `loguru` 적용
- 함수 단위 핵심 포인트에만 로그 추가
- 파일별 실패 로그는 `에러 개수 + 첫 에러`까지만 출력

2차 작업이 필요하면 그때 한다.

- 프로젝트 전역 logging/loguru 통합
- CLI/test 환경별 sink/format 분리
- request_id, operation_id, game_id까지 구조화 로그로 확장


## 완료 기준

- validator 시작부터 종료까지 흐름이 로그만으로 추적 가능하다.
- 파일별 성공/실패 이유가 로그에서 바로 보인다.
- 반환 JSON 계약은 바뀌지 않는다.
- 로그 양이 과도하지 않고, 대형 실패 파일에서도 읽을 수 있는 수준을 유지한다.
