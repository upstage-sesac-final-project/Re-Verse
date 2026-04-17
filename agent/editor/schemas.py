from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class ExtractionResult(BaseModel):
    """1단계: 핵심 키워드 추출 결과"""

    subject: str = Field(..., description="조작 대상 (예: 슬라임, 주인공, 게임 제목)")
    property: str | None = Field(None, description="수정/조회하려는 속성 (예: 체력, 가격, 이름)")
    value: str | None = Field(None, description="설정하려는 값 (예: 500, 냥냥펀치)")
    action: str = Field(..., description="의도 유형 (READ, UPDATE, CREATE, DELETE)")


class Step1ExtractionResponse(BaseModel):
    """1단계 최종 응답 스키마"""

    extractions: list[ExtractionResult] = Field(..., description="추출된 핵심 키워드 목록")
    thought_process: str = Field(..., description="추출 근거 및 논리")


class ClassificationResult(BaseModel):
    """2단계: 카테고리 분류 결과"""

    name: str = Field(..., description="분류 대상 이름 (예: 슬라임, 주인공, 포션, 강철검, 독)")
    category: str = Field(
        ...,
        description="가장 높은 점수를 받은 최종 데이터 카테고리 (Actor, Enemy, Item, Skill, Weapon, Armor, Class, State, System, None)",
    )
    category_scores: dict[str, float] = Field(
        ...,
        description="모든 카테고리에 대한 점수 매핑 (0.0 ~ 1.0). 합계가 1이 될 필요는 없으나 상대적 우위를 나타냄",
    )
    is_category_label: bool = Field(
        False, description="단순히 카테고리를 지칭하는 단어(예: 템, 몹, 캐릭, 직업)인지 여부"
    )
    system_ref: str | None = Field(
        None, description="시스템 예약어 참조 (hero, game_title, currency, start_pos)"
    )
    reason: str = Field(..., description="최종 카테고리 선택 이유 (점수 기반 설명 포함)")


class Step2ClassificationResponse(BaseModel):
    """2단계 최종 응답 스키마"""

    classifications: list[ClassificationResult] = Field(
        ..., description="키워드별 카테고리 분류 목록"
    )
    thought_process: str = Field(..., description="전체적인 분류 논리")


class FinalDefinitionResponse(BaseModel):
    """정의 노드(2단계)의 최종 출력 스키마 (PROGRESS.md 규격 준수)"""

    target_files: list[str] = Field(..., description="수정/조회가 발생하는 JSON 파일 목록")
    modifications: list[dict] = Field(
        ...,
        description="최종 작업 목록. 각 항목은 type, target, params(ID와 필드 포함)를 가져야 함",
    )
    extracted_ids: dict[str, Any] = Field(..., description="식별된 모든 ID 정보 요약")
    params_sufficient: bool = Field(True, description="요청 처리에 필요한 정보가 충분한지 여부")
    message_for_user: str | None = Field(
        None, description="정보가 부족하거나 사용자에게 전달할 메시지"
    )

    @model_validator(mode="after")
    def enforce_consistency(self) -> "FinalDefinitionResponse":
        """modifications가 비어있는데 params_sufficient=True인 모순 방지."""
        if not self.modifications and self.params_sufficient:
            self.params_sufficient = False
            if not self.message_for_user:
                self.message_for_user = "요청을 수정 명세로 변환하지 못했습니다. 어떤 내용을 바꾸고 싶은지 다시 알려주세요."
        return self
