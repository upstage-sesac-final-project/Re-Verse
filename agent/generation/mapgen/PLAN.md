# 맵 선택기 구현 계획 (mapgen Phase 1)

> **목표**: "게임 생성" 쿼리가 들어오면, 사용자의 의도에 맞는 샘플 맵 3~10개를 `agent/rag/data/samplemaps/`에서 골라 신규 게임의 초기 맵으로 사용한다.
>
> **범위**: 최초 게임 생성 경로 전용. "게임 수정" 경로는 건드리지 않는다. 이벤트 생성/편집은 담당 범위 밖이므로, 샘플 맵이 이미 가진 이벤트는 그대로 사용한다.

---

## 1. 배경 및 설계 원칙

### 1.1 왜 RAG를 안 쓰는가
- 후보가 293개뿐 → 벡터 DB/임베딩 인프라가 과한 오버헤드
- `map_metadata.json`이 이미 정제된 구조화 자산(tags, description, tileset_id) → 임베딩으로 흐릿하게 만들 이유 없음
- 태그 명시 매칭이 "판타지"류 상위 쿼리에서 의미 유사도보다 정확함
- 디버깅 가능(점수/필터 투명)

### 1.2 확장성 관점 — Phase 2(타일 조립)를 미리 고려
1차에선 샘플 선택, 2차에선 타일 하나하나 깔아서 맵을 조립할 계획이다. 두 단계가 공유하는 **유일한 영구 자산**은 "쿼리 → 구조화된 의도"이다. 따라서:
- **`MapIntent` 스키마를 공용 모듈로 분리한다** (`intent/schema.py`)
- **`intent_extractor`도 공용으로 분리한다** (`intent/extractor.py`)
- 1차는 intent → 샘플 선택, 2차는 intent → 타일 조립. 앞단은 동일.

### 1.3 메타데이터 품질 점검 결과
- 총 293개, 누락 필드 0건, lint 충돌 0건
- 평균 태그 6.5개/맵, 설명 평균 43자
- 고유 태그 346종 — **동의어 과다** (예: 실외/야외/외부) → 정규화 필요
- 타일셋 ID 실제 의미 (데이터 기반 재확인):

  | ts | 의미 | 대표 태그 |
  |----|------|-----------|
  | 1 | 월드맵 | 월드맵, 광활한, 바다, 대륙 |
  | 2 | 자연/야외 | 실외, 마을, 숲, 사막 |
  | 3 | 건물 실내 | 실내, 침실, 상점, 주택 |
  | 4 | 던전/지하 | 던전, 동굴, 지하 |
  | 5 | 현대 야외 | 현대, 분수, 정원 |
  | 6 | SF/현대 실내 | SF, 사무실, 공장 |

---

## 2. 아키텍처

### 2.1 흐름도
```
사용자 쿼리 ("판타지 게임 만들어줘")
        │
        ▼
 [게임 생성 라우터]  ← 기존 router 노드가 분기
        │
        ▼
 [intent_extractor]  ─── LLM 1회 호출 (Solar, structured output)
        │              출력: MapIntent
        ▼
 [sample_selector]
   ├─ filter.py   : 룰 기반 점수 → 후보 20~30개
   ├─ ranker.py   : LLM 재랭킹 (압축본만 전달) → 상위 N개 file_name
   └─ selector.py : 위 둘을 묶은 entrypoint
        │
        ▼
 선택된 MapXXX.json 파일 경로 N개
        │
        ▼
 [게임 빌더] : 파일을 신규 게임 디렉터리로 복사, MapInfos.json 갱신
```

### 2.2 폴더 구조 (신규)
```
agent/generation/mapgen/
├── PLAN.md                       # 이 문서
├── generate_map_metadata.py      # 기존. 헤더 덤프 스크립트
├── normalize_tags.py              # (신규) 태그 정규화 1회 스크립트
├── data/
│   ├── map_metadata.json          # (이동) rag/data에서 이동 + 정규화 적용
│   ├── map_metadata.backup.json   # Gemini 원본 백업
│   └── tag_aliases.json           # (신규) 동의어 사전
├── intent/
│   ├── __init__.py
│   ├── schema.py                  # MapIntent (Pydantic). Phase 2와 공용
│   └── extractor.py               # 쿼리 → MapIntent. Phase 2와 공용
└── sample_selector/
    ├── __init__.py
    ├── filter.py                  # 룰 필터 + 점수
    ├── ranker.py                  # LLM 재랭킹
    └── selector.py                # entrypoint
```

**참고**: `samplemaps/` 폴더는 `agent/rag/data/samplemaps/`에 그대로 둔다 (원본 에셋은 이동하지 않음). 메타데이터만 mapgen 쪽으로 이동.

---

## 3. 데이터 설계

### 3.1 `MapIntent` 스키마 (Pydantic)
```python
class MapIntent(BaseModel):
    biome:        list[str]        # ["forest", "beach", "mountain"]
    structures:   list[str]        # ["village", "temple", "castle"]
    mood:         list[str]        # ["peaceful", "mystical", "dark"]
    era:          Literal["fantasy","medieval","modern","sf","mixed"]
    scale:        Literal["small","medium","large","world"]
    tileset_hint: list[int]        # Phase 1 전용 힌트
    n_maps:       int = 3          # 1~10
    raw_keywords: list[str]        # LLM이 추출한 한국어 원시 키워드
```
- Phase 2는 `tileset_hint`를 무시하고 `biome`/`structures`로 오토타일/배치 규칙을 선택한다.
- `raw_keywords`는 룰 필터의 태그 매칭에 직접 쓰인다.

### 3.2 `tag_aliases.json`
```json
{
  "야외": ["실외", "외부", "바깥"],
  "주택": ["집", "가옥", "가정집"],
  "판타지": ["중세풍", "중세"]
}
```
- 키가 정규화된 canonical 태그, 값이 동의어 리스트.
- `normalize_tags.py`가 이 사전으로 `map_metadata.json`의 `tags`를 일괄 치환.
- 1차 구현은 **수작업 + 통계 기반 후보 추출**로 작성 (LLM 호출 없이).

### 3.3 정규화된 `map_metadata.json`
스키마는 기존과 동일. 변경점은 `tags` 값만 canonical로 교체.

---

## 4. 알고리즘 상세

### 4.1 `filter.py` — 룰 기반 점수
입력: `MapIntent`, `map_metadata.json` 전체 (메모리에 상주, ~수백 KB)

점수식 (맵 1개에 대해):
```
score =
  w_ts   * (1 if map.tileset_id in intent.tileset_hint else 0)
+ w_tag  * |set(map.tags) ∩ set(intent.all_keywords())| / |intent.all_keywords()|
+ w_desc * (1 if any kw in map.description else 0)
+ w_scale* (scale_match_score)
```
- `intent.all_keywords()` = `biome + structures + mood + raw_keywords` 를 한국어로 매핑 (소형 매핑 테이블 내장)
- 가중치 초기값: `w_ts=2.0, w_tag=3.0, w_desc=1.0, w_scale=1.5`
- `scale_match_score`: width×height 범위 → small/medium/large/world 라벨 → intent.scale과 일치 시 1

출력: 상위 **20~30개** 후보 `(file_name, score, metadata)` 리스트

### 4.2 `ranker.py` — LLM 재랭킹
- 후보 20~30개의 **압축 표현**만 프롬프트에 넣음:
  ```
  Map027 | ts3 | 수정 광산 동굴 | [광산,동굴,수정,레일,판타지] | 레일이 깔린 광산...
  ```
- 프롬프트: "사용자 의도: {intent를 자연어로 풀어씀}. 다음 후보 중 가장 어울리는 {n_maps}개의 file_name을 JSON 배열로 반환."
- structured output (json_schema) 사용
- 다양성 힌트 추가: "가능하면 다양한 tileset_id가 포함되도록"
- 토큰 예산: 후보 30개 × ~100 토큰 ≈ 3k 토큰 입력, 출력 ~200 토큰

### 4.3 `selector.py` — entrypoint
```python
def select_maps(query: str, *, n_maps: int = 3) -> list[str]:
    intent = extract_intent(query)          # intent/extractor.py
    intent.n_maps = n_maps
    candidates = rule_filter(intent)        # filter.py (top 30)
    chosen = llm_rerank(intent, candidates) # ranker.py (top n_maps)
    return chosen                           # ["Map027.json", ...]
```

### 4.4 `intent/extractor.py` — 쿼리 → MapIntent
- Solar `solar-pro3` + structured output (json_schema)
- 프롬프트는 few-shot 2~3개 포함 (판타지/현대/SF)
- 실패 시 최소 fallback: `raw_keywords`만 채우고 나머지는 기본값

---

## 5. 게임 빌더 연동 (최초 게임 생성 경로)

### 5.1 신규 게임이 건드려야 할 데이터 파일들

| 파일 | Phase 1 동작 | 비고 |
|------|--------------|------|
| `data/MapXXX.json` | 샘플맵에서 **복사** + 리넘버링 | 원본 ID 무시, 새 게임 기준 1번부터 |
| `data/MapInfos.json` | **신규 엔트리 추가** | id/name/parentId/order/scrollX/scrollY |
| `data/Tilesets.json` | **검증만** | base_game은 ID 1~6 보장. 누락 시 경고/중단 |
| `data/System.json` | `startMapId`/`startX`/`startY` **갱신** | 첫 번째 선택 맵의 ID와 적절한 좌표 |

**핵심 사실**: `storage/games/base_game/data/Tilesets.json`은 ID 1~6을 "세계/외부/내부/던전/SF 외부/SF 내부"로 이미 보유 → 샘플맵의 `tileset_id` 1~6과 정확히 일치. Phase 1에서 Tilesets.json은 수정하지 않고 **존재 검증만** 한다.

### 5.2 구체적 단계
1. `selector.select_maps(query, n_maps=N)` 호출 → file_name 리스트 (예: `["Map001.json","Map027.json","Map055.json"]`)
2. **타일셋 검증**: 선택된 각 맵의 `tileset_id`가 신규 게임의 `Tilesets.json`에 존재하는지 확인. 누락 시 경고 로그 + 그 맵은 스킵 또는 폴백.
3. **복사 + 리넘버링**: 신규 게임 디렉터리에 `Map001.json, Map002.json, ...` 순서로 저장 (원본 파일명 무시).
4. **`MapInfos.json` 갱신**: 각 맵에 대해 엔트리 추가
   - `id`: 신규 번호
   - `name`: metadata의 `display_name`
   - `parentId`: 0 (트리 최상위) — 단순화. 추후 카테고리화 가능
   - `order`: 신규 번호
   - `scrollX`/`scrollY`: 0 (기본값)
   - `expanded`: false
5. **`System.json` 갱신**: `startMapId = 1` (첫 선택 맵), `startX`/`startY`는 맵 중앙 또는 (8,6) 기본값. 추후 샘플맵 메타에 시작 좌표 힌트를 추가할 수 있음.

### 5.3 건드리지 않는 것
- 이벤트 생성/수정 (담당 범위 밖)
- 타일셋 에셋 파일 (img/tilesets/*.png) 및 Tilesets.json 자체 (Phase 2에서 다룸)
- 게임 수정 경로

### 5.4 알려진 한계 (Phase 1 수용 사항)
- 샘플맵 내부의 **맵 간 transfer 이벤트**(다른 맵으로 이동하는 이벤트)는 원본 맵 ID를 참조하므로, 리넘버링 후 깨질 수 있음. 이벤트는 담당 범위 밖이므로 **"맵 이동 이벤트는 동작하지 않을 수 있음"을 수용**한다.
- 샘플맵 내부의 NPC/아이템/적 이벤트는 그대로 남아 있고 정상 동작.

---

## 6. 테스트 계획

### 6.1 Unit
- `normalize_tags.py` 적용 전후 diff 확인
- `filter.py`: 고정 intent에 대한 top-N 결과 스냅샷 테스트
- `MapIntent` 스키마 검증

### 6.2 Integration (LLM 호출)
- `pytest -m integration`으로 격리
- 케이스:
  - "판타지 RPG" → 월드맵(ts1) + 자연(ts2) + 던전(ts4) 혼합 기대
  - "사이버펑크 도시" → ts5/ts6 기대
  - "아늑한 마을 게임" → ts2(자연/마을) 기대
- 검증: 반환된 file_name이 실제로 메타데이터에 존재 + tileset_id 분포가 기대와 일치

### 6.3 CLI 수동 테스트
```bash
uv run python -m agent.generation.mapgen.sample_selector.selector "판타지 게임 만들어줘"
```

---

## 7. 작업 순서 (체크리스트)

### Phase 1-A: 데이터 준비
- [ ] `agent/rag/data/map_metadata.json` → `agent/generation/mapgen/data/map_metadata.backup.json`로 백업 복사
- [ ] `normalize_tags.py` 작성: 전체 태그 통계 → 동의어 후보 수작업 검토 → `tag_aliases.json` 생성
- [ ] `normalize_tags.py` 실행 → `agent/generation/mapgen/data/map_metadata.json` 생성
- [ ] `agent/rag/data/map_metadata.json` 삭제 또는 유지 결정

### Phase 1-B: Intent 계층 (Phase 2 공용)
- [ ] `intent/schema.py` — `MapIntent` Pydantic 모델
- [ ] `intent/extractor.py` — Solar 호출, structured output, few-shot
- [ ] Unit test: 샘플 쿼리 3개에 대한 intent 추출 결과 확인

### Phase 1-C: 샘플 선택기
- [ ] `sample_selector/filter.py` — 룰 점수 함수
- [ ] `sample_selector/ranker.py` — LLM 재랭킹
- [ ] `sample_selector/selector.py` — entrypoint
- [ ] CLI 진입점 추가 (`__main__.py` 또는 `selector.py` 하단 `if __name__`)

### Phase 1-D: 통합
- [ ] 게임 빌더 경로 조사: 기존 "게임 생성" 흐름에서 맵이 어디서 주입되는지 파악
- [ ] 그 지점에 `selector.select_maps()` 결과를 꽂는 어댑터 작성
- [ ] MapInfos.json 갱신 로직
- [ ] E2E 테스트: "판타지 게임 만들어줘" → 실제 신규 게임 디렉터리에 3~10개 맵 존재 확인

### Phase 1-E: LangGraph 노드 편입
- [ ] `agent/graph/workflow.py`에서 게임 생성 라우트를 찾아 `intent_extractor` + `sample_selector` 노드로 치환/추가
- [ ] `state.py`에 `map_intent`, `selected_maps` 필드 추가

---

## 8. 미결 사항 / 나중에 결정

- **가중치 튜닝**: w_ts/w_tag/w_desc/w_scale 초기값은 눈대중. 실제 쿼리 10개 정도로 돌려보고 조정.
- **`n_maps`를 사용자 쿼리에서 뽑을지, 항상 기본 3개로 할지**: 지금은 intent에 포함시키되 기본값 3.
- **샘플맵 폴더 이동 여부**: `agent/rag/data/samplemaps/` → `agent/generation/mapgen/data/samplemaps/` 이동은 별도 PR.
- **Phase 2 시작 시점**: 1차가 end-to-end로 동작하고 최소 5개 시나리오에서 만족스러운 결과가 나오면 시작.
- **`agent/rag/data/all_maps_info.json`의 운명**: `generate_map_metadata.py`의 출력물. 현재는 사용처 불분명 → Phase 1-A에서 조사 후 유지/폐기 결정.

---

## 9. 리스크 및 완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| Gemini가 채운 메타데이터에 간헐적 환각 | 선택 품질 저하 | Phase 1 운영 중 오류 케이스 수집 → 수작업 수정 |
| 태그 정규화 과정에서 의미 손실 | 변별력 저하 | 백업 유지 + diff 검토 |
| 샘플맵의 타일셋 ID가 신규 게임 프로젝트에 없는 경우 | 맵 로드 실패 | base_game(ID 1~6)에서 파생된 게임만 지원. 검증 단계에서 누락 시 경고 + 해당 맵 스킵 |
| 리넘버링으로 맵 간 transfer 이벤트가 깨짐 | 맵 이동 불가 | Phase 1 수용 사항. 이벤트 담당자와 별도 논의 |
| LLM 재랭킹 비결정성 | 같은 쿼리에 다른 결과 | temperature=0 고정 |
| `raw_keywords` 한-영 불일치 (intent 필드는 영어, 태그는 한국어) | 매칭 실패 | intent 내부 매핑 테이블로 biome/structures/mood/era를 한국어 키워드로 확장 |

---

## 10. 성공 기준 (Phase 1 완료 조건)

1. `uv run python -m agent.generation.mapgen.sample_selector.selector "판타지 게임 만들어줘"` 실행 → 3개 `MapXXX.json` 파일명 출력
2. 최소 5개 시나리오(판타지/현대/SF/호러/아늑한 마을)에서 **사람 눈으로 봤을 때 부적절한 선택 ≤ 1개**
3. LangGraph 게임 생성 경로에서 호출되어 신규 게임 디렉터리에 맵이 복사됨
4. `uv run pytest -m "not integration"`에서 unit 테스트 전부 통과
