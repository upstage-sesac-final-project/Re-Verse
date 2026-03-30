# Definition Node 재설계 계획

## 1~4단계: 데이터 식별 및 ID 확정 (완료)
- **1단계**: 키워드 추출 (Action, Subject, Property, Value)
- **2단계**: 카테고리 분류 (Actor, Enemy, Item, Skill, Weapon, Armor, Class, System) 및 확신도 점수 계산
- **3단계**: 시스템 보정 ("주인공" -> Actor ID 1 등)
- **4단계**: 구체적 ID 매핑 (RAG 검색 + 문자열 유사도 체크를 통한 ID 확정)

---

## 5단계: 필드 명세화 및 최종 조립 (Specification & Final Assembly)

### 1. 목표
1~4단계의 결과를 종합하여 `rpgmaker-mz-data-schema.md` 규격에 맞는 최종 수정 명세(JSON)를 생성한다.

### 2. 매핑 사전 (Reference: rpgmaker-mz-data-schema.md)
LLM은 아래의 표준 스키마를 엄격히 준수하여 번역한다.

| 자연어 (자주 쓰이는 표현) | 내부 필드명 (camelCase) | 비고 |
| :--- | :--- | :--- |
| 체력, HP | `params[0]` | MHP (최대 HP) |
| 마력, MP | `params[1]` | MMP (최대 MP) |
| 공격력 | `params[2]` | ATK |
| 방어력 | `params[3]` | DEF |
| 가격, 원, G | `price` | Items, Weapons, Armors 공통 |
| 회복량 | `damage.value` 또는 `effects` | 아이템/스킬 설정에 따름 |
| 직업 | `classId` | Actors.json 필드 |

### 3. 최종 출력 규격 (PROGRESS.md 준수)
LLM은 최종적으로 `FinalDefinitionResponse` 구조를 반환하며, `modifications` 리스트는 아래 형식을 따른다.

```json
{
  "target_files": ["Enemies.json"],
  "modifications": [
    {
      "type": "update",
      "target": "enemy",
      "params": {
        "enemy_id": 1,
        "params[0]": 500
      }
    }
  ],
  "extracted_ids": { "enemy_id": 1 },
  "params_sufficient": true
}
```

### 4. 조립 원칙
- **작업 통합**: 한 대상에 대한 '생성'과 '속성 수정'은 하나의 작업(`create` 또는 `update`)으로 합친다.
- **카테고리 우선순위**: 사용자의 호칭보다 2단계 점수가 높거나 4단계 검색 결과가 뚜렷한 카테고리를 최종 선택한다.
- **타입 정규화**: 수치 데이터는 정수(int) 또는 실수(float)로 정규화한다.
