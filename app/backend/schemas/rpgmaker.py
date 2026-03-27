from typing import Any

from pydantic import BaseModel, Field


class EntityMapping(BaseModel):
    """엔티티 추출 및 ID 매핑 정보"""

    category: str = Field(
        ..., description="데이터 카테고리 (예: Actors, Items, Skills, Classes 등)"
    )
    id: str = Field(..., description="데이터의 고유 ID (숫자 문자열). 신규 생성이면 'NEW'")
    name: str = Field(..., description="데이터의 이름")
    reason: str = Field(..., description="이 엔티티를 선택한 이유")


class DefinitionNodeResponse(BaseModel):
    """정의 노드(2단계)의 단일 수정 사항 스키마"""

    file: str = Field(
        ...,
        description="수정/조회할 대상 JSON 파일명 (예: Actors.json, Classes.json, Skills.json 등)",
    )
    action: str = Field(..., description="수행할 액션 (CREATE, READ, UPDATE, DELETE)")

    target_entity: EntityMapping = Field(..., description="주요 수정 대상 엔티티 (예: 특정 캐릭터)")
    action_object: EntityMapping | None = Field(
        None, description="액션의 대상이 되는 보조 엔티티 (예: 부여할 스킬)"
    )

    target_field: str | None = Field(
        None, description="수정할 구체적인 필드명 (예: traits, learnings, params[2])"
    )
    current_value: Any = Field(None, description="현재 데이터베이스에 저장된 값")
    new_value: Any = Field(None, description="새로 설정할 값 (객체, 리스트, 또는 단순 값)")

    thought_process: str = Field(..., description="이 특정 수정을 결정한 논리적 근거")


class FinalDefinitionResponse(BaseModel):
    """정의 노드(2단계)의 최종 출력 스키마 (복수 수정 및 연쇄 작업 지원)"""

    modifications: list[DefinitionNodeResponse] = Field(
        ..., description="수행해야 할 모든 수정 작업 목록 (순서대로 수행됨)"
    )
    params_sufficient: bool = Field(True, description="요청 처리에 필요한 정보가 충분한지 여부")
    message_for_user: str | None = Field(
        None, description="정보가 부족하거나 사용자에게 질문이 필요할 때 작성"
    )
    overall_thought_process: str = Field(
        ..., description="전체적인 작업 계획 (예: 스킬 생성 후 캐릭터 traits에 연결)"
    )
    confidence: float = Field(..., description="결과에 대한 전체적인 확신도 (0.0 ~ 1.0)")
