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


STEP2_SYSTEM_PROMPT = """당신은 사용자의 요청에서 대상(Subject)이 RPG Maker MZ의 어떤 데이터 카테고리에 속하는지 판별하는 전문가입니다.

### [허용 카테고리 목록]
- **Actor, Enemy, Item, Skill, Weapon, Armor, Class, State, Element, System, None**

### [분류 가이드라인]
1. **정확한 분류**: "총", "검"은 Weapon입니다. "얼음", "불"은 Element입니다.
2. **카테고리 지칭어 판별 (is_category_label)**:
   - "아이템", "템", "적", "몬스터", "몹", "캐릭터", "캐릭", "스킬", "기술" 등과 같이 **구체적인 이름이 아닌 카테고리 자체를 지칭하는 단어**는 반드시 `is_category_label: true`로 설정하십시오.
   - "슬라임", "포션"과 같이 구체적인 고유 명칭은 `false`입니다.
3. **주인공 처리**: "주인공", "쥔공" 등은 category: Actor, system_ref: hero, is_category_label: false로 고정하십시오.
4. 이 단계에서는 분류 정보만 제공하며, 어떠한 실행 계획도 세우지 마십시오.

### [분류 핵심 원칙 - 엄격 준수]
1. **지시어(Category Indicator) 우선**: 사용자가 대상을 지칭하는 명사(예: '스킬', '캐릭터', '아이템', '적/몬스터', '무기', '방어구')를 함께 사용했다면, 해당 명사에 대응하는 카테고리를 **절대적**으로 선택하십시오.
   - **예시**: "체력 포션 스킬" -> '포션'이라는 이름 때문에 Item으로 분류하지 마십시오. 사용자가 '스킬'이라고 명시했으므로 카테고리는 반드시 **Skill**입니다.
   - **예시**: "리드라는 캐릭터" -> 이름이 적군 같더라도 사용자가 '캐릭터'라고 했으므로 카테고리는 **Actor**입니다.
2. **System 값 검색 배제**: 수정 대상이 '게임 제목', '통화 단위' 등 **System** 카테고리의 속성인 경우, 설정하려는 **값(Value)**(예: '냥냥펀치')은 별도의 엔티티로 분류하거나 검색할 필요가 없습니다. 이는 단순 문자열/숫자 값입니다.
3. **이름-카테고리 충돌 해결**: 대상 이름이 다른 카테고리와 혼동될지라도(예: '불 검' 아이템 vs '불 검' 무기), 사용자가 명시한 카테고리 지시어를 절대적으로 신뢰하십시오.
4. **지시어가 없는 경우에만 추론**: 사용자가 이름을 단독으로 사용한 경우(예: "리드 수정해줘")에만 이름의 의미를 통해 가장 확률이 높은 카테고리를 추론하십시오.

### [출력 규칙]
- 사용자가 명시한 카테고리 지시어가 문장에 포함되어 있다면, 해당 카테고리에 높은 점수를 부여하고 `reason`에 "사용자 지시어(예: 스킬) 기반 분류"라고 명시하십시오.
"""


def build_step2_prompt(extractions: list[dict], user_input: str = "") -> list[BaseMessage]:
    targets = set()
    for ext in extractions:
        if ext.get("subject"):
            targets.add(ext["subject"])
        # value가 숫자가 아닌 경우에만(엔티티 이름일 가능성) 분류 대상에 추가
        val = ext.get("value")
        if val and not (isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit())):
            targets.add(val)

    targets_str = ", ".join(list(targets))
    human_message = f'원문 입력: "{user_input}"\n대상 목록: {targets_str}\n\n위 원문을 참고하여 각 대상들의 카테고리를 분류하고 지칭어 여부 및 system_ref를 확인하십시오.'
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
6. **아이템(item)의 "효과" / 사용·전투 시 수치 변화 (범용 규칙, 매우 중요)**:
   - **효과·데미지·피해·깎·회복·흡수·드레인·HP·MP·TP·상태이상·버프/디버프** 등 **플레이에 반영되는 변화**를 말하면, 이는 **설명(description)만 바꾸는 요청이 아닙니다.** 반드시 MZ 데이터 필드(`damage`, `effects`, 필요 시 `note` 등)로 표현하십시오.
   - **`damage`**: 아이템의 "피해" 블록. 항상 객체로 넣고 필드는 `type`, `elementId`, `formula`, `variance`, `critical`를 맞추십시오.
     - **`damage.type` (0~6, MZ 관례)**: 0=없음, 1=HP 피해, 2=MP 피해, 3=HP 회복, 4=MP 회복, 5=HP 흡수, 6=MP 흡수. 사용자 의도에 맞는 타입을 고르십시오(예: "MP를 깎는다"→2, "MP를 채운다"→4).
     - **`damage.formula`**: 런타임 계산식. 허용 토큰 예: `a.atk`, `a.def`, `a.mat`, `a.agi`, `a.luk`, `b.mhp`, `b.def`, `b.hp`, `b.mp`, 숫자, `+ - * / ( )`. **의도를 설명 문장으로만 남기지 말고** 수식으로 옮기십시오.
       - 고정 피해 50: `type: 1`, `formula: "50"`.
       - 최대 HP의 비율 등은 `b.mhp`와 연산으로 표현(예: 최대 HP의 30% 피해 → `"b.mhp * 0.3"` 등, 문맥에 맞게).
       - **남은 HP가 정확히 1이 되게**: HP 피해 `type: 1`, `formula: "b.hp - 1"`, `variance: 0`, `critical: false` (단순 `"1"`은 "피해량 1"이지 "남김 1"이 아님).
       - **완전 회복 성격**(수식으로 전체 회복): `type: 3`, `formula: "b.mhp"` 또는 문맥에 맞는 회복량.
       - **고정량 HP 회복**(예: "HP를 3 늘려"): `type: 3`, `formula: "3"` 이 가장 단순합니다. 기존 데이터가 MP 회복만 `effects`(code 12)로 두었다면, 동일 프로젝트 관례에 맞춰 **HP는 code 11**로 `effects`에 옮기거나 `damage`와 `effects`를 정리해 **의도한 수치가 실제로 적용되게** 맞추십시오.
     - **`variance` / `critical`**: 고정값을 원하면 `variance: 0`, 치명타 없음이면 `critical: false`.
   - **`effects`**: "사용 효과" 배열. **고정 수치 HP/MP/TP 회복**, **상태 부여·해제**, **일시 강화/약화** 등은 `damage`만으로 표현하기 어색할 때 `effects`의 `code`, `dataId`, `value1`, `value2`로 넣으십시오. (예: HP 회복 code 11, MP 회복 12, 상태 추가 21 등 — 스키마·레퍼런스의 허용 코드를 따름.)
   - **동시 사용**: 한 아이템이 "피해 + 상태 부여"처럼 복합이면 `damage`와 `effects`를 함께 채울 수 있습니다.
   - **설명만 바꾸라고 명시**한 경우에 한해 `description`(및 요청된 다른 문자열 필드)만 수정합니다.
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
