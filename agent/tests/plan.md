목적

현재 validator 구조를 실제 실행 흐름에 맞게 다시 정리한다.

이번 구조의 핵심은 아래 두 가지다.

validator.py는 state 기반 validator다.
test_validator.py는 경로 기반 실행 드라이버다.

즉, 앞 노드가 넘겨주는 state를 검증하는 역할과, 로컬에서 파일 경로를 받아 validator를 실행해보는 역할을 분리한다.

최종 파일 구성

2.1 validator.py

validator.py는 실제 validator 구현 본체다.

담당 역할:

LangGraph node entry
state 파싱
수정된 파일 판별
파일별 스키마 검증
필요 시 교차 검증
검증 결과 집계
검증 결과 요약

중요한 점:
validator.py는 파일 경로를 직접 받지 않는다.
이 파일은 항상 state dict를 입력으로 받아 동작한다.

즉 validator.py의 성격은 다음과 같다.

경로 기반 실행기 아님
state 기반 validator 맞음

2.2 test_validator.py

test_validator.py는 테스트 및 실행 드라이버 역할을 맡는다.

담당 역할:

파일 경로 입력 받기
실제 JSON 파일 읽기
current_game_state 구성
modified_game_state 구성
테스트용 changes_log, backup_paths, retry_count 구성
위 state를 validator.py에 전달
반환 결과 출력

즉 test_validator.py는 pytest용 순수 테스트 파일이라기보다 수동 실행용 러너에 가깝다.

입력 구조

앞 노드에서 validator.py는 아래 형태의 state를 받는다.

current_game_state
modified_game_state
changes_log
backup_paths
retry_count

각 필드 의미는 아래와 같다.

current_game_state

수정 전 실제 JSON 스냅샷
비교 기준
어떤 파일이 수정되었는지 판별할 때 사용

modified_game_state

수정 후 실제 JSON 스냅샷
validator의 주 검증 대상
스키마 검증, 구조 검증, 참조 검증의 기준

changes_log

step별 실행 결과
어떤 수정이 어떤 단계에서 발생했는지 파악하기 위한 보조 정보
검증 실패 시 설명 보강용으로 사용 가능
유효성 판정의 기준은 아님

backup_paths

파일별 백업 경로
참고용 메타데이터
검증 성공/실패를 결정하는 기준은 아님

retry_count

재시도 횟수
로깅 또는 요약 문구 보강용
검증 로직 핵심과는 분리
핵심 설계 원칙

4.1 truth source는 modified_game_state
validator가 실제로 검증해야 하는 대상은 수정 후 상태다.
따라서 가장 중요한 입력은 modified_game_state다.

4.2 수정 여부 판별은 current_game_state와 비교
어떤 파일이 수정되었는지는 current_game_state와 modified_game_state를 비교해서 계산한다.

4.3 changes_log는 설명용
changes_log는 어떤 step이 어떤 결과를 만들었는지 보여주는 보조 데이터다.
검증 실패 메시지를 더 이해하기 쉽게 만드는 데 쓸 수는 있지만, 검증의 기준이 되면 안 된다.

4.4 검증 결과는 코드가 결정
스키마 검증, 교차 검증, success 판정은 항상 deterministic code가 담당한다.

4.5 요약은 후처리
validation_summary는 사람이 빠르게 확인하기 위한 요약이다.
핵심 결과는 항상 validation_results와 success다.

4.6 경로 처리는 test_validator.py가 담당
경로를 받아 JSON을 읽고 state를 만드는 작업은 test_validator.py가 맡는다.
validator.py는 만들어진 state만 검증한다.

수정 파일 판별 방식

validator.py는 파일 경로가 아니라 state 안의 key를 기준으로 수정 파일을 판별한다.

예를 들어 아래처럼 key 자체가 파일명 역할을 한다.

Actors.json
Classes.json
System.json

수정 파일 판별 규칙은 아래처럼 둔다.

modified_game_state의 각 파일명을 순회한다.
같은 파일명이 current_game_state에도 있는지 확인한다.
값이 다르면 수정된 파일로 본다.
modified_game_state에만 있으면 신규 파일로 본다.
필요하면 current_game_state에만 있고 modified_game_state에는 없는 경우 삭제 후보로 처리할 수 있다.

즉 validator.py는 별도 경로 없이도 어떤 JSON이 수정되었는지 판별할 수 있다.

validator.py의 책임

6.1 순수 검증

validator.py는 수정된 파일만 골라 검증한다.

기본 흐름은 아래와 같다.

state에서 current_game_state, modified_game_state, changes_log, backup_paths, retry_count 추출
수정된 파일 목록 계산
각 파일명에 대응하는 스키마 resolve
modified_game_state[file_name] 값을 스키마에 넣어 검증
필요 시 교차 검증 수행
파일별 결과 object 생성
전체 결과 집계

중요한 점:
validator는 파일 시스템에서 JSON을 다시 읽지 않는다.
앞 노드가 이미 JSON 내용을 state로 넘겨주므로 validator는 state 내부 값만 검증하면 된다.

6.2 검증 결과 요약

validator는 파일별 검증 결과를 바탕으로 validation_summary를 만든다.

우선순위는 아래와 같다.

validation_results
success
validation_summary

즉 요약은 사람이 읽기 쉽게 정리하는 부가 기능이고, 실제 판정은 코드가 만든 검증 결과가 담당한다.

출력 계약

validator.py의 반환 형식은 아래 3개 top-level field로 고정한다.

validation_results
validation_summary
success

각 파일별 결과 object는 아래 shape를 기본으로 한다.

target
success
message
errors
error_count

필요하면 아래 필드를 추가할 수 있다.

backup_path
related_steps

예시 형태:

validation_results:
각 수정 파일별 결과 리스트

validation_summary:
전체 검증 결과 요약 문장

success:
전체 성공 여부

파일별 결과 예시 의미:

target: 파일명
success: 파일 단위 성공 여부
message: 파일 단위 결과 메시지
errors: 표준화된 에러 리스트
error_count: 에러 개수
backup_path: 해당 파일 백업 경로
related_steps: 관련 step id 목록
validator.py 내부 함수 구성

파일은 하나만 쓰므로 validator.py 안에서 함수 단위로 역할을 나눈다.

권장 구성:

state 파싱 함수
current_game_state
modified_game_state
changes_log
backup_paths
retry_count
추출
수정 파일 판별 함수
수정 전후 state 비교
변경된 파일명 목록 추출
스키마 resolve 함수
파일명으로 스키마 찾기
예: Actors.json -> 해당 스키마
단일 파일 검증 함수
특정 파일의 modified snapshot 검증
에러 표준화
파일 단위 결과 object 생성
교차 검증 함수
여러 JSON 간 참조 무결성 확인
예: actor-class 참조, partyMembers-actor 참조
관련 step 추적 함수
changes_log에서 파일 관련 step id 추정
설명 보강용
전체 집계 함수
파일별 결과 리스트 생성
전체 success 계산
summary 생성 함수
검증 결과를 바탕으로 요약 생성
fallback summary 포함
node entry 함수
전체 validator 흐름 실행
최종 dict 반환
검증 범위

validator의 기본 검증 순서는 아래처럼 둔다.

스키마 검증
타입
필수 필드
구조 일관성
범위 조건
필요 시 strict diff 성격 검증
스키마는 통과했지만 normalize 과정에서 구조가 변형되는 경우 감지
데이터 손실이나 형태 왜곡 확인
교차 검증
Actors.json의 각 actor classId가 Classes.json의 id 집합 안에 있는지
System.json의 partyMembers actor id가 Actors.json에 실제 존재하는지

즉 스키마 검증이 1차고, 교차 검증은 그 다음 단계다.

예시 입력 기준 validator 동작

지금 예시 state를 기준으로 하면 validator는 아래처럼 동작한다.

current_game_state와 modified_game_state 비교
변경된 파일 식별
Actors.json 변경됨
Classes.json 변경 없음
System.json 변경됨
수정된 파일만 스키마 검증
Actors.json
System.json
참조 검증 수행
새 액터 id=3이 Actors.json에 존재하는지 확인
System.json.partyMembers의 3이 Actors.json에 존재하는지 확인
Actors.json의 classId=2가 Classes.json에 존재하는지 확인
changes_log 참고
Actors.json 관련 step: 3, 4, 5
System.json 관련 step: 6
최종 결과 반환

즉 Classes.json이 직접 수정되지는 않았더라도, 참조 검증용 기준 데이터로는 사용될 수 있다.

test_validator.py 실행 구조

test_validator.py는 경로를 받는다.

이 파일의 흐름은 아래처럼 잡는다.

입력 경로로부터 JSON 파일 읽기
원본 상태와 수정 상태를 각각 dict로 구성
changes_log, backup_paths, retry_count를 테스트용으로 구성
위 값을 합쳐 validator 입력 state 생성
이 state를 validator.py의 core 함수에 전달
반환값 출력

즉 경로 처리 책임은 test_validator.py에 있고, 검증 책임은 validator.py에 있다.

한 줄로 정리하면 아래와 같다.

test_validator.py는 경로 기반 state 생성기
validator.py는 state 기반 검증기
실행 방식

현재 계획 기준에서 test_validator.py는 pytest 테스트 파일이 아니라 실행 드라이버다.
따라서 실행 방식은 pytest가 아니라 python 직접 실행이다.

즉 현재 구조에서는 이렇게 실행한다.

python agent/tests/test_validator.py ...

정리하면:

지금 계획 기준 실행 방식: python test_validator.py ...
나중에 assert 기반 테스트 함수들로 바꾸면: pytest

즉 현재 이름은 test_validator.py지만, 실제 역할은 실행용 테스트 드라이버에 더 가깝다.

구현 순서
출력 계약 고정
validation_results
validation_summary
success
validator.py에 state 파싱 및 수정 파일 판별 구현
단일 파일 스키마 검증 구현
교차 검증 구현
결과 집계 구현
summary 구현
fallback 먼저
필요 시 LLM 연결
node entry 연결
test_validator.py에서 경로 기반 state 생성 연결
수동 실행 확인
최종 정리

이번 구조에서 validator.py는 경로 기반 검증기가 아니다.
정확히는 앞 노드가 넘겨준 수정 후 게임 상태 스냅샷을 검증하는 state 기반 validator다.

반면 test_validator.py는 경로를 받아 실제 JSON을 읽고, 이를 validator가 요구하는 state 형태로 변환해서 전달하는 경로 기반 래퍼다.

따라서 역할 분리는 아래처럼 고정한다.

validator.py: state 기반 검증 + 결과 요약
test_validator.py: 경로 입력 + state 구성 + 실행