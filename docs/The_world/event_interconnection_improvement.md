# 이벤트 간 연동(Switch Chain) 개선안

> 작성일: 2026-04-10
> 상태: 개선안 제안 (미구현)
> 분석: [event_interconnection_analysis.md](event_interconnection_analysis.md) 참조
> 관련 코드: `agent/generation/compilers/`, `agent/generation/nodes/event_planner.py`, `agent/generation/prompts/event_planner_prompt.py`

---

## 개선안 A: DSL 필드 확장 (최소 변경)

**범위**: DSL 모델 + 컴파일러만 수정. 프롬프트/LLM 동작은 기존과 동일하게 유지.

**변경 사항**:

1. **TransferEvent에 `condition_switch` 추가**
   ```python
   class TransferEvent(BaseModel):
       ...
       condition_switch: str | None = None  # 추가: 스위치 ON일 때만 이동
       blocked_dialogue: str | None = None  # 추가: 조건 미충족 시 메시지
   ```
   - 컴파일러: condition_switch가 있으면 2페이지 구성 (page1: blocked_dialogue, page2: transfer)
   - RPG Maker MZ 동작: 마지막 유효 페이지 우선이므로 switch ON → page2 활성 → 이동

2. **ShopEvent에 `condition_switch` 추가**
   ```python
   class ShopEvent(BaseModel):
       ...
       condition_switch: str | None = None  # 추가: 스위치 ON일 때만 상점 오픈
   ```
   - 컴파일러: NPC와 동일한 2페이지 패턴 적용

**장점**: 변경 최소. LLM이 이미 아는 `condition_switch` 패턴만 확장.
**단점**: 아이템 조건, 변수 카운터는 여전히 불가.

---

## 개선안 B: 아이템 조건 추가 (A 포함 + 아이템 퀘스트)

**범위**: A의 모든 변경 + 아이템 기반 조건/소비 지원.

**변경 사항** (A에 추가):

3. **NpcEvent에 `required_item` 추가**
   ```python
   class NpcEvent(BaseModel):
       ...
       required_item: str | None = None    # 아이템 소지 시 대화 분기
       consume_item: bool = False          # True면 아이템 소비 후 대화
   ```
   - 컴파일러: `code 111, parameters [4, itemId]` (아이템 소지 분기)
   - 소비: `code 126, parameters [itemId, 0, 1, -amount]` (아이템 감소)

4. **ChestEvent에 `condition_switch` 추가**
   ```python
   class ChestEvent(BaseModel):
       ...
       condition_switch: str | None = None  # 스위치 ON일 때만 보물상자 출현
   ```

**장점**: "열쇠를 가져오면 문이 열린다", "약초를 NPC에게 전달" 같은 핵심 퀘스트 가능.
**단점**: 컴파일러 분기가 복잡해짐. 프롬프트에 아이템 조건 예시 필요.

---

## 개선안 C: 이벤트 체인 매니페스트 (A+B 포함 + 구조적 연동)

**범위**: A+B의 모든 변경 + 스토리 흐름을 명시적으로 정의하는 매니페스트 도입.

**핵심 아이디어**: LLM에게 개별 이벤트를 만들라고 하기 전에, **"이벤트 체인 계획"** 을 먼저 생성.

**변경 사항** (A+B에 추가):

5. **GameSpec에 `event_chains` 필드 추가**
   ```python
   class EventChain(BaseModel):
       name: str                    # "마왕성 입장 퀘스트"
       steps: list[ChainStep]       # 순서가 있는 단계들

   class ChainStep(BaseModel):
       map: str                     # 이 단계가 발생하는 맵
       event_type: str              # npc, battle, chest 등
       description: str             # "장로에게 말을 걸면 열쇠를 받는다"
       sets_switch: str | None      # 이 단계가 완료되면 켜는 스위치
       requires_switch: str | None  # 이 단계를 시작하려면 필요한 스위치
       requires_item: str | None    # 이 단계를 시작하려면 필요한 아이템
   ```

6. **A노드(game_designer)가 event_chains를 함께 기획**
   - 스토리 acts와 연동하여 "어떤 순서로 이벤트가 이어지는지" 정의
   - 이 체인이 F노드 프롬프트에 주입되어 LLM이 참조

7. **스위치 참조 검증 추가**
   ```python
   # event_planner.py의 _validate_name_refs에 추가
   if hasattr(e, 'condition_switch') and e.condition_switch:
       if e.condition_switch not in all_switch_names:
           logger.warning("switch '%s' 참조되었으나 어디서도 set되지 않음", ...)
   ```

**장점**: 이벤트 연동이 "우연히 스위치 이름이 맞아야" 하는 게 아니라 구조적으로 보장됨.
**단점**: 구현 범위 큼. game_designer 프롬프트도 대폭 수정 필요.

---

## 개선안 D: 프롬프트 개선만 (코드 변경 없음)

**범위**: event_planner_prompt.py만 수정. 기존 DSL 필드만으로 최대한 활용.

**변경 사항**:

8. **프롬프트에 연동 패턴 예시 추가**
   ```
   ## 이벤트 연동 패턴

   ### 패턴 1: 보스 처치 → NPC 대화 변경
   - battle: on_win.set_switch: "마왕_defeated"
   - npc: condition_switch: "마왕_defeated", alt_dialogue: "평화가 왔어요!"

   ### 패턴 2: NPC 대화 → 다른 이벤트 활성화
   - npc: set_switch: "quest_accepted"
   - npc (다른 맵): condition_switch: "quest_accepted"

   ### 패턴 3: 보물 획득 기록
   - chest: chest_switch: "chest_01_opened"
   - npc: condition_switch: "chest_01_opened"
   ```

9. **맵 간 스위치 참조 규칙 명시**
   ```
   ## 스위치 이름 규칙
   - 사전 할당 스위치를 우선 사용할 것
   - 새 스위치 생성 시: {목적}_{대상} 형식 (예: quest_elder_talked)
   - 같은 스위치 이름은 맵이 달라도 동일한 게임 상태를 의미함
   ```

10. **"스토리 흐름 표" 섹션 추가** — LLM이 이벤트 작성 전에 스위치 흐름을 먼저 정리하도록 유도
    ```
    ## 이 맵의 스위치 흐름
    아래 표를 먼저 작성한 뒤 이벤트를 생성하세요:
    | 이벤트 | 확인하는 스위치 | 설정하는 스위치 |
    ```

**장점**: 코드 변경 제로. 즉시 적용 가능.
**단점**: Transfer/Shop 조건 문제는 해결 불가. LLM이 지시를 따르지 않을 수 있음.

---

## 개선안 비교

| 기준 | A: DSL 확장 | B: A + 아이템 | C: A+B + 매니페스트 | D: 프롬프트만 |
|------|:-:|:-:|:-:|:-:|
| 구현 난이도 | 낮음 | 중간 | 높음 | 최소 |
| Transfer 조건 이동 | **O** | **O** | **O** | X |
| Shop 조건 해금 | **O** | **O** | **O** | X |
| 아이템 조건 퀘스트 | X | **O** | **O** | X |
| 구조적 연동 보장 | X | X | **O** | X |
| 스위치 검증 | X | X | **O** | X |
| 코드 변경량 | ~100줄 | ~200줄 | ~500줄+ | 0줄 |
| 기존 테스트 영향 | 낮음 | 중간 | 높음 | 없음 |

---

## 권장 실행 순서

즉시 적용 가능한 것부터 단계적으로:

```
Phase 1: D (프롬프트 개선) — 코드 변경 없이 즉시 효과
    ↓
Phase 2: A (DSL 필드 확장) — transfer/shop condition_switch
    ↓
Phase 3: B (아이템 조건) — required_item, consume_item
    ↓
Phase 4: C (매니페스트) — event_chains로 구조적 보장
```

각 Phase는 독립 PR로 분리 가능. Phase 1만으로도 현재 "이벤트가 이어지지 않는" 문제의 상당 부분이 개선됨.
