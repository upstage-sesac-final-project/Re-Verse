목표

validator 구조를 아래 2개 파일 기준으로 정리한다.

validator.py
test_validator.py

이 구조에서 validator 노드의 핵심 책임은 오직 두 가지다.

순수 검증
검증 결과 요약

전제 조건은 아래와 같다.

앞 노드는 validator.py에 파일 경로가 아니라 state를 넘긴다.
이 state에는 실제 JSON 스냅샷과 실행 로그가 포함된다.
test_validator.py는 별도로 파일 경로를 받아 테스트용 state를 구성한다.
스키마 정의는 이미 별도 파일들에서 관리되고 있으므로 validator는 이를 import해서 사용만 한다.
구현 파일은 더 세분화하지 않고 validator.py 하나에 모은다.

최종 파일 역할

validator.py

이 파일은 실제 validator 구현 전체를 담당한다.

포함 역할:

LangGraph node entry
state 파싱
수정된 파일 판별
파일별 스키마 검증
필요 시 교차 검증
검증 결과 집계
검증 결과 요약
direct execution용 core 함수 제공

즉 validator.py는 경로 기반 실행기가 아니라, state 기반 검증기다.

test_validator.py

이 파일은 테스트 및 실행 드라이버 역할을 맡는다.

포함 역할:

파일 경로 입력 받기
실제 JSON 파일 로드
current_game_state, modified_game_state 구성
테스트용 changes_log, backup_paths, retry_count 구성
이 state를 validator.py에 전달
결과 출력 또는 assert

즉 test_validator.py는 경로 기반 래퍼이자 테스트 파일이다.

핵심 설계 원칙

검증의 truth source는 modified_game_state다.
수정 여부 판별 기준은 current_game_state와 modified_game_state 비교다.
changes_log는 설명 보강용이다.
backup_paths와 retry_count는 메타데이터다.
검증 결과는 코드가 결정한다.
요약은 후처리다.
경로 처리는 test_validator.py가 맡고, 검증 본체는 validator.py가 맡는다.

입력 데이터 구조

앞 노드에서 validator.py는 아래 state를 받는다.

current_game_state
수정 전 실제 JSON 스냅샷
modified_game_state
수정 후 실제 JSON 스냅샷
changes_log
step별 실행 결과
backup_paths
파일별 백업 경로
retry_count
재시도 횟수

이 중 validator의 핵심 입력은 modified_game_state다.

각 필드 역할은 아래처럼 정의한다.

modified_game_state

주 검증 대상
수정 후 JSON 내용을 직접 담고 있음
스키마 검증, 구조 검증, 참조 검증의 기준

current_game_state

비교 기준
어떤 파일이 실제로 수정되었는지 판별할 때 사용
필요 시 수정 전후 차이 분석에 사용

changes_log

설명 보강용
어떤 step이 어떤 수정을 만들었는지 추적 가능
검증 실패 시 관련 step을 찾는 데 보조적으로 사용 가능
단, 유효성 판정의 기준은 아님

backup_paths

참고용 메타데이터
파일별 백업 위치 확인용
검증 성공/실패 판정 기준은 아님

retry_count

재시도 메타데이터
요약 메시지나 로깅에 활용 가능
검증 로직 핵심과는 분리

수정 파일 판별 방식

validator.py는 파일 경로를 직접 받지 않는다.
대신 current_game_state와 modified_game_state의 key를 비교해서 수정된 파일을 판별한다.

판별 규칙은 아래처럼 둔다.

modified_game_state의 각 파일명을 순회한다.
같은 파일명이 current_game_state에도 있는지 확인한다.
값이 다르면 수정된 파일로 본다.
modified_game_state에만 있으면 신규 파일로 본다.
필요하면 current_game_state에만 있고 modified_game_state에 없는 경우 삭제 후보로 처리할 수 있다.

예를 들어 현재 구조에서는 아래 key 자체가 파일명이다.

Actors.json
Classes.json
System.json

따라서 validator는 별도 파일 경로 없이도 어떤 JSON이 바뀌었는지 판별할 수 있다.

검증 책임

A. 순수 검증

validator.py는 수정된 파일만 골라 검증한다.

기본 흐름은 아래와 같다.

state에서 current_game_state, modified_game_state, changes_log, backup_paths, retry_count 추출
수정된 파일 목록 계산
각 파일명에 대응하는 스키마 resolve
modified_game_state[file_name] 값을 스키마에 넣어 검증
필요 시 교차 검증 수행
파일별 결과 object 생성
전체 결과 집계

여기서 중요한 점은 validator가 파일 시스템에서 JSON을 다시 읽지 않는다는 것이다.
앞 노드가 이미 JSON 내용을 state로 넘겨주므로, validator는 state 내부 값만 검증하면 된다.

B. 검증 결과 요약

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

예시:

{
"validation_results": [
{
"target": "Actors.json",
"success": true,
"message": "Actors.json validation passed",
"errors": [],
"error_count": 0,
"backup_path": "/app/storage/games/game_001/backup/Actors.json.20260327_112001.bak",
"related_steps": [3, 4, 5]
},
{
"target": "System.json",
"success": true,
"message": "System.json validation passed",
"errors": [],
"error_count": 0,
"backup_path": "/app/storage/games/game_001/backup/System.json.20260327_112001.bak",
"related_steps": [6]
}
],
"validation_summary": "수정된 2개 파일 모두 검증을 통과했습니다.",
"success": true
}

validator.py 내부 함수 구성

파일은 하나만 쓸 수 있으므로, validator.py 안에서 함수 단위로 역할을 나눈다.

권장 구성은 아래와 같다.

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
Actors.json[].classId가 Classes.json의 id 집합 안에 있는지
System.json.partyMembers의 actor id가 Actors.json에 실제 존재하는지

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
반환값 출력 또는 assert

즉 경로 처리 책임은 test_validator.py에 있고, 검증 책임은 validator.py에 있다.

한 줄로 정리하면 아래와 같다.

test_validator.py는 경로 기반 state 생성기
validator.py는 state 기반 검증기

요약 설계

요약은 반드시 검증 결과 기반으로만 생성한다.

권장 summary 입력 메타는 아래와 같다.

수정된 파일 수
성공 파일 수
실패 파일 수
전체 에러 수
실패한 파일 목록
파일별 대표 메시지
retry_count

LLM summary를 쓰더라도 없는 오류를 만들어내면 안 된다.
따라서 raw result만 던지지 말고 위 메타를 정리해서 넣는 편이 안전하다.

그리고 fallback summary는 반드시 둔다.

예:

성공 시: "수정된 2개 파일이 모두 검증을 통과했습니다."
실패 시: "수정된 3개 파일 중 1개 파일에서 총 4개의 오류가 발생했습니다."

즉 요약 실패가 validator 실패로 이어지면 안 된다.

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
테스트 정리

최종 정리

이번 구조에서 validator.py는 경로 기반 검증기가 아니다.
정확히는 앞 노드가 넘겨준 수정 후 게임 상태 스냅샷을 검증하는 state 기반 validator다.

반면 test_validator.py는 경로를 받아 실제 JSON을 읽고, 이를 validator가 요구하는 state 형태로 변환해서 전달하는 경로 기반 래퍼다.

따라서 역할 분리는 아래처럼 고정하면 된다.

validator.py: state 기반 검증 + 결과 요약
test_validator.py: 경로 입력 + state 구성 + 실행/테스트