"""Definition 노드용 프롬프트 빌더 (Multi-Step & Dependency 지원)."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState
from agent.prompts.examples import (
    ACTORS_EXAMPLE_PROMPT,
    ARMORS_EXAMPLE_PROMPT,
    CLASSES_EXAMPLE_PROMPT,
    ENEMIES_EXAMPLE_PROMPT,
    ITEMS_EXAMPLE_PROMPT,
    SKILLS_EXAMPLE_PROMPT,
    WEAPONS_EXAMPLE_PROMPT,
)

# .format() 사용 시 실제 중괄호는 {{ }}로 이중 처리해야 합니다.
BASE_SYSTEM_PROMPT_TEMPLATE = """당신은 RPG Maker MZ 전문 데이터 설계자입니다.
사용자의 요청을 분석하여 데이터 간의 관계를 파악하고, 필요한 모든 작업 단계(조회 및 수정 포함)를 정확히 정의하십시오.

### [RPG Maker MZ 표준 데이터 구조 레퍼런스 (Raw JSON)]
데이터를 생성(CREATE), 조회(READ), 또는 수정(UPDATE)할 때, 반드시 아래 제공된 필드명과 구조(camelCase)를 엄격히 따르십시오.
임의로 필드명을 바꾸거나 없는 필드를 생성하지 마십시오.

- **Skills (스킬)**:
{skills}

- **Items (아이템)**:
{items}

- **Actors (캐릭터)**:
{actors}

- **Weapons (무기)**:
{weapons}

- **Armors (방어구)**:
{armors}

- **Enemies (적)**:
{enemies}

- **Classes (직업)**:
{classes}

[공통 규칙]
- 결과는 반드시 `FinalDefinitionResponse` 구조(modifications 리스트 포함)로 반환하십시오.
- **조회(READ) 요청인 경우에도 반드시 `modifications` 리스트에 해당 작업을 포함해야 합니다.**
- 모든 필드명은 camelCase를 준수하십시오.

### [RPG Maker MZ 표준 데이터 규칙]
1. **Actors (캐릭터)**:
   - `learnings` 필드가 **없습니다**. 특정 캐릭터에게 스킬을 부여하려면 반드시 `traits` 리스트에 추가하십시오.
   - 스킬 추가 Trait 구조: {{"code": 43, "dataId": 스킬ID, "value": 1}}
2. **Classes (직업)**:
   - 특정 레벨에 배우게 하려면 `learnings` 리스트에 추가하십시오.
   - Learning 구조: {{"level": 레벨, "note": "", "skillId": 스킬ID}}
3. **기본 우선순위 (Default Behavior)**:
   - "주인공에게 파이어볼 추가"처럼 '레벨'이나 '직업' 언급이 없는 경우:
     **해당 Actor의 `traits`에 즉시 부여(Code 43)**하는 것을 기본값으로 삼으십시오.
   - "마법사 직업이 배우게 해줘" 또는 "10레벨에 배우게 해줘"라고 명시된 경우에만 `Classes.json`의 `learnings`를 수정하십시오.

### [의존성 및 연결(Linking) 범용 규칙]
1. **데이터 존재 여부 확인**: 대상을 '추가'할 때, 해당 대상이 [Track B] 후보군에 없다면 먼저 `CREATE` 작업을 수행하십시오.
2. **복합 작업 생성**: "A에게 B를 넣어줘" 요청은 반드시 2단계(B 생성 + A의 traits/learnings 연결)로 정의하십시오.
"""

# 주입될 데이터들의 중괄호도 .format()이 해석하지 못하도록 미리 이중 처리하거나,
# 템플릿의 .format 대신 더 단순한 방식을 사용합니다.
# 여기서는 가장 확실한 문자열 치환(replace) 방식을 사용하겠습니다.

BASE_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT_TEMPLATE.replace("{skills}", SKILLS_EXAMPLE_PROMPT)
    .replace("{items}", ITEMS_EXAMPLE_PROMPT)
    .replace("{actors}", ACTORS_EXAMPLE_PROMPT)
    .replace("{weapons}", WEAPONS_EXAMPLE_PROMPT)
    .replace("{armors}", ARMORS_EXAMPLE_PROMPT)
    .replace("{enemies}", ENEMIES_EXAMPLE_PROMPT)
    .replace("{classes}", CLASSES_EXAMPLE_PROMPT)
)

# Router(1번 노드)의 한글 인텐트와 매핑
INTENT_SPECIFIC_INSTRUCTIONS = {
    "게임_요소_생성": """
### [생성(CREATE) 전용 규칙]
- **주체 식별 및 기본값**:
  - 주체(예: "주인공")가 명시된 경우: [대상 생성] -> [Actor의 traits에 연결]의 2단계 작업을 생성하십시오.
  - 별도 언급이 없다면 `Actors.json`의 1번 데이터(ID: 1)를 주인공으로 간주하여 `traits`를 수정하십시오.
- **ID 결정**: 신규 생성 시(CREATE)에는 반드시 제공된 [Track B]의 '신규 생성용 ID'를 사용하십시오.
""",
    "게임_요소_수정": """
### [수정(UPDATE) 및 자동 생성 전용 규칙]
- **능동적 생성(Proactive Create)**: 사용자가 수정을 요청한 대상(예: "슬라임")이 [Track B]의 '기존 데이터' 목록에 없다면, **가장 적절한 카테고리에 해당 엔티티를 새로 생성(CREATE)**하는 단계를 먼저 정의하십시오.
- **카테고리 추론 가이드**:
  - 이름이 몬스터/동물인 경우(슬라임, 고블린, 드래곤 등): `Enemies.json` (적)
  - 이름이 사람 이름인 경우(리드, 프리실라 등): `Actors.json` (캐릭터)
  - 물건 이름인 경우(포션, 검, 갑옷 등): `Items/Weapons/Armors.json`
- **직접 필드 수정**: 능력치(HP, 공격력 등)를 수정하라는 요청은 해당 엔티티의 `params` 필드 등을 직접 수정하는 작업입니다. **이 작업을 위해 새로운 스킬(Skills)이나 아이템을 생성하지 마십시오.**
- **작업 순서**: 대상이 없을 경우 [신규 생성] -> [필드 수정] 순서로 단계를 정의하십시오.
""",
    "게임_요소_조회": """
### [조회(READ) 전용 규칙]
- 데이터를 읽어오는 작업입니다.
- **반드시** `modifications` 리스트에 `action="READ"` 작업을 하나 이상 정의하십시오.
- `target_field`에는 조회할 구체적인 필드명(예: params[0], gold, description 등)을 명확히 명시하십시오.
- 조회 작업이므로 `new_value`는 필요하지 않습니다.
""",
    "추가_정보_필요": """
### [추가정보 필요 전용 규칙]
- 정보가 매우 부족한 경우에만 사용하고, 웬만하면 기본값(주인공의 traits 등)을 적용하십시오.
""",
}


def build_prompt(
    state: AgentState, knowledge_context: str, retrieved_context: str
) -> list[BaseMessage]:
    intent = state.get("intent", "게임_요소_수정")
    specific_instruction = INTENT_SPECIFIC_INSTRUCTIONS.get(
        intent, INTENT_SPECIFIC_INSTRUCTIONS.get("게임_요소_수정")
    )

    system_message = f"{BASE_SYSTEM_PROMPT}\n{specific_instruction}\n\n### [Track A: 기술 지식]\n{knowledge_context}"
    human_message = f"""### [Track B: 엔티티 및 ID 정보]
{retrieved_context}

### [ID 매칭 및 선택 규칙]
1. **정확한 매칭**: '기존 데이터' 목록에서 사용자의 요청과 이름이 가장 유사한 항목의 ID를 사용하십시오.
2. **할루시네이션 방지**: 목록에 없는 ID(예: 예시에서 본 ID 11 등)를 임의로 지어내지 마십시오. 오직 제공된 [Track B]의 ID만 사용하십시오.
3. **단일 대상 우선**: 사용자가 명시적으로 여러 대상을 지칭하지 않는 한, 가장 적절한 엔티티 하나에 대해서만 작업을 생성하십시오.

### [사용자 요청]
- 원문: "{state.get("user_input", "")}"
- 파악된 의도: "{intent}"

위 정보를 바탕으로 모든 작업 단계를 정의하십시오. Actors에게는 `learnings`를 절대 사용하지 말고 `traits`를 사용하십시오.
"""

    return [SystemMessage(content=system_message), HumanMessage(content=human_message)]
