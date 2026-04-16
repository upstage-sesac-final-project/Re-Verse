"""Operation IR 타입 정의.

Operation IR 은 definition 노드가 생성하고 planner / validator / executor 가 소비하는
정규화된 수정 명령 표현이다. 두 경로(Step 5 코드 기반, Step 6 LLM fallback) 가
동일한 스키마를 지키도록 여기서 한 번만 정의한다.

참고: 현 구현은 TypedDict 기반으로 runtime 검증은 없다. `validate.py` 가
degenerate(update/delete/read 인데 subject 미식별 또는 updates 비어있음) 만 감지한다.
"""

from __future__ import annotations

from typing import Literal, TypedDict

OpKind = Literal["create", "update", "update_all", "delete", "read"]
"""operation_tuple 의 `op` 필드 허용값."""

ValueKind = Literal[
    "string",
    "param",
    "skill",
    "weapon",
    "armor",
    "class",
    "item",
    "state",
    "element",
    "trait",
    "map_creation",
]
"""operation_tuple.value.kind 허용값. 참조/단순값/맵생성 등 의미 구분."""

SubjectScope = Literal["single", "all"]
"""subject.scope — 단일 엔티티 또는 파일 전체."""


class OperationValue(TypedDict, total=False):
    """operation_tuple.value 구조.

    참조 필드(skill/weapon/armor/class/item)는 ref 로 이름 넘기고 후처리(resolve.py) 에서 id 로 변환.
    단순 필드(string/param)는 new_value 로 직접 값 전달.
    trait 는 array_op 로 업데이트 방식 지정.
    map_creation 은 original_file_name 로 베이스 맵 지정.
    """

    kind: ValueKind
    ref: str | None
    new_value: str | int | float | None
    type_hint: str | None  # 방패 / 장신구 등 슬롯 힌트
    array_op: str | None  # trait 업데이트 방식
    match_hint: str | None  # trait 매칭 힌트
    original_file_name: str  # map_creation 전용


class OperationSubject(TypedDict, total=False):
    """operation_tuple.subject 구조.

    단일 엔티티면 name/id 중 하나 이상 있어야 함(validator 가 강제).
    파일 전체 대상이면 scope="all".
    """

    name: str | None
    id: int | str | None  # "NEW" 문자열 또는 실제 정수 id
    scope: SubjectScope


class OperationTuple(TypedDict, total=False):
    """정규화된 수정 명령 단위.

    definition(Step 5 build / Step 6 normalize) 가 생성하고 planner 가 소비한다.
    각 필드 규약:
      - op:      CRUD 종류
      - file:    대상 JSON 파일 (예: "Actors.json")
      - subject: 대상 엔티티 식별자 (create 면 None 또는 name 만)
      - field:   수정할 필드명 (update 계열만)
      - value:   수정값 명세 (update/create 에 사용)
      - raw_updates: (normalize 경로 한정) LLM 이 준 updates dict 원본
    """

    op: OpKind
    file: str
    subject: OperationSubject | None
    field: str | None
    value: OperationValue | None
    raw_updates: dict  # Step 6 경로가 LLM updates dict 를 그대로 넘길 때 사용
