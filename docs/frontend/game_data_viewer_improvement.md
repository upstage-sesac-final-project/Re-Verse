# GameDataViewer 시각화 개선 계획

> 대상 파일: `app/frontend/src/components/game/GameDataViewer.jsx`

## 현재 상태 (As-Is)

| 항목 | 현재 동작 | 문제 |
|------|----------|------|
| 배열 필드 (traits, equips, effects 등) | `[3개]` 텍스트만 표시 | 내용 확인 불가 |
| 객체 필드 (damage, battleBgm 등) | `{...}` 텍스트만 표시 | 내용 확인 불가 |
| ID 참조 (classId, skillId 등) | 숫자만 표시 (`classId: 1`) | 다른 JSON 크로스 참조 없음 |
| 카드 접힌 상태 | `#1 전사` (id + 이름만) | 핵심 스탯 안 보임 |
| 2차원 params (Classes) | 1차원 8개로 잘림 | 레벨별 곡선 데이터 유실 |
| 데이터 탐색 | 스크롤만 가능 | 검색/필터 없음 |

---

## Phase 1: 숨겨진 데이터 펼치기

**목표**: `[N개]`, `{...}`로 가려진 데이터를 실제로 볼 수 있게 한다.

### 변경 사항

1. **배열 인라인 렌더링** — `ValueCell` 컴포넌트 수정
   - traits: `[{code, dataId, value}]` → 뱃지로 표시 (예: `공격력 +10%`, `속성: 화염`)
   - equips: `[weaponId, shieldId, ...]` → 슬롯별 라벨 (무기, 방패, 머리, 몸, 장신구)
   - learnings: `[{level, skillId}]` → `Lv.5: 파이어`, `Lv.10: 힐` 형태
   - dropItems: `[{kind, dataId, denominator}]` → `회복포션 (1/3 확률)` 형태
   - effects: `[{code, dataId, value1, value2}]` → `HP 회복 +500` 형태
   - actions (Enemy): `[{skillId, rating}]` → `공격 (R:5)`, `파이어 (R:3)` 형태

2. **객체 인라인 렌더링**
   - damage: `{type, formula, elementId}` → `물리: a.atk * 2 - b.def` 형태
   - battleBgm: `{name, volume, pitch}` → `Battle1 (vol:90 pit:100)` 형태

3. **2차원 params 처리** (Classes.json)
   - 레벨 1과 최대 레벨(99) 값만 요약: `MHP: 400→8000, ATK: 20→150`

### 검증
- 모든 JSON 탭에서 카드 펼치기 → 배열/객체 필드가 읽을 수 있는 텍스트로 표시되는지 확인

---

## Phase 2: ID → 이름 크로스 참조

**목표**: 숫자 ID를 사람이 읽을 수 있는 이름으로 표시한다.

### 변경 사항

1. **참조 테이블 빌드** — 컴포넌트 마운트 시 주요 JSON을 미리 fetch
   ```
   classes:  { 1: "전사", 2: "마법사" }
   skills:   { 1: "공격", 2: "파이어" }
   items:    { 1: "회복 포션" }
   weapons:  { 1: "강철 검" }
   armors:   { 1: "가죽 갑옷" }
   enemies:  { 1: "슬라임" }
   states:   { 1: "전투불능" }
   ```

2. **ID 필드 자동 변환** — `ValueCell`에서 필드명 기반 매핑
   | 필드명 | 참조 대상 |
   |--------|----------|
   | classId | Classes |
   | skillId | Skills |
   | equipId / equips[n] | Weapons (n=0), Armors (n=1~4) |
   | stypeId | 고정 맵 (1=마법, 2=필살기) |
   | elementId | System.json elements |
   | stateId | States |

3. **표시 형식**: `전사 (#1)` — 이름 + 작은 ID

### 검증
- Actors 탭에서 classId가 직업명으로 표시되는지
- Skills 탭에서 learnings의 skillId가 스킬명으로 표시되는지
- equips 배열이 실제 장비 이름으로 표시되는지

---

## Phase 3: 카드 요약 강화

**목표**: 카드를 펼치지 않아도 핵심 정보를 한눈에 파악할 수 있게 한다.

### 변경 사항

1. **파일별 요약 라인** — 접힌 카드 헤더에 핵심 스탯 표시

   | 파일 | 요약 예시 |
   |------|----------|
   | Actors | `#1 용사 — 전사 Lv.1~99 장비: 강철검/가죽갑옷` |
   | Classes | `#1 전사 — MHP 400→8000 스킬 5개` |
   | Enemies | `#1 슬라임 — HP:500 ATK:15 EXP:20 Gold:10` |
   | Skills | `#3 파이어 — MP:5 범위:적1체 위력: a.mat*2` |
   | Items | `#1 회복포션 — HP+500 가격:50` |
   | Weapons | `#1 강철검 — ATK+10 가격:200` |
   | Armors | `#1 가죽갑옷 — DEF+5 가격:100` |
   | States | `#1 전투불능 — 우선도:100 행동불가` |

2. **ItemCard 컴포넌트 분리** — 파일 타입별 `SummaryLine` 서브컴포넌트
   - `ActorSummary`, `EnemySummary`, `SkillSummary` 등
   - Phase 2의 참조 테이블 활용

### 검증
- 접힌 상태에서 각 카드의 요약이 정확한지 확인
- 스크롤 없이 리스트만 보고 데이터 파악이 가능한지

---

## Phase 4: 검색 및 필터

**목표**: 데이터가 많아도 원하는 항목을 빠르게 찾을 수 있게 한다.

### 변경 사항

1. **텍스트 검색바** — 탭 아래에 검색 input 추가
   - name, description 필드에서 부분 일치 검색
   - 디바운스 300ms

2. **정렬 옵션** — ID순 (기본), 이름순, 가격순 등 파일별 정렬 기준
   - 토글 버튼으로 오름차순/내림차순

3. **전체 펼치기/접기 버튼**

### 검증
- 검색어 입력 시 실시간 필터링 동작 확인
- 정렬 변경 시 카드 순서 즉시 반영 확인

---

## 우선순위 요약

| Phase | 예상 영향 | 의존성 |
|-------|----------|--------|
| Phase 1 | 가장 큼 — 현재 안 보이는 데이터가 보이게 됨 | 없음 |
| Phase 2 | 가독성 대폭 향상 — 숫자 ID가 이름으로 변환 | Phase 1 이후 |
| Phase 3 | 탐색 효율 향상 — 펼치지 않아도 핵심 파악 | Phase 2 이후 (참조 테이블 필요) |
| Phase 4 | 편의 기능 — 데이터 많을 때 유용 | Phase 3 이후 |
