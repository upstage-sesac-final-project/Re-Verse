"""Definition 노드용 프롬프트 (재설계된 5단계 구조)."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.editor.state import AgentState

STEP1_SYSTEM_PROMPT = """당신은 사용자의 요청에서 핵심적인 키워드와 의도를 추출하는 전문가입니다.

### [추출 규칙 - 엄격 준수]
1. **Subject (대상)**: 상태가 변경되는 엔티티를 추출하십시오. "A에게 B를 부여/장착/추가"에서 A가 Subject입니다.
   - 리드에게 엑스칼리버를 장착 → Subject: 리드
   - 슬라임의 공격력을 100으로 → Subject: 슬라임
   - 파이어볼 스킬 추가 → Subject: 파이어볼 (새로 만드는 것 자체가 대상)
   - **주의**: 문장에 없는 단어를 임의로 추측하여 넣지 마십시오.
2. **Property (속성)**: Subject에서 변경되는 속성이나 관계를 추출하십시오.
   - 리드에게 엑스칼리버를 장착 → Property: 장비 (또는 장착)
   - 슬라임의 공격력을 100으로 → Property: 공격력
3. **Value (값)**: 새로 설정하거나 부여하려는 구체적인 이름이나 수치를 적으십시오.
   - 리드에게 엑스칼리버를 장착 → Value: 엑스칼리버
   - 슬라임의 공격력을 100으로 → Value: 100
4. **Action (유형)**: READ, UPDATE, CREATE, DELETE 중 하나를 선택하십시오.

### [카테고리 지시어를 Subject 에서 분리 — 엄격 준수]
- 사용자가 `"X 직업"`, `"X 상태이상"`, `"X 액터"`, `"X 무기"`, `"X 방어구"`, `"X 아이템"`, `"X 스킬"`, `"X 몬스터"`, `"X 적"` 처럼 **고유명사(X) 뒤에 카테고리 지시어를 붙여** 발화한 경우:
  - Subject 에는 **고유명사(X)만** 넣으십시오. 카테고리 지시어는 Subject 에 포함하지 마십시오.
  - 카테고리 정보는 Step 2 에서 별도로 분류하므로 Subject 에 넣을 필요가 없습니다.
- **적용 예시**:
  - `검사 직업의 최대 HP를 1.5배로` → Subject: `검사` (✗ `검사 직업`)
  - `독 상태이상의 지속 턴을 5로` → Subject: `독` (✗ `독 상태이상`)
  - `기사 직업의 경험치 곡선을 더 완만하게` → Subject: `기사` (✗ `기사 직업`)
  - `마법사 직업의 최대 레벨을 80으로` → Subject: `마법사` (✗ `마법사 직업`)
  - `침묵 상태이상의 아이콘을 13번으로` → Subject: `침묵` (✗ `침묵 상태이상`)
- **예외**: 고유명사 자체에 카테고리 단어가 포함된 경우(예: `"검사"` 라는 이름의 엔티티)는 그대로 유지.
- **CREATE 는 해당 없음**: `"수호의 방패"라는 방어구를 만들어줘` 에서는 `수호의 방패` 전체가 새 엔티티 이름이므로 Subject = `수호의 방패` (여기서 "방어구" 는 카테고리 지시어이지 이름이 아님).

### [현재 턴 경계 — 최상위 규칙 (이전 대화 오염 차단)]
- 추출 대상은 **오직 `<current_turn>` 태그 내부의 문자열**이다. 시스템 프롬프트·이전 대화·외부 예시는 참고만 하고, 거기서 본 엔티티 이름을 현재 턴의 Subject/Value 로 사용하지 마라.
- Subject/Value 로 출력하는 모든 문자열은 `<current_turn>` 의 원문에 **연속된 substring 으로 그대로 등장**해야 한다. 등장하지 않으면 추출하지 말고, 해당 extraction 은 버려라.
- 대명사·지시어(`그거`, `방금 그`, `아까 만든 애`) 가 들어 있어도 이전 턴의 구체 이름을 그대로 채우지 마라. `<current_turn>` 내부에 이름이 없으면 `subject` 를 비워 두고 action 만 남겨라. 이후 단계에서 처리한다.
- 이전 턴의 property/value(예: `가격 300`) 를 현재 턴 extraction 에 **재사용하지 마라**. 현재 턴에 명시되지 않은 수치는 추출하지 않는다.

### [고유명사 보존 — 최상위 규칙]
- 사용자가 **따옴표(`"..."`, `'...'`, `「...」`, `『...』`) 또는 대괄호(`[...]`)로 감싼 문자열**은 그 엔티티의 **공식 이름**입니다.
- 이 문자열은 **원문 그대로(substring 단위로 동일하게) Subject 또는 Value에 넣어야 합니다.** 동의어·번역·축약·변형·재구성·번호 추가 절대 금지.
- 따옴표가 없더라도 사용자가 명시적으로 준 고유명사는 **원문 substring**으로 보존하십시오.

**원칙 (추상 형태로 기술)**:
- user input에 `"<원문>"` 형태의 따옴표 감싼 문자열이 있으면, Subject 또는 Value에는 반드시 그 `<원문>`을 **문자 단위로 동일하게** 넣으십시오.
- 다음 변형은 모두 금지: (a) 동의어/유사어 치환, (b) 앞뒤 음절·접미사 누락(예: "X초"에서 "초" 누락), (c) 로마 숫자·아라비아 숫자·레벨 표기 임의 추가, (d) 조사/수식어를 떼어내거나 붙여넣기.

**검증 절차 (출력 직전 자체 체크)**:
- 출력할 Subject/Value 문자열이 user input에 **연속된 substring으로 그대로 존재하는지** 확인하십시오.
- 존재하지 않으면, user input에서 따옴표(`"..."`, `'...'`, `「...」`, `『...』`) 내부의 원문을 찾아 그 값으로 교체한 뒤 재확인하십시오.
- 따옴표가 없다면 user input의 명사구 중 가장 긴 연속 substring을 사용하고, 임의 생성된 문자열은 사용하지 마십시오.

### [핵심 원칙]
- **"A에게 B를 ~하다"** 패턴에서는 항상 A가 Subject, B가 Value입니다.
  - 장착, 부여, 배우게, 추가, 변경 등 모든 동사에 적용됩니다.
- 사용자가 "A 속성의 B"라고 말하면, [CREATE: B]와 [PROPERTY: 속성, VALUE: A]로 나누어 추출하십시오.

### [ "X의 Y" / "A라는 B" 패턴 — category 단서 우선]
- 문장에 `무기 / 검 / 창 / 활 / 지팡이 / 방어구 / 갑옷 / 방패 / 반지 / 목걸이 / 장신구 / 아이템 / 포션 / 물약 / 초(草) / 스킬 / 기술 / 마법 / 상태이상 / 직업 / 클래스 / 적 / 몬스터 / 캐릭터 / 액터` 같은 **카테고리 지시어 B** 가 있으면, **"X의 Y" 의 전체 명사구(예: "용사의 검", "용맹의 반지")** 를 Subject 로 삼고, 소유격 "의" 앞에서 끊지 마십시오.
  - `"용사의 검"이라는 무기를 추가해줘` → Subject: `용사의 검` (✗ `용사`)
  - `"용맹의 반지"라는 장신구를 만들어줘` → Subject: `용맹의 반지` (✗ `용맹`)
  - `"생명의 반지"라는 방어구` → Subject: `생명의 반지` (✗ `생명`)
- 따옴표로 감싸져 있으면 따옴표 내부 원문 전체가 Subject. 따옴표가 없어도 뒤에 카테고리 지시어가 붙어 있으면 "의" 를 포함한 전체 명사구를 Subject 로 유지하십시오.
- "X의 Y 를 ...로 바꿔줘" 처럼 **X 가 기존 엔티티이고 Y 가 속성** 인 경우(예: `마왕의 이름을 대마왕으로`) 는 여기에 해당하지 않습니다. 이 경우는 Subject=`마왕`, Property=`이름`, Value=`대마왕`.
- 반드시 `Step1ExtractionResponse` 구조로 반환하십시오.
"""


def build_step1_prompt(state: AgentState) -> list[BaseMessage]:
    user_input = state.get("user_input", "")
    human_message = (
        f"<current_turn>\n{user_input}\n</current_turn>\n\n"
        "위 `<current_turn>` 내부 문자열에서만 핵심 키워드를 추출하여 반환하십시오. "
        "`<current_turn>` 에 등장하지 않는 엔티티·수치는 절대 포함하지 마십시오."
    )
    return [SystemMessage(content=STEP1_SYSTEM_PROMPT), HumanMessage(content=human_message)]


STEP2_SYSTEM_PROMPT = """당신은 사용자의 요청에서 대상(Subject)이 RPG Maker MZ의 어떤 데이터 카테고리에 속하는지 판별하는 전문가입니다.

### [허용 카테고리 목록]
- **Actor, Enemy, Item, Skill, Weapon, Armor, Class, State, Element, Map, System, None**

### [분류 가이드라인]
1. **정확한 분류**: "총", "검"은 Weapon입니다. "얼음", "불"은 Element입니다.
2. **카테고리 지칭어 판별 (is_category_label)**:
   - "아이템", "템", "적", "몬스터", "몹", "캐릭터", "캐릭", "스킬", "기술" 등과 같이 **구체적인 이름이 아닌 카테고리 자체를 지칭하는 단어**는 반드시 `is_category_label: true`로 설정하십시오.
   - "슬라임", "포션"과 같이 구체적인 고유 명칭은 `false`입니다.
   - 단, "모든 액터", "전체 캐릭터", "전부 적"처럼 범위 수식이 붙더라도 Subject 자체는 여전히 카테고리 지칭어이므로 `is_category_label: true`로 유지하십시오.
3. **주인공 처리**: "주인공", "쥔공" 등은 category: Actor, system_ref: hero, is_category_label: false로 고정하십시오.
4. 이 단계에서는 분류 정보만 제공하며, 어떠한 실행 계획도 세우지 마십시오.

### [분류 핵심 원칙 - 엄격 준수]
1. **지시어(Category Indicator) 우선 — 절대 규칙**: 사용자 문장에 아래 카테고리 지시어가 **하나라도** 등장하면, 그 지시어가 가리키는 카테고리를 **절대적**으로 선택하십시오. 엔티티 이름의 의미·연상은 **후순위**이며 지시어를 절대 덮어쓰지 못합니다.
   - **지시어 매핑 표** (이 표가 최우선 신호):
     | 지시어 (문장에 등장하는 단어) | 카테고리 |
     |---|---|
     | 무기, 검, 칼, 도끼, 창, 활, 지팡이, 완드, 단검, 장검 | Weapon |
     | 방어구, 갑옷, 투구, 헬멧, 방패, 장갑, 신발, 반지, 목걸이, 장신구, 악세서리 | Armor |
     | 아이템, 소비품, 포션, 물약, 약, 초(草) | Item |
     | 스킬, 기술, 마법, 주문 | Skill |
     | 상태이상, 버프, 디버프, 상태 | State |
     | 직업, 클래스, 잡 | Class |
     | 적, 몬스터, 몹, 보스 | Enemy |
     | 캐릭터, 액터, 주인공, 파티원, 동료 | Actor |
     | 속성 (불, 물, 얼음 등 원소 자체) | Element |

2. **합성어에서 "이름 연상"이 지시어를 덮지 않도록 주의** (최근 잦은 오류):
   - `"얼음 창"이라는 무기를 추가해줘`
     - 이름이 "얼음" → 마법/Element로 연상될 수 있지만, 문장에 **"무기"** 지시어가 있음. 카테고리는 반드시 **Weapon**.
   - `"회복초"라는 회복 아이템을 추가해줘`
     - 이름이 "회복" → 스킬로 연상될 수 있지만, 문장에 **"아이템"** 지시어가 있음. 카테고리는 반드시 **Item**.
   - `"천둥의 화살" 스킬을 추가해줘`
     - 이름이 "화살" → 무기로 연상될 수 있지만, 문장에 **"스킬"** 지시어가 있음. 카테고리는 반드시 **Skill**.
   - `"화염검" 무기를 만들어줘`
     - 이름이 "화염" → Element, "검" → Weapon. 두 신호가 이름 내에서 충돌해도 **문장의 "무기"** 지시어가 절대적. 카테고리는 **Weapon**.
   - 원칙: **이름이 합성어여서 이름 안에 다른 카테고리 연상 단어가 섞여 있어도, 문장 본문의 지시어가 있으면 그것만 보십시오.**

3. **System 값 검색 배제**: 수정 대상이 '게임 제목', '통화 단위' 등 **System** 카테고리의 속성인 경우, 설정하려는 **값(Value)**(예: '냥냥펀치')은 별도의 엔티티로 분류하거나 검색할 필요가 없습니다. 이는 단순 문자열/숫자 값입니다.
4. **이름-카테고리 충돌 해결**: 대상 이름이 다른 카테고리와 혼동될지라도(예: '불 검' 아이템 vs '불 검' 무기), 사용자가 명시한 카테고리 지시어를 절대적으로 신뢰하십시오.
5. **지시어가 없는 경우에만 추론**: 사용자가 이름을 단독으로 사용한 경우(예: "리드 수정해줘")에만 이름의 의미를 통해 가장 확률이 높은 카테고리를 추론하십시오.

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

### [Step 1·2 결과 존중 — 최상위 규칙 (엄격 준수)]
앞 단계에서 이미 추출·분류가 끝났습니다. 당신은 그 결과를 **재해석하거나 덮어쓰지 않습니다.** 오직 세부 필드만 채웁니다.

1. **이름(name) 보존 — literal 유지**:
   - `extractions[i].subject`와 `extractions[i].value`의 문자열은 **문자 단위로 동일하게** `params.name` 또는 해당 식별 필드에 넣으십시오.
   - 다음 행위는 모두 금지: (a) 동의어/유사어 치환("생명의 반지" → "근성의 반지" 금지), (b) 축약·접미사 누락("수면초" → "수면" 금지), (c) 로마 숫자/번호 추가("치유술" → "치유 I" 금지), (d) 스킬 레벨·등급 표기 삽입, (e) 재작명.
   - 이름에서 **기능을 추론하는 것은 허용**되지만, 추론 결과는 **오직 세부 필드**(`description`, `effects`, `damage`, `traits`, `params` 수치 등)에만 반영하십시오. **이름 필드는 절대 바꾸지 마십시오.**
     - 예: subject='회복 포션' → name에는 그대로 `"회복 포션"` 유지. effects에만 HP 회복 code 11 추가.
     - 예: subject='불 드래곤' → name에는 그대로 `"불 드래곤"` 유지. traits에만 화염 속성 추가.

2. **카테고리(target) 보존 — classifications 준수**:
   - `classifications[i].category`가 Weapon이면 `target: "weapon"`, target_file은 `Weapons.json`. Item이면 `target: "item"`, `Items.json`. 그대로 매핑하십시오.
   - 이름의 연상(예: "얼음"이 마법 느낌이 난다)만 보고 **다른 카테고리로 바꾸지 마십시오.** classifications가 이미 문장 지시어를 반영해 결정한 결과입니다.
   - 예: classifications에서 "얼음 활" → Weapon → `target: "weapon"`, `target_file: "Weapons.json"`. Skills로 재라우팅 금지.
   - 예: classifications에서 "수면초" → Item → `target: "item"`, `target_file: "Items.json"`. Skills로 재라우팅 금지.

3. **target_file 보존 — 절대 규칙**:
   - 각 modification 의 `target_file` 은 해당 subject 의 `classifications[i].category` 가 지정하는 파일과 **반드시 일치**해야 합니다.
     - Actor→Actors.json, Enemy→Enemies.json, Item→Items.json, Skill→Skills.json, Weapon→Weapons.json, Armor→Armors.json, Class→Classes.json, State→States.json, Element/System→System.json, Map→MapInfos.json.
   - 예: classifications 에 `"수호의 방패" → Armor` 이면 `target_file="Armors.json"`. System.json 이나 다른 파일로 보내지 마십시오.
   - 예: classifications 에 `"얼음 활" → Weapon` 이면 `target_file="Weapons.json"`. Skills.json 으로 보내지 마십시오.
   - classifications 와 어긋난 target_file 을 낸 경우, 이후 결정론 후처리에서 classifications 기준으로 강제 교정됩니다.

4. **위 세 규칙 위반 시 출력은 잘못된 것으로 간주됩니다.** 의심스러우면 extractions/classifications의 원문을 그대로 복사해 쓰십시오.

### [최종 조립 지침 - 필수 준수]
1. **필드 매핑 및 추론**:
   - 사용자가 요청한 `property`(속성)는 반드시 `params` 내의 적절한 필드명으로 변환하여 포함하십시오.
   - **생성(CREATE) 요청 시, 대상의 이름에서 기능을 추론하여 세부 데이터(description/effects/damage/traits/params)를 채우되, 이름 자체는 변경하지 마십시오.**
   - 예: name은 '체력 회복 포션' 그대로. `effects` 리스트에 HP 회복(code: 11) 데이터 추가.
   - 예: name은 '불 드래곤' 그대로. `traits`에 화염 속성(code: 31, dataId: 2) 추가.
2. **액션 타입**: `type`은 반드시 "read", "update", "create", "delete" 중 하나여야 합니다.
3. **타겟 카테고리**: `target`은 "actor", "enemy", "item" 등 데이터 카테고리여야 합니다.
4. **범위 지정 bulk update/read 규칙**:
   - 사용자가 "모든", "전체", "전부", "모두" 같은 범위 표현으로 카테고리 전체를 수정/조회하려는 경우, 이를 불충분으로 버리지 말고 **selector 기반 작업**으로 표현하십시오.
   - 현재 bulk update는 `actor`, `enemy`, `item`, `weapon`, `armor`, `class`, `state`, `element` 카테고리를 지원합니다.
   - `skill` 카테고리의 전체 bulk update는 현재 지원하지 않으므로, 해당 경우에는 `params_sufficient=false`와 설명 메시지를 반환하십시오.
   - **중요**: bulk 대상 카테고리의 현재 데이터 개수가 0개여도, 요청 자체는 여전히 유효한 bulk update입니다. 이를 `create`로 바꾸지 마십시오.
   - 빈 집합에 대한 bulk update는 "실행 시 변경 대상이 0건일 수 있는 유효한 no-op update"로 취급해야 합니다.
   - 따라서 bulk_context에 대상이 0개라고 나오더라도, 새 엔티티 생성을 요구하거나 사용자에게 이름/설명/아이콘 같은 create용 정보를 다시 묻지 마십시오.
   - 예: `"모든 액터가 초기 레벨 25가 되게 해줘"` →
     `{{"type":"update","target":"actor","params":{{"selector":{{"mode":"all"}},"updates":{{"initialLevel":25}}}}}}`
   - 예: `"아이템 전부 가격 100으로"` →
     `{{"type":"update","target":"item","params":{{"selector":{{"mode":"all"}},"updates":{{"price":100}}}}}}` 와 같이 **bulk selector + canonical updates** 구조를 사용하십시오.
   - bulk 작업에서는 `actor_id` 같은 단일 ID를 억지로 넣지 마십시오.
5. **과잉 생성 금지**:
   - 범위 수식이 없는 단순 지칭어(is_category_label: true)는 별도의 생성 작업을 만들지 마십시오.
   - 구체적인 이름이 있는 항목에 대해서만 create를 만드십시오.
6. **ID 필드 및 요약 규격**:
   - `modifications` 내 `params`는 **단일 대상이면 `대상카테고리_id`, 범위 대상이면 `selector`**를 포함해야 합니다.
   - 신규 생성(CREATE)인 경우, ID는 반드시 **"NEW"**여야 합니다. (임의의 숫자를 지어내지 마십시오.)
   - 조회/수정(READ/UPDATE)인 경우, 식별된 **실제 숫자 ID**를 사용하십시오.
7. **아이템(item)의 "효과" / 사용·전투 시 수치 변화 (범용 규칙, 매우 중요)**:
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
8. **스키마 기반 필드 매핑 (범용 원칙)**:
   - 사용자가 **속성·수치·설정 변경**을 요청하면 `params`에서 **스키마 필드 설명(`Field(description=...)`)과 가장 일치하는 필드**를 찾아 매핑하십시오.
   - **애매한 용어**(예: "레벨", "공격력", "속도")는 대상 카테고리 스키마에 있는 **모든 관련 필드의 설명을 검토**한 후, **맥락에 가장 적합한 필드**를 선택하십시오.
   - 예: "액터 레벨 올려줘" → `initialLevel`(시작 레벨)과 `maxLevel`(상한) 중 **맥락상 시작 레벨이 더 적절**하면 `initialLevel`을, **상한 조정**을 의도했으면 `maxLevel`을 선택.
   - **여러 해석이 가능한 경우** 스키마 설명과 기존 값을 참고해 **가장 합리적인 필드**를 우선하되, **명시적 지시어**가 있으면 그것을 따르십시오.
   - 단, bulk selector 기반 update/read에서는 실제 숫자 ID 대신 `selector`를 사용하십시오.
9. **의미 해석 책임**:
   - `property`를 실제 RPG Maker 필드명으로 바꾸는 작업은 당신의 책임입니다.
   - 예: "초기 레벨" -> `initialLevel`, "닉네임" -> `nickname`
   - 코드가 후처리로 필드명을 바꿔주지 않는다고 가정하고 정확한 canonical field를 직접 작성하십시오.
"""


def build_step5_prompt(
    state: AgentState,
    extractions: list,
    classifications: list,
    sys_info: dict,
    schema1: str,
    schema2: str,
    bulk_context: dict | None = None,
    previous_response: dict | None = None,
    extra_instructions: str = "",
) -> list[BaseMessage]:
    # 시스템 프롬프트에 스키마 내용 주입
    system_content = STEP5_SYSTEM_PROMPT.format(schema1=schema1, schema2=schema2)

    context = {
        "user_input": state.get("user_input"),
        "extractions": extractions,
        "classifications": classifications,
        "system_info": sys_info,  # 실제 속성 리스트 등 시스템 데이터 주입
        "bulk_context": bulk_context or {},
        "ranked_map_candidates": state.get("ranked_map_candidates", []),  # 맵 후보군 주입
        "previous_response": previous_response or {},
    }

    human_message = f"""아래 분석 데이터와 실제 시스템 정보를 바탕으로 최종 modifications 리스트를 작성하십시오.

### [분석 데이터 및 시스템 정보]
{context}

### [특별 지시]
- 속성(Element) ID가 필요한 경우, `system_info['elements']` 배열에서 해당 단어와 가장 유사한 항목의 **인덱스 번호**를 `dataId`로 사용하십시오. (예: 4번째에 있다면 4)
- `bulk_context`가 비어 있지 않다면, 그것은 category 전체 수정 후보에 대한 조회 결과 요약입니다. bulk 수정이 필요할 때 이 컨텍스트를 우선 참고하십시오.
- **맵(Map) 추가/삭제 관련**:
  - 사용자가 맵 추가를 요청하면, `ranked_map_candidates` 리스트에서 현재 게임에 없는 가장 적합한(점수 높은) 맵을 선택하십시오.
  - 맵 추가 시 `type: "create"`, `target: "map"`, `params`에는 `name`, `original_file_name`(후보군에서 가져옴)을 포함하십시오.
  - 맵 삭제 시 `type: "delete"`, `target: "map"`, `params`에는 `map_id`를 포함하십시오.
{extra_instructions}
"""

    return [SystemMessage(content=system_content), HumanMessage(content=human_message)]
