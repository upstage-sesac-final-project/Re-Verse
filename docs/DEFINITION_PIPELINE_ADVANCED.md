# 🛠 Definition 노드 고도화 및 데이터 모듈화 상세 명세

본 업데이트는 **멀티 유저 대응(game_id 기반 동적 경로)**, **지능형 의도 분석(7단계 파이프라인)**, 그리고 **데이터 일관성 보장(중앙 집중식 I/O 및 선제적 RAG 동기화)**을 핵심 목표로 합니다.

---

## 1. 중앙 집중식 데이터 접근 계층 (`agent/utils/game_data_io.py`)
기존 노드별로 산재해 있던 파일 읽기/쓰기 로직을 하나의 공통 모듈로 통합했습니다.

*   **동적 경로 제어**: `AgentState`의 `game_id`를 기반으로 사용자별 독립적인 데이터 공간(`storage/games/{game_id}/data/`)에 접근합니다.
*   **추상화된 인터페이스**: 복잡한 파일명 규격을 몰라도 카테고리명(`actor`, `enemy` 등)만으로 데이터 조작이 가능합니다.
*   **주요 기능**:
    - `read_game_json` / `write_game_json`: 멀티 유저 경로 기반 I/O
    - `get_next_entity_id`: 실제 파일의 `max(id) + 1`을 계산하여 데이터 무결성 보장
    - `get_system_context`: 게임 제목, 화폐, 주인공 정보를 결합하여 제공

```python
# [핵심 로직] 유효한 마지막 ID를 찾아 다음 번호를 안전하게 생성
def get_next_entity_id(game_id: str, category: str) -> int:
    data = read_game_json(game_id, category)
    if not data: return 1
    ids = [item["id"] for item in data if item and "id" in item]
    return max(ids) + 1 if ids else 1
```

---

## 2. 지능형 RAG 동기화 엔진 (`agent/rag/retriever.py`)
사용자의 수정 사항이 즉시 검색에 반영되도록 UX 대기 시간을 최소화하는 로직을 구현했습니다.

*   **Hash 기반 증분 업데이트**: 파일 내용의 MD5 해시를 저장하여, **내용이 실제로 변경된 경우에만** 재인덱싱을 수행함으로써 불필요한 계산 리소스를 절약합니다.
*   **선제적 업데이트(Proactive Sync)**: 다음 쿼리 시 대기 시간을 없애기 위해, 그래프 종료 직전(6번 노드 등)에 변경된 파일만 골라 미리 인덱싱을 마칩니다.
*   **동기적 실행 보장**: 백엔드의 로컬 데이터 삭제 정책에 따라, 파일 삭제 전 인덱싱이 완료되도록 `await` 기반의 안정적 프로세스를 구축했습니다.

```python
# [핵심 로직] 해시 비교를 통한 지능적 재인덱싱
async def index_category(self, category: str):
    current_hash = self._get_data_hash(valid_items)
    if existing_hash == current_hash:
        return # 변경 없음 시 0.001초 만에 종료
    # 다를 경우에만 기존 데이터 삭제 및 신규 인덱싱 수행
```

---

## 3. 7단계 지능형 의도 분석 파이프라인 (`agent/graph/nodes/definition.py`)
자연어 요청을 RPG Maker MZ 스키마에 맞는 정밀한 작업 명세서로 변환합니다.

### 파이프라인 단계
1.  **추출**: 핵심 키워드 및 액션(CREATE/UPDATE 등) 분리
2.  **분류**: 엔티티 카테고리 판별 및 지칭어(Label) 식별
3.  **시스템 보정**: "주인공", "화폐" 등 시스템 예약어 실시간 매핑
4.  **ID 매핑**: RAG 검색을 통한 기존 엔티티 ID 특정
5.  **필터링**: 중복된 지칭어 및 과잉 생성 항목 제거 (아이템 vs 회복 포션)
6.  **최종 조립**: `rpgmaker-mz-data-schema.md` 기반 작업 명세 생성
7.  **실시간 ID 할당**: **[Rule-based ID Hijacking]** 신규 생성 건에 대해 실제 파일 기반의 ID 강제 할당

```python
# [핵심 로직] LLM의 추측성 ID를 무시하고 시스템이 계산한 실제 ID로 덮어쓰기
if action_type == "create" or params.get(id_field) == "NEW":
    assigned_id = get_next_entity_id(game_id, target)
    params[id_field] = assigned_id # 룰베이스 기반 강제 수정
```

---

## 4. 프롬프트 엔지니어링 강화 (`agent/prompts/definition_prompt.py`)
LLM이 더 지능적으로 데이터를 완성하고 불필요한 데이터를 생성하지 않도록 지시를 정교화했습니다.

*   **단일 엔티티 원칙 (Single Entity Principle)**: "거미 몬스터 만들어줘" 요청 시 드롭 아이템 등을 지어내지 않고 오직 몬스터 본체만 생성하도록 엄격히 제한.
*   **데이터 추론 (Inference)**: 아이템 이름(예: '체력 회복 포션')에서 기능을 추론하여 `effects` 필드의 상세 코드(11번 HP 회복 등)를 스스로 채우도록 유도.
*   **지칭어 판별 강화**: "아이템", "적"과 같은 단어를 `is_category_label`로 분류하여 중복 생성 로직에서 배제.

---

## ✅ 주요 수정 완료 항목 (Bug Fixes)
1.  **중복 생성 해결**: "아이템"과 "회복 포션"이 각각 생성되던 문제를 지칭어 필터링 로직으로 해결.
2.  **과잉 생성 해결**: 적 생성 시 요청하지 않은 무기/방어구까지 지어내던 문제를 단일 엔티티 원칙 프롬프트로 차단.
3.  **필드 매핑 오류 해결**: `traits`나 `effects`가 빈 값으로 나가던 문제를 이름 기반 데이터 추론 지침으로 보완.
4.  **ID 무결성 확보**: LLM이 임의로 생성하던 `enemy_id: 1`과 같은 값을 실제 파일 조회 기반의 `마지막 ID + 1`로 강제 치환하여 데이터 충돌 방지.

---

**결론**: 이 구조는 백엔드 팀의 S3 동기화 및 로그인 기능 도입에 완벽히 대응하며, 에이전트가 게임의 현재 상태를 정확히 인지하고 다음 답변을 준비하는 **'인덱스 선순환 구조'**를 완성했습니다.
