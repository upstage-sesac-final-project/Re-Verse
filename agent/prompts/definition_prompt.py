"""Definition 노드용 프롬프트 (재설계된 5단계 구조)."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState

STEP1_SYSTEM_PROMPT = """당신은 사용자의 요청에서 핵심적인 키워드와 의도를 추출하는 전문가입니다.

### [추출 규칙 - 엄격 준수]
1. **Subject (대상)**: 문장에서 조작의 대상이 되는 단어를 **원문 그대로** 추출하십시오. (예: "총을 추가" -> Subject: "총")
   - **주의**: 문장에 없는 단어(예: 몬스터, 캐릭터 등)를 임의로 추측하여 넣지 마십시오.
2. **Property (속성)**: 대상의 성질이나 수치를 추출하십시오. (예: "얼음 속성" -> Property: "속성", Value: "얼음")
3. **Value (값)**: 새로 설정하거나 변경하려는 구체적인 이름이나 수치를 적으십시오.
4. **Action (유형)**: READ, UPDATE, CREATE, DELETE 중 하나를 선택하십시오.

### [주의 사항]
- 사용자가 "A 속성의 B"라고 말하면, [CREATE: B]와 [PROPERTY: 속성, VALUE: A]로 나누어 추출하십시오.
- 반드시 `Step1ExtractionResponse` 구조로 반환하십시오.
"""


def build_step1_prompt(state: AgentState) -> list[BaseMessage]:
    user_input = state.get("user_input", "")
    human_message = (
        f'사용자 요청: "{user_input}"\n\n위 요청에서 핵심 키워드들을 추출하여 반환하십시오.'
    )
    return [SystemMessage(content=STEP1_SYSTEM_PROMPT), HumanMessage(content=human_message)]


STEP2_SYSTEM_PROMPT = """당신은 주어진 단어들이 RPG Maker MZ의 어떤 데이터 카테고리에 속하는지 분류하는 전문가입니다.

### [허용 카테고리 목록]
- **Actor, Enemy, Item, Skill, Weapon, Armor, Class, State, Element, System, None**

### [분류 가이드라인]
1. **정확한 분류**: "총", "검"은 Weapon입니다. "얼음", "불"은 Element입니다.
2. **카테고리 지칭어 판별 (is_category_label)**:
   - "아이템", "템", "적", "몬스터", "몹", "캐릭터", "캐릭", "스킬", "기술" 등과 같이 **구체적인 이름이 아닌 카테고리 자체를 지칭하는 단어**는 반드시 `is_category_label: true`로 설정하십시오.
   - "슬라임", "포션"과 같이 구체적인 고유 명칭은 `false`입니다.
3. **주인공 처리**: "주인공", "쥔공" 등은 category: Actor, system_ref: hero, is_category_label: false로 고정하십시오.
4. 이 단계에서는 분류 정보만 제공하며, 어떠한 실행 계획도 세우지 마십시오.
"""


def build_step2_prompt(extractions: list[dict]) -> list[BaseMessage]:
    targets = set()
    for ext in extractions:
        if ext.get("subject"):
            targets.add(ext["subject"])
        # value가 숫자가 아닌 경우에만(엔티티 이름일 가능성) 분류 대상에 추가
        val = ext.get("value")
        if val and not (isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit())):
            targets.add(val)

    targets_str = ", ".join(list(targets))
    human_message = f"대상 목록: {targets_str}\n\n위 대상들의 카테고리를 분류하고 지칭어 여부 및 system_ref를 확인하십시오."
    return [SystemMessage(content=STEP2_SYSTEM_PROMPT), HumanMessage(content=human_message)]


STEP5_SYSTEM_PROMPT = """당신은 수집된 정보를 바탕으로 RPG Maker MZ 규격에 맞는 최종 작업 지시서를 작성합니다.

### [참조 문서: 데이터 스키마 레퍼런스]
{schema1}
{schema2}

### [최종 조립 지침 - 필수 준수]
1. **필드 매핑 및 추론**:
   - 사용자가 요청한 `property`(속성)는 반드시 `params` 내의 적절한 필드명으로 변환하여 포함하십시오.
   - **생성(CREATE) 요청 시, 대상의 이름(예: '체력 회복 포션')에서 기능을 추론하여 필수 데이터를 채우십시오.**
   - 예: '회복 포션' -> `effects` 리스트에 HP 회복(code: 11) 데이터 추가.
   - 예: '불 드래곤' -> `traits`에 화염 속성(code: 31, dataId: 2) 추가.
2. **액션 타입**: `type`은 반드시 "read", "update", "create", "delete" 중 하나여야 합니다.
3. **타겟 카테고리**: `target`은 "actor", "enemy", "item" 등 데이터 카테고리여야 합니다.
4. **과잉 생성 금지**: 지칭어(is_category_label: true)인 대상은 별도의 생성 작업을 만들지 마십시오. 구체적인 이름이 있는 항목에 대해서만 작업을 생성하십시오.
5. **ID 필드 및 요약 규격**:
   - `modifications` 내 `params`에는 반드시 `대상카테고리_id` 필드를 포함하십시오.
   - 신규 생성(CREATE)인 경우, ID는 반드시 **"NEW"**여야 합니다. (임의의 숫자를 지어내지 마십시오.)
   - 조회/수정(READ/UPDATE)인 경우, 식별된 **실제 숫자 ID**를 사용하십시오.
"""


def build_step5_prompt(
    state: AgentState,
    extractions: list,
    classifications: list,
    sys_info: dict,
    schema1: str,
    schema2: str,
) -> list[BaseMessage]:
    # 시스템 프롬프트에 스키마 내용 주입
    system_content = STEP5_SYSTEM_PROMPT.format(schema1=schema1, schema2=schema2)

    context = {
        "user_input": state.get("user_input"),
        "extractions": extractions,
        "classifications": classifications,
        "system_info": sys_info,  # 실제 속성 리스트 등 시스템 데이터 주입
    }

    human_message = f"""아래 분석 데이터와 실제 시스템 정보를 바탕으로 최종 modifications 리스트를 작성하십시오.

### [분석 데이터 및 시스템 정보]
{context}

### [특별 지시]
- 속성(Element) ID가 필요한 경우, `system_info['elements']` 배열에서 해당 단어와 가장 유사한 항목의 **인덱스 번호**를 `dataId`로 사용하십시오. (예: 4번째에 있다면 4)
"""

    return [SystemMessage(content=system_content), HumanMessage(content=human_message)]
