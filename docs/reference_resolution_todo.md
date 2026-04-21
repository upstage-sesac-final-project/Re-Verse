# 참조 해결 (reference resolution) 강화 TODO

2026-04-19 로컬 테스트 중 드러난 갭. 본체 통합 sprint 범위 밖 — 차기 sprint 에서 다룬다.

## 배경

현재 `reference_checks` 는 "해당 이름의 엔티티가 있냐 / 없냐 / 애매하냐" 수준의 단일-엔티티
존재 확인만 수행한다. 복합 참조 관계 (예: "무기를 만들어서 액터에게 장착", "스킬을
배울 수 있게 직업에 연결") 는 operation_tuples 가 여러 단계로 펼쳐질 때 각 step 사이의
의미적 연결을 만들어내지 못하고 있다.

## 드러난 증상

| 입력 | 관찰 | 기대 |
|---|---|---|
| "엑스칼리버 만들어서 엘리아스에게 장착시켜줘" | Weapons.json.create 만 수행. 장착 누락 | 무기 create → 엘리아스(Actor)의 initialEquips 에 weapon_id 삽입 |
| "화염검 만들어서 주인공에게 장착해줘" | 무기만 생성 | 무기 create → 주인공(System.startingParty[0])의 직업(Class)의 허용 무기 유형 확인 → initialEquips 또는 직업의 traits 에 equip 허용 추가 |
| "파이어볼 스킬 만들어서 마법사한테 추가" | Skills.json.create 만 | 스킬 create → 마법사(Class)의 learnings 에 추가 (또는 learning 불가면 hold) |
| "드래곤 만들고 드롭 아이템에 드래곤의 비늘 생기게 해줘" | multi_intent 로 terminal | Enemy create → Item "드래곤의 비늘" create → Enemy.dropItems 에 연결 |

## 필요한 것

1. **참조 토폴로지 모델** — "무기 → 액터 장비", "스킬 → 직업 learnings", "아이템 → 적
   dropItems" 등 RPG Maker MZ 의 엔티티 간 참조를 graph 로 선언.
2. **복합 명령 분해** — Router 가 multi_intent 로 terminal 하지 않고, "A 만들고 B 에
   연결" 같은 자연 패턴을 operation_tuples 여러 개로 펼쳐야 함.
3. **선행 create + 후속 wire 패턴** — planner 의 dependencies.py + handlers 가 `_equip`,
   `_add_learning`, `_add_drop_item` 같은 wire 액션을 이미 일부 지원 — 이 경로를
   reference_checks 와 operation_tuples 가 실제로 채우도록 연결해야 함.
4. **주인공/파티/플레이어블 해소 (bulk_scope 확장)** — 단일 "주인공" 외에 "주인공
   파티", "플레이어블 액터 전부" 를 System.startingParty 기반으로 실제 ID list 로 해소.
   현재 `_FILE_LABEL_TO_CATEGORY` 는 단일 카테고리만.

## 짚어둘 것 (구현 시 참고)

- `agent/editor/nodes/planner/dependencies.py` 의 `lookup_requirements` 가 이미
  "무기 create → initialEquips 세팅" 같은 의존성 그래프를 가지고 있음 → 여기 내용을
  reference_checks 와 조합해야 함
- `system_ref=party` 를 추가하려면 `get_system_context` 확장 + Step 3 resolver 추가
- 복합 명령 분해는 Router parsed_extractions 가 이미 부분 해결 — 이걸 action 이 다른
  케이스 ("create A + equip to B") 로 확장 필요

---

## 2026-04-19 18:30 로컬 테스트 후속 이슈 (미해결)

### Issue A — Actor + 직업 composite 에서 Class 선행 create 가 실제로 안 됨

**입력**: "액터로 경찰 '이자야'도 추가해줘. 체력 400 mp 30 atk 15로."

**결과**: Actor `이자야` (id=3) 는 만들어졌지만 Class `경찰` 은 **선행 create 안 됐음**. 경고
2 건 (스탯은 Classes 에 / 직업 '경찰' Classes.json 에 없음) 만 내려옴.

**원인**: `agent/editor/nodes/planner/__init__.py` 의 `_consume_reference_checks` 가
`not_found + (op 이 update/delete/read 일 때)` 에만 선행 create 를 prepend 함.
**Actor create 하나만 있는 경우는 prepend 트리거 안 됨** — Class 가 "참조되는
엔티티" 지 "수정 대상" 이 아님에도 로직이 놓침.

**수정 방향**:
- `_consume_reference_checks` 조건 확장: ops 중 어느 것도 그 reference_checks entry 의
  (file, name) 을 **대상** 으로 갖지 않으면 "참조용 not_found" 로 간주 → 선행 create
  prepend
- 또는 separate 로직: `reference_checks[i].category` 가 Actor create 의 classId 참조
  카테고리 (Class) 면 무조건 선행

### Issue B — "직업에 경찰 추가해줘 체력은 400 MP는 30 ATK는 15" → skill bulk 로 오분류

**입력**: "직업에 경찰 추가해줘 체력은 400 MP는 30 ATK는 15"

**결과**: 응답 "현재 전체 대상 bulk 수정은 skill 카테고리를 지원하지 않습니다."

**원인 후보** (로그 필요):
1. Router 가 "직업" 을 field="직업" 으로 세팅 안 하고 Definition Step 2 LLM 이
   skill 로 분류
2. Router parsed_command 는 맞았는데 Definition 의 `_detect_unsupported_bulk_targets`
   가 "직업 + 여러 스탯" 을 bulk 로 해석하고 skill 로 잘못 매핑 (매우 이상함)

**확인 방법**: 다음 재현 시 Router intent / field / Definition Step 2 classifications
로그 필요.

**수정 방향 (가정)**:
- Router 프롬프트에 "직업 = Class" 매핑 재확인 + "직업에 X 추가" = object_create
  (Class 생성) 명시 예시 추가
- `_detect_unsupported_bulk_targets` 의 "Class 지시어 판정" 확인. "직업" 이 category
  label 로 잡혀서 bulk 취급되는지
