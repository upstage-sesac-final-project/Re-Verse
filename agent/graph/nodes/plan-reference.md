참조 검증 확장 계획

목적

현재 validator.py의 참조 검증은 일부 규칙만 다루고 있다.
앞으로는 RPG Maker MZ 데이터베이스 전반의 참조 관계를 validator.py 내부에서 체계적으로 검증하도록 확장해야 한다.

이번 작업의 목표는 다음과 같다.

참조 검증을 일부 하드코딩 수준에서 끝내지 않는다.
참조 규칙 테이블 기반 구조로 바꾼다.
데이터베이스형 참조와 System 배열형 참조를 분리해서 처리한다.
traits 기반 참조는 공통 규칙으로 처리한다.
검증 결과는 기존 validation_results.errors 형식에 맞춰 합친다.

핵심 방향

이번 수정에서 validator.py의 참조 검증은 “파일별 if문 몇 개 추가” 방식이 아니라, “참조 규칙 목록을 순회하는 구조”로 바꿔야 한다.

즉 아래처럼 간다.

source file
source field path
target source
lookup 방식
optional condition
explanation

validator는 이 규칙들을 순회하면서 참조 무결성을 검사해야 한다.

참조 타깃 분류

참조 검증은 크게 3종류로 나눈다.

데이터베이스형 참조

대상 JSON의 각 객체 id 집합을 기준으로 검증하는 방식이다.

예:

Actors.classId -> Classes[].id
Classes.learnings[].skillId -> Skills[].id
Skills.animationId -> Animations[].id
Enemies.actions[].skillId -> Skills[].id
Troops.members[].enemyId -> Enemies[].id
System.partyMembers[] -> Actors[].id
System.testTroopId -> Troops[].id
System 배열형 참조

System.json 내부 배열의 유효 인덱스를 기준으로 검증하는 방식이다.

예:

Skills.damage.elementId -> System.elements
Skills.requiredWtypeId1 -> System.weaponTypes
Skills.requiredWtypeId2 -> System.weaponTypes
Skills.stypeId -> System.skillTypes
Items.damage.elementId -> System.elements
Weapons.etypeId -> System.equipTypes
Weapons.wtypeId -> System.weaponTypes
Armors.etypeId -> System.equipTypes
Armors.atypeId -> System.armorTypes

주의:
이 경우 target은 [].id가 아니라 System 내부 배열의 index 또는 유효 범위다.
따라서 기존 DB형 참조와 같은 방식으로 처리하면 안 된다.

traits 기반 공통 참조

traits를 가지는 데이터는 개별 파일마다 중복 구현하지 말고, traits[].code 값에 따라 참조 대상을 결정하는 공통 검증 함수로 처리한다.

예:

traits[code=51].dataId -> System.weaponTypes
traits[code=52].dataId -> System.armorTypes
traits[code=31].dataId -> System.elements
traits[code=11].dataId -> System.elements
traits[code=13].dataId -> States[].id

이 규칙은 traits 필드를 가진 파일들 전체에 재사용 가능해야 한다.

중요 원칙

MZ 화면 기준 설명이 아니라 실제 JSON 필드 기준으로 구현한다.
즉 표에 적힌 의미를 그대로 믿지 말고, 실제 JSON 구조에 해당 필드가 존재하는지 보고 구현해야 한다.
참조 타깃이 DB형인지 System 배열형인지 반드시 구분한다.
둘을 같은 방식으로 처리하면 안 된다.
0, null, 빈 값 허용 여부를 필드별로 확인해야 한다.
예를 들어 animationId, elementId, requiredWtypeId 등은 0이 “없음” 의미일 수 있다.
이 경우 무조건 에러로 처리하면 안 된다.
조건부 참조는 조건까지 포함해서 구현한다.
예:
Enemies.dropItems[kind=1].dataId -> Items
Enemies.dropItems[kind=2].dataId -> Weapons
Enemies.dropItems[kind=3].dataId -> Armors
Skills.effects[code=21].dataId -> States
수정된 파일만 직접 검증하되, 참조 대상 파일은 merged snapshot에서 읽는다.
즉 current_game_state와 modified_game_state를 합친 reference snapshot을 기준으로 참조 대상을 조회하는 구조는 유지한다.

구현 요구사항

validator.py 내부에 참조 규칙 테이블을 만든다.

권장 정보:

source_file
source_path
target_kind
target_file 또는 system_key
condition
allow_zero 또는 allow_empty
message template

여기서 target_kind는 최소 아래 3개 정도로 나누는 게 좋다.

db
system_index
trait_rule
DB형 참조 검증 함수를 만든다.

역할:

특정 파일의 특정 path에서 참조값 추출
target_file의 id 집합 구성
참조값이 유효한지 확인
실패 시 표준 에러 object 생성
System 배열형 참조 검증 함수를 만든다.

역할:

System.json의 특정 배열을 읽음
참조값이 유효 범위 안에 있는지 확인
필요 시 0 허용 여부 반영
실패 시 표준 에러 object 생성
traits 공통 검증 함수를 만든다.

역할:

traits 배열을 순회
code 값에 따라 참조 타깃 결정
dataId가 유효한지 확인
실패 시 표준 에러 object 생성
조건부 경로 추출을 지원해야 한다.

예:

learnings[].skillId
effects[code=21].dataId
dropItems[kind=2].dataId
members[].enemyId

즉 단순 1단 path만 보지 말고, 중첩 리스트 내부 조건부 추출까지 지원해야 한다.

기존 validation_results 형식은 유지한다.

참조 검증 에러도 최종적으로는 기존 파일별 결과에 합쳐져야 한다.

즉 파일별 결과 object 안의 errors 리스트에 추가되고,
error_count에도 반영되어야 한다.

1차로 넣어야 할 참조 규칙

아래 규칙들은 우선 구현 대상이다.

Actors

classId -> Classes
equips -> Classes
traits[code=51].dataId -> System.weaponTypes
traits[code=52].dataId -> System.armorTypes
traits[code=31].dataId -> System.elements
traits[code=11].dataId -> System.elements
traits[code=13].dataId -> States

Classes

learnings[].skillId -> Skills
traits[code=51].dataId -> System.weaponTypes
traits[code=52].dataId -> System.armorTypes
traits[code=31].dataId -> System.elements
traits[code=11].dataId -> System.elements
traits[code=13].dataId -> States

Skills

animationId -> Animations
damage.elementId -> System.elements
effects[code=21].dataId -> States
requiredWtypeId1 -> System.weaponTypes
requiredWtypeId2 -> System.weaponTypes
stypeId -> System.skillTypes

Items

animationId -> Animations
damage.elementId -> System.elements
effects[code=21].dataId -> States

Weapons

animationId -> Animations
etypeId -> System.equipTypes
wtypeId -> System.weaponTypes
traits[code=51].dataId -> System.weaponTypes
traits[code=52].dataId -> System.armorTypes
traits[code=31].dataId -> System.elements
traits[code=11].dataId -> System.elements
traits[code=13].dataId -> States

Armors

etypeId -> System.equipTypes
atypeId -> System.armorTypes
traits[code=51].dataId -> System.weaponTypes
traits[code=52].dataId -> System.armorTypes
traits[code=31].dataId -> System.elements
traits[code=11].dataId -> System.elements
traits[code=13].dataId -> States

Enemies

actions[].skillId -> Skills
dropItems[kind=1].dataId -> Items
dropItems[kind=2].dataId -> Weapons
dropItems[kind=3].dataId -> Armors
traits[code=51].dataId -> System.weaponTypes
traits[code=52].dataId -> System.armorTypes
traits[code=31].dataId -> System.elements
traits[code=11].dataId -> System.elements
traits[code=13].dataId -> States

Troops

members[].enemyId -> Enemies

System

partyMembers[] -> Actors
testBattlers[].actorId -> Actors
testTroopId -> Troops

추가 확인이 필요한 규칙

아래는 문서상 의미는 있지만, 실제 JSON 필드 구조를 한 번 더 확인하고 넣어야 한다.

Actors.equips -> Classes
이건 “액터 초기 장비가 직업 기준으로 정해진다”는 의미와 실제 Actors.json 필드 참조 구조가 다를 수 있다.
실제 JSON에 classId만 있고 equips가 직접 직업을 참조하지 않는다면, validator 규칙으로 넣으면 안 된다.
System.testBattlers -> Classes
실제 JSON에 classId가 직접 없으면 넣지 않는다.
반드시 실제 testBattlers 구조를 보고 결정한다.
System.testBattlers[].equips[] -> Weapons / Armors
이건 equip slot 구조와 item type 구분 방식이 필요하다.
현재 바로 넣기보다는 실제 JSON 구조 확인 후 구현한다.

즉 위 3개는 “보류 또는 확인 필요”로 표시하고, 실제 필드 확인 후 추가한다.

에러 형식

참조 검증 에러도 기존 형식을 따른다.

최소 포함 정보:

loc
msg

가능하면 추가:

input
expected

예시 개념:

loc: "$[3].classId"
msg: "Referenced classId 99 does not exist in Classes.json"
input: 99
expected: "existing Classes.json id"

즉 스키마 에러와 비슷한 방식으로 파일별 errors에 누적되게 한다.

구현 우선순위

참조 규칙 테이블 정의
DB형 참조 검증 함수 구현
System 배열형 참조 검증 함수 구현
traits 공통 검증 함수 구현
조건부 path 추출 구현
기존 validate flow에 연결
파일별 errors와 error_count에 합치기

최종 목표

validator.py의 참조 검증은 일부 파일만 개별 처리하는 수준이 아니라,
RPG Maker MZ 데이터베이스 전반의 주요 참조 관계를 규칙 기반으로 검사하는 구조가 되어야 한다.

즉 이번 수정의 목표는 아래 한 줄로 정리된다.

현재의 제한적인 하드코딩 참조 검증을, 확장 가능한 규칙 테이블 기반 참조 검증 구조로 바꾼다.
