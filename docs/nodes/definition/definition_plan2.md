# Definition Node 고도화 계획: 세부 의도 기반 스키마 최적화

## 0. 개요
전체 스키마 문서(약 11,000 토큰)를 매번 프롬프트에 주입하는 비효율을 해결하기 위해, 사용자의 **세부 의도(Granular Intent)**를 먼저 파악하고, 해당 작업에 꼭 필요한 스키마 섹션만 골라내어 주입하는 최적화 전략을 수립한다.

---

## 1단계: 세부 의도(Granular Intent) 정의
사용자의 요청을 아래와 같은 구체적인 작업 단위로 분류한다. (스프레드시트 예시 기반)

| 세부 의도 | 설명 | 필수 참조 섹션 |
| :--- | :--- | :--- |
| `add_skill_to_actor` | 캐릭터에게 특정 스킬 부여 | Actors, Skills, Traits, System |
| `add_skill_to_class` | 직업에 배울 스킬 추가 | Classes, Skills, Learnings, System |
| `create_skill` | 새로운 스킬 생성 | Skills, Damage 구조, Effect 구조, System |
| `modify_property` | HP, 가격 등 단순 수치 수정 | 해당 엔티티(Enemy/Item 등), System |
| `add_item_to_actor` | 캐릭터에게 아이템 지급 | Actors, Items, Trait(보통은 소지품 관리) |
| `query_info` | 데이터 조회 요청 | 해당 엔티티 섹션 전체 |

---

## 2단계: 추출 로직 고도화 (Step 1 Enhancement)
- **목표**: 1단계 LLM이 키워드 추출과 동시에 위 테이블의 `granular_intent`를 판별하게 한다.
- **스키마 수정**: `Step1ExtractionResponse`에 `granular_intent` 필드 추가.
- **프롬프트 수정**: 의도 분류를 위한 Few-shot 예시 추가.

---

## 3단계: 지능형 스키마 필터 구축 (Knowledge Filter)
- **목표**: 판별된 `granular_intent`를 입력받아, Markdown 문서에서 필요한 섹션만 잘라내는 파이썬 함수 구현.
- **로직**:
  1. `granular_intent` -> 필요한 섹션 키워드 리스트 추출.
  2. Markdown 문서를 `##` 단위로 파싱.
  3. 키워드가 포함된 섹션 + 공통 규칙 섹션만 결합하여 최종 프롬프트용 텍스트 생성.

---

## 4단계: 통합 및 검증 (Integration & Validation)
- **목표**: 최적화된 프롬프트를 5단계(최종 조립)에 적용하고 토큰 절감 효과 확인.
- **테스트 케이스**:
  - "주인공에게 파이어볼 추가" -> 토큰이 2,000개 이하로 줄어드는지 확인.
  - "슬라임 체력 500" -> 몬스터 관련 정보만 주입되는지 확인.

---

## 구현 순서
1. `schemas.py`에 `granular_intent` 추가. (진행 예정)
2. `definition_prompt.py`의 1단계 프롬프트에 의도 분류 가이드 추가.
3. `definition.py`에 의도 기반 필터링 함수 구현.
4. 최종 테스트 및 LangSmith 모니터링.
