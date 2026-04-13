# Phase 8 — 테스트 강화

> 상태: 미구현
> 우선순위: **중간** — 안정화 전 필수

---

## 목표

현재 단위 테스트(14개) → 이벤트 컴파일러 + 통합 테스트 추가

---

## 현재 테스트 커버리지

```
pytest testpaths: ["app/backend/tests", "agent/tests"]

agent/tests/
├── generation/
│   ├── test_generation_foundations.py  # 8개 — 단위 테스트
│   └── test_balance.py                 # 6개 — balance.py 단위 테스트
└── (기타 파일 — 비생성 관련)
    # test_validator.py, test_router.py, test_planner.py 등

agent/tests 전체: 126개 통과
generation/ 특화: 14개
```

LLM 실제 호출 없음. 워크플로우 end-to-end 테스트 없음.

---

## 구현 대상 (canonical: `testing_strategy.md`)

### 단위 테스트 추가

**`test_event_compiler.py`** — 6개 이벤트 타입 컴파일 결과 검증
```python
def test_compile_npc_two_pages():
    """NPC 2페이지 패턴 (condition_switch + alt_dialogue) 검증."""

def test_compile_ending_auto_run():
    """EndingEvent Auto-Run 트리거 + code 354 검증."""

def test_compile_transfer_coordinates():
    """TransferEvent to_map 이름 → ID 변환 검증."""
```

**`test_integrator.py`** — System.json / Map*.json 조립 검증
```python
def test_build_map_json_event_index_zero_null():
    """Map*.json events[0]이 null인지 검증."""

def test_build_system_json_start_pos():
    """startMapId가 town 타입 맵인지 검증."""
```

**`test_generation_validator.py`** — 각 검증 함수 개별 테스트
```python
def test_check_ending_reachable_no_boss_map():
    """보스 맵 없으면 R23 오류."""

def test_check_map_id_consistency_assets_only():
    """Map*.json 없을 때 R18 skip."""
```

### 통합 테스트 (mock LLM)

**`test_workflow_integration.py`** — LLM mock으로 전체 파이프라인 실행
```python
@pytest.fixture
def mock_llm():
    """고정 GameSpec/MapSpec/DSL 반환하는 mock."""

async def test_full_pipeline_assets_phase(mock_llm):
    """phase_limit='assets' → 8개 에셋 파일 생성."""

async def test_full_pipeline_maps_phase(mock_llm):
    """phase_limit='maps' → 에셋 + Map*.json 생성."""

async def test_full_pipeline_validator_retry(mock_llm):
    """R1 오류 발생 시 retry_assets 라우팅."""
```

실행 명령:
```bash
uv run pytest agent/tests/generation/ -v  # generation 특화만
uv run pytest agent/tests/ app/backend/tests -v  # 전체
```

---

## 완료 기준

- [ ] `uv run pytest agent/tests/ -v` — 30개 이상 통과 (현재 14개 generation 특화)
- [ ] 이벤트 컴파일러 6개 타입 전부 테스트
- [ ] 검증기 주요 함수 개별 테스트
- [ ] mock LLM으로 전체 파이프라인 3개 시나리오 통과
