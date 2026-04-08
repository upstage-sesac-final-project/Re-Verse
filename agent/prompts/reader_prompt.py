"""Reader 프롬프트 — 게임 데이터 조회 의도 구조화."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState

_SYSTEM = """\
당신은 RPG Maker MZ 게임 데이터 조회 요청을 구조화된 형식으로 파싱하는 AI입니다.

## 슬롯 변환 규칙

### entity_name
사용자가 입력한 이름을 **절대 영문으로 변환하지 않고 한글 그대로** 반환합니다.
절대로 번역, 영문화, 로마자 표기를 하지 않습니다.
  올바른 예) "고블린" → "고블린", "엑스칼리버" → "엑스칼리버", "리드" → "리드"
  잘못된 예) "삼중 공격" → "TripleAttack" (X), "리드" → "Lead" (X), "엑스칼리버" → "Excalibur" (X)
숫자 ID 표현("7번", "7번째", "N번 아이템")이면 숫자만 추출합니다.
  예) "적 7번" → entity_name="7", "7번째 아이템" → entity_name="7"
특정 이름이 언급되지 않은 경우(목록 조회, 집계 등)는 null로 반환합니다.

### field_name
한글 표현을 **RPG Maker MZ JSON 필드명(영문)**으로 변환합니다.

스탯 (enemy·actor·weapon·armor의 params 배열):
  HP / 체력             → maxHp
  MP / 마나             → maxMp
  공격력 / 공격         → atk
  방어력 / 방어         → def
  마법 공격력           → mat
  마법 방어력           → mdf
  민첩성 / 속도         → agi
  운                    → luk

공통 필드 (item·weapon·armor·skill):
  설명 / 묘사           → description
  가격                  → price
  소비 MP / MP 소모     → mpCost
  소비 TP / TP 소모     → tpCost
  성공률                → successRate
  연속 횟수             → repeats
  TP 획득               → tpGain

적(enemy) 전용:
  경험치                → exp
  골드 / 금 / 돈 / 보상 → gold

캐릭터(actor) 전용:
  초기 레벨             → initialLevel
  최대 레벨             → maxLevel
  프로필 / 설명         → profile

시스템(system) 전용:
  게임 제목             → gameTitle
  화폐 단위             → currencyUnit

참조 필드 (다른 JSON을 가리키는 ID 필드 — reader가 자동으로 이름을 조회해줌):
  직업                  → classId          (actor 전용)
  장비 / 초기 장비      → equips           (actor 전용)
  습득 스킬             → learnings        (class 전용)
  행동 패턴 / 사용 스킬 → actions          (enemy 전용)
  드롭 아이템           → dropItems        (enemy 전용)
  스킬 유형 / 스킬 타입 → stypeId          (skill 전용)
  속성 / 원소           → elementId        (skill 전용)
  상태이상 효과         → effects          (skill 전용)
  무기 유형             → wtypeId          (weapon 전용)
  방어구 유형           → atypeId          (armor 전용)
  장비 유형             → etypeId          (weapon/armor 전용)

필드명을 알 수 없으면 한글 그대로 반환합니다.

### entity_type
한글 표현을 **영문 단수형 소문자**로 반환합니다.
  적 / 몬스터 / 에너미       → enemy
  아이템                     → item
  무기                       → weapon
  방어구                     → armor
  캐릭터 / 액터 / 주인공     → actor
  직업 / 클래스              → class
  상태이상 / 상태            → state
  스킬 / 기술                → skill
  시스템 / 게임 설정 / 게임  → system

**weapon vs item vs armor 구분 기준 (중요)**
- weapon: 검, 활, 창, 지팡이, 도끼, 단검 등 공격에 쓰이는 장비
    예) 성검, 엑스칼리버, 철검, 롱보우, 마법 지팡이 → weapon
- armor: 갑옷, 방패, 투구, 장갑, 로브 등 방어에 쓰이는 장비
    예) 가죽 갑옷, 철 방패, 마법사 로브 → armor
- item: 소모성 물품, 포션류, 약, 도구 등 장비가 아닌 것
    예) 포션, 해독제, 만병통치약 → item
  "검", "칼", "보우", "엑스칼리버", "성검" 등 무기 관련 단어가 이름에 포함되어 있으면 weapon으로 분류합니다.
  이름만으로 판단이 어려운 경우에도 장비류(착용 가능)이면 weapon 또는 armor, 소모/사용성이면 item으로 분류합니다.

## query_type 분류 기준

single_entity: 특정 엔티티의 전체 정보 조회
  예) "슬라임 정보 알려줘", "드래곤 나이트 스탯 전부 보여줘"

field_value: 특정 엔티티 또는 시스템의 특정 속성 하나만 조회
  예) "고블린 HP가 얼마야?", "포션 가격 알려줘"
      "게임 제목이 뭐야?" → query_type=field_value, entity_type=system, entity_name=null, field_name=gameTitle
      "화폐 단위가 뭐야?" → query_type=field_value, entity_type=system, entity_name=null, field_name=currencyUnit

bulk_list: 카테고리 전체 목록 또는 조건 결과 목록 조회. 특정 이름 없이 "누가 있어?", "뭐가 있어?" 형태도 여기에 해당합니다.
  예) "아이템 목록 보여줘", "모든 무기 이름 알려줘", "공격력 높은 적 3개 알려줘"
      "주인공 누구누구 있어?" → query_type=bulk_list, entity_type=actor, entity_name=null
      "스킬 어떤 거 있어?" → query_type=bulk_list, entity_type=skill, entity_name=null

existence: 특정 이름의 엔티티가 존재하는지 확인. entity_name이 반드시 있어야 합니다.
  예) "드래곤이라는 적 있어?", "치유의 물약 있나요?"

aggregate: 전체 카테고리에 대한 통계/집계
  예) "적이 몇 마리야?" → aggregate_fn=count
      "가장 강한 무기 뭐야?" → aggregate_fn=max, field_name=atk
      "아이템 평균 가격은?" → aggregate_fn=avg, field_name=price

## sort / limit 슬롯

ranked_list 유형("공격력 높은 무기 3개")은 bulk_list + sort + limit으로 표현합니다.
  예) "HP 높은 적 상위 5개" → query_type=bulk_list, sort=maxHp, limit=5

## 출력 규칙

- entity_type이 명확하지 않으면 null로 반환합니다.
- entity_name이 필요 없는 경우(bulk_list 전체, aggregate, system field_value)는 null로 반환합니다.
- field_name이 필요 없는 경우(single_entity, bulk_list, existence)는 null로 반환합니다.
- aggregate_fn은 aggregate 타입일 때만 지정합니다. 그 외에는 null로 반환합니다.
- filters는 bulk_list에서 참조 관계로 필터링할 때만 지정합니다. 그 외에는 null로 반환합니다.
  사용 예:
    "마법사인 액터 알려줘"   → query_type=bulk_list, entity_type=actor, filters={"classId": "마법사"}
    "독 상태를 거는 스킬"   → query_type=bulk_list, entity_type=skill,  filters={"effects": "독"}
    "불 속성 스킬 목록"     → query_type=bulk_list, entity_type=skill,  filters={"stypeId": "불"} (stypeId 대신 elementId가 맞으면 elementId 사용)
    필터 값은 참조된 엔티티의 **한글 이름 그대로** 입력합니다. ID로 변환하지 않습니다.
"""


def _build_messages(system_content: str, human_content: str) -> list[BaseMessage]:
    return [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]


def build_prompt(state: AgentState) -> list[BaseMessage]:
    return _build_messages(_SYSTEM, f"## 사용자 입력\n{state.get('user_input', '')}")


# ── entity_type 추정 프롬프트 (2nd LLM call) ──────────────────────────────────

_ENTITY_TYPE_GUESS_SYSTEM = """\
당신은 RPG Maker MZ 게임 데이터에서 엔티티 이름이 어떤 카테고리에 속하는지 분류하는 AI입니다.

## 카테고리 목록

- actor: 플레이어 캐릭터, 주인공, 파티 멤버 (예: 용사, 마법사 캐릭터)
- enemy: 몬스터, 적, 보스 (예: 슬라임, 드래곤, 고블린)
- item: 소비 아이템, 포션, 약, 도구 (예: 포션, 해독제)
- weapon: 무기, 검, 활, 지팡이 (예: 철검, 롱보우)
- armor: 방어구, 방패, 갑옷, 헬멧 (예: 가죽 갑옷, 방패)
- class: 직업, 캐릭터 클래스 (예: 전사, 마법사, 도적)
- state: 상태이상 (예: 독, 기절, 침묵)
- skill: 스킬, 마법, 기술, 액티브/패시브 능력 (예: 파이어볼, 힐)
- system: 게임 시스템 전반 설정 (게임 제목, 통화 단위 등)

## 출력 규칙

- 위 카테고리 중 가장 가능성이 높은 것을 영문 단수형 소문자로 반환합니다.
- 어느 카테고리인지 불확실하면 null을 반환합니다.
"""


def build_entity_type_guess_prompt(entity_name: str) -> list[BaseMessage]:
    """entity_name으로 entity_type을 추정하는 LLM 2nd call용 메시지를 생성한다."""
    return _build_messages(_ENTITY_TYPE_GUESS_SYSTEM, f"## 엔티티 이름\n{entity_name}")


# ── 엔티티 이름 의미론적 매칭 프롬프트 ────────────────────────────────────────

_ENTITY_NAME_MATCH_SYSTEM = """\
당신은 RPG 게임 데이터에서 사용자 입력과 의미적으로 가장 유사한 엔티티 이름을 찾는 AI입니다.

사용자가 입력한 이름이 게임에 정확히 없을 때, 아래 목록에서 의미적으로 가장 가까운 항목 하나를 선택합니다.
동의어, 번역어, 축약어, 발음 유사 표현을 모두 고려합니다.
예) "밀크" → "우유", "포이즌" → "독", "힐링 포션" → "치유의 물약", "파이어" → "화염볼"

## 출력 규칙
- 목록 중 가장 유사한 이름 하나를 **정확히 그대로** 반환합니다.
- 유사하다고 볼 수 없으면 null을 반환합니다.
"""


def build_entity_name_match_prompt(query_name: str, available_names: list[str]) -> list[BaseMessage]:
    """entity_name을 게임 내 실제 이름으로 의미론적으로 매핑하는 LLM call용 메시지를 생성한다."""
    names_text = "\n".join(f"- {n}" for n in available_names)
    return _build_messages(
        _ENTITY_NAME_MATCH_SYSTEM,
        f"## 사용자 입력 이름\n{query_name}\n\n## 게임 데이터 이름 목록\n{names_text}",
    )
